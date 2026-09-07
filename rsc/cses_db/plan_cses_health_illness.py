#!/usr/bin/env python3
"""Design the first HEALTH table and check HH/HL linkage; no database writes.

Read only local processed caches. With --check-database, compare the relevant
live HH/HL key projections and inspect target/catalog readiness in a read-only
transaction. Proposed DDL is an artifact and is never executed here.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd
from build_cses_health import ROW_NUMBER, load_source
from cache_cses_questionnaires import add_artifact, file_sha, put, require, verify_manifest
from cses_hh_hl_common import ID_WIDTHS, clean_code, snake_case
from organize_cses_questionnaires import WAVES

SPEC = "rsc/specs/cses_health_illness_table_v1.json"
HEALTH = "data/processed/cses_health/v1"
QUESTIONNAIRES = "data/processed/cses_questionnaires/v1"
OUTPUT = "data/processing/cses/health_illness_preflight_v1"
BASELINES = {
    "hl": "data/processing/cses/final_HL_CSES.parquet",
    "hh": "data/processing/cses/final_HH_CSES.parquet",
}
KEY_COLUMNS = {"hl": ["survey_wave", "household_id", "person_id"], "hh": ["survey_wave", "household_id"]}


def canonical_keys(frame, kind):
    frame = frame.rename(columns=snake_case)[KEY_COLUMNS[kind]].astype("string")
    require(not frame.isna().any().any(), f"Missing {kind} baseline identifiers")
    unique = ["survey_wave", "person_id"] if kind == "hl" else KEY_COLUMNS[kind]
    require(not frame.duplicated(unique).any(), f"Ambiguous {kind} baseline keys")
    return frame.sort_values(KEY_COLUMNS[kind]).reset_index(drop=True)


def source_keys(frame, wave):
    names = {c.lower(): c for c in frame}
    require("hhid" in names and "persid" in names, "Missing native ID columns")
    keys = pd.DataFrame(index=frame.index)
    keys["survey_wave"] = pd.Series(wave, index=frame.index, dtype="string")
    for native, output, title in [("hhid", "household_id", "Household ID"), ("persid", "person_id", "Person ID")]:
        keys[output], invalid = clean_code(frame[names[native]], ID_WIDTHS[wave][title])
        require(invalid == 0 and keys[output].notna().all(), f"Invalid source {native} in {wave}")
    require(not keys.duplicated(KEY_COLUMNS["hl"]).any(), "Duplicate normalized source keys")
    return keys


def link_keys(keys, hh, hl):
    """No many-to-many expansion, household-only person matching or row deletion."""
    keys = keys.reset_index(drop=True).copy()
    keys["_order"] = range(len(keys))
    linked = keys.merge(
        hl.rename(columns={"household_id": "roster_household_id"}),
        on=["survey_wave", "person_id"],
        how="left",
        validate="many_to_one",
    )
    linked["hl_link_status"] = "matched"
    absent = linked.roster_household_id.isna()
    conflict = ~absent & linked.household_id.ne(linked.roster_household_id)
    linked.loc[absent, "hl_link_status"] = "person_not_in_roster"
    linked.loc[conflict, "hl_link_status"] = "household_conflict"
    linked = linked.merge(hh.assign(hh_link_matched=True), on=KEY_COLUMNS["hh"], how="left", validate="many_to_one")
    linked["hh_link_matched"] = linked.hh_link_matched.eq(True)
    linked = linked.sort_values("_order").drop(columns="_order").reset_index(drop=True)
    require(len(linked) == len(keys), "Linkage changed source row count")
    linked["hl_link_status"] = linked.hl_link_status.astype("string")
    linked["roster_household_id"] = linked.roster_household_id.astype("string")
    return linked


def evidence_status(library, wave):
    sources = [s for s in library["sources"] if s["survey_wave"] == wave]
    primary = [
        s
        for s in sources
        if s["instrument_type"] == "household_questionnaire"
        and s["language_code"] == "en"
        and s.get("registered_instrument_id") is not None
    ]
    if primary:
        require(len(primary) == 1, "Ambiguous registered English household form")
        return (
            "draft_form_available"
            if primary[0]["documentation_status"] == "provisional"
            else "form_available_unreviewed_for_health"
        )
    if any(s["instrument_type"] in {"forms_bundle", "questionnaire_bundle"} for s in sources):
        return "image_bundle_not_transcribed"
    return "household_form_not_located"


def raw_json_records(frame):
    """Use Python float repr, not pandas' default ten-digit JSON precision."""
    names = list(frame.columns)
    require(all(isinstance(c, str) for c in names), "Native field names must be strings")
    result = []
    for row in frame.itertuples(index=False, name=None):
        record = {name: None if pd.isna(value) else value for name, value in zip(names, row, strict=True)}
        result.append(json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    return pd.Series(result, index=frame.index, dtype="string")


def check_raw_roundtrip(frame, records):
    restored = pd.DataFrame([json.loads(value) for value in records], columns=frame.columns)
    for column in frame:
        restored[column] = restored[column].astype(frame[column].dtype)
    pd.testing.assert_frame_equal(frame.reset_index(drop=True), restored, check_exact=True)


def proposed_ddl(spec):
    # Spec values are local code-owned identifiers; still quote every identifier.
    def ident(value):
        return '"' + value.replace('"', '""') + '"'

    columns = [f"    {ident(c['name'])} {c['type']}" + ("" if c["nullable"] else " NOT NULL") for c in spec["columns"]]
    columns += [
        "    PRIMARY KEY (" + ", ".join(map(ident, spec["primary_key"])) + ")",
        "    UNIQUE (" + ", ".join(map(ident, spec["unique_key"])) + ")",
        "    CHECK (source_row_number > 0)",
        "    CHECK (source_sha256 ~ '^[0-9a-f]{64}$')",
        "    CHECK (jsonb_typeof(raw_record) = 'object')",
        "    CHECK (jsonb_typeof(source_member_chain) = 'array')",
        "    CHECK (hl_link_status IN ('matched','person_not_in_roster','household_conflict'))",
        "    CHECK (harmonization_status = 'native_codes_not_harmonized')",
    ]
    return (
        "-- DESIGN ONLY. Not executed by this preflight.\n"
        "-- A future publisher must include registry/lineage and transactional load validation.\n"
        f"CREATE TABLE {ident(spec['target_schema'])}.{ident(spec['target_table'])} (\n"
        + ",\n".join(columns)
        + "\n);\n"
    )


def database_preflight(spec, baselines, sources):
    from cses_baseline_metadata import connect_database
    from psycopg import sql
    from publish_cses_age_topcode import read_only

    with connect_database({"dbname": "mda"}) as conn:
        read_only(conn)
        comparisons = {}
        for kind, table in [("hl", "final_HL_CSES"), ("hh", "final_HH_CSES")]:
            records = conn.execute(
                sql.SQL("SELECT {} FROM {}").format(
                    sql.SQL(",").join(map(sql.Identifier, KEY_COLUMNS[kind])), sql.Identifier("cses_data", table)
                )
            ).fetchall()
            actual = canonical_keys(pd.DataFrame.from_records(records, columns=KEY_COLUMNS[kind]), kind)
            pd.testing.assert_frame_equal(actual, baselines[kind], check_exact=True)
            comparisons[kind] = {
                "rows_checked": len(actual),
                "key_columns": KEY_COLUMNS[kind],
                "every_key_matches_local_baseline": True,
            }
        target = conn.execute(
            "SELECT to_regclass(%s)::text AS relation", (f"{spec['target_schema']}.{spec['target_table']}",)
        ).fetchone()["relation"]
        permissions = conn.execute("""SELECT
          has_schema_privilege(current_user,'cses_data','CREATE') AS can_create,
          (SELECT count(*) FROM pg_event_trigger WHERE evtenabled <> 'D') AS active_event_triggers""").fetchone()
        current = conn.execute("""SELECT
          (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname IN ('cses_meta','cses_alignment','cses_data','cses_analysis') AND c.relkind='r') AS physical_relations,
          (SELECT count(*) FROM cses_meta.cses_dataset) AS datasets,
          (SELECT count(*) FROM cses_alignment.cses_source_variable) AS source_variables,
          (SELECT count(*) FROM cses_alignment.cses_canonical_variable) AS canonical_variables""").fetchone()
        registered = conn.execute("""SELECT d.dataset_id,d.module_code,s.survey_wave,
          a.relative_path,d.member_path,d.nested_member_path FROM cses_meta.cses_dataset d
          JOIN cses_meta.cses_source_archive a USING(source_archive_id)
          JOIN cses_meta.cses_survey s ON s.survey_id=d.survey_id""").fetchall()
        existing = []
        for source in sources:
            chain = source["member_chain"]
            matches = [
                d["dataset_id"]
                for d in registered
                if d["relative_path"] == source["archive_relative_path"]
                and d["survey_wave"] == source["survey_wave"]
                and d["member_path"] == chain[0]
                and (d["nested_member_path"] or None) == ("::".join(chain[1:]) or None)
            ]
            existing.append({"source_id": source["source_id"], "matching_dataset_ids": matches})
        require(
            conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on", "Read-only lost"
        )
    checks = {
        "target_absent": target is None,
        "create_privilege_available": permissions["can_create"],
        "no_active_ddl_event_triggers": permissions["active_event_triggers"] == 0,
        "live_spine_keys_equal_local": True,
    }
    return {
        "database_mutated": False,
        "transaction_read_only": True,
        "checks": checks,
        "structural_preflight_passed": all(checks.values()),
        "baseline_comparisons": comparisons,
        "current_catalog_counts": current,
        "existing_health_dataset_registrations": existing,
        "scope_limit": "No DDL, COPY/load, constraint execution, backup check or write-transaction validation performed.",
    }


def build(root, output, check_database=False):
    spec = json.loads((root / SPEC).read_text())
    require(not spec["database_publication_authorized"], "Preflight cannot authorize publication")
    intake = verify_manifest(root / HEALTH)
    library = verify_manifest(root / QUESTIONNAIRES)
    require(
        file_sha(root / QUESTIONNAIRES / "manifest.json") == intake["questionnaire_library_manifest_sha256"],
        "Questionnaire library differs from intake",
    )
    baselines = {kind: canonical_keys(pd.read_parquet(root / path), kind) for kind, path in BASELINES.items()}
    sources = sorted(
        [s for s in intake["sources"] if s["topic"] == spec["source_topic"]],
        key=lambda s: WAVES.index(s["survey_wave"]),
    )
    require(
        Counter(s["survey_wave"] for s in sources) == Counter({w: 1 for w in WAVES}),
        "Exactly one illness source per wave required",
    )
    frames, summaries, variables, missing_roster, missing_health = [], [], [], [], []
    for source in sources:
        wave = source["survey_wave"]
        require(source["extended_missing_cells"] == 0, "Extended missing requires a new explicit table representation")
        native = load_source(root / HEALTH, source["source_id"])
        require(len(native) == spec["expected_source_records"][wave], "Source count drift")
        keys = source_keys(native, wave)
        linked = link_keys(keys, baselines["hh"], baselines["hl"])
        linked["source_id"] = source["source_id"]
        linked["source_row_number"] = native[ROW_NUMBER].astype("int64")
        linked["source_archive"] = source["archive_relative_path"]
        linked["source_member_chain"] = json.dumps(source["member_chain"], ensure_ascii=False)
        linked["source_sha256"] = source["source_sha256"]
        raw = native.drop(columns=ROW_NUMBER)
        linked["raw_record"] = raw_json_records(raw)
        check_raw_roundtrip(raw, linked.raw_record)
        linked["questionnaire_evidence_status"] = evidence_status(library, wave)
        linked["harmonization_status"] = "native_codes_not_harmonized"
        for column in spec["columns"]:
            if column["type"] in {"text", "jsonb"}:
                linked[column["name"]] = linked[column["name"]].astype("string")
            if not column["nullable"]:
                require(linked[column["name"]].notna().all(), f"Null required column: {column['name']}")
        frames.append(linked[[c["name"] for c in spec["columns"]]])
        unmatched = linked.loc[
            linked.hl_link_status.ne("matched"),
            ["survey_wave", "household_id", "person_id", "source_id", "source_row_number", "hl_link_status"],
        ]
        missing_roster.append(unmatched)
        roster = baselines["hl"].loc[baselines["hl"].survey_wave.eq(wave)]
        coverage = roster.merge(keys, how="left", indicator=True, validate="one_to_one")
        unrepresented = coverage.loc[coverage._merge.eq("left_only"), KEY_COLUMNS["hl"]]
        missing_health.append(unrepresented)
        statuses = Counter(linked.hl_link_status)
        summary = {
            "survey_wave": wave,
            "source_records": len(linked),
            "roster_records": len(roster),
            "hl_matched": statuses["matched"],
            "person_not_in_roster": statuses["person_not_in_roster"],
            "household_conflict": statuses["household_conflict"],
            "hh_unmatched": int((~linked.hh_link_matched).sum()),
            "roster_without_health_record": len(unrepresented),
            "questionnaire_evidence_status": evidence_status(library, wave),
        }
        summaries.append(summary)
        variables.extend(
            {
                **field,
                "survey_wave": wave,
                "source_id": source["source_id"],
                "target_location": ["raw_record", field["variable_name"]],
                "question_semantics_reviewed": False,
            }
            for field in source["fields"]
        )
        print(
            f"{wave}: {len(linked):,} retained; {len(unmatched)} HL unmatched; {len(unrepresented)} roster-only",
            flush=True,
        )
    combined = pd.concat(frames, ignore_index=True)
    for key in [spec["primary_key"], spec["unique_key"]]:
        require(not combined.duplicated(key).any(), f"Duplicate proposed key: {key}")
    preflight = database_preflight(spec, baselines, sources) if check_database else {"database_checked": False}
    artifacts = {}
    for name, frame in [
        ("illness_source.parquet", combined),
        ("health_without_roster.parquet", pd.concat(missing_roster, ignore_index=True)),
        ("roster_without_health.parquet", pd.concat(missing_health, ignore_index=True)),
    ]:
        payload = frame.to_parquet(index=False)
        import io

        pd.testing.assert_frame_equal(frame, pd.read_parquet(io.BytesIO(payload)), check_exact=True)
        add_artifact(output, artifacts, name, payload)
    add_artifact(output, artifacts, "source_variables.json", variables)
    add_artifact(output, artifacts, "proposed_schema.sql", proposed_ddl(spec))
    metadata_todo = [
        "Register the ten illness/care source datasets and native variable dictionaries, avoiding duplicate source identities.",
        "Register one physical output, source-to-output edges, a named release and load run.",
        "Record all native-field storage mappings without asserting new questionnaire links or harmonized semantics.",
        "Prepare a backup and transactional publisher; retain the five unlinked source people unless a reviewed correction resolves them.",
        "Recheck target absence, live HH/HL key hashes, reader permissions and post-load equality immediately before publication.",
    ]
    plan = {
        "plan_id": spec["plan_id"],
        "target": f"{spec['target_schema']}.{spec['target_table']}",
        "stage": spec["stage"],
        "database_mutated": False,
        "publication_approved": False,
        "table_created": False,
        "columns": spec["columns"],
        "primary_key": spec["primary_key"],
        "unique_key": spec["unique_key"],
        "foreign_keys": [],
        "waves": summaries,
        "source_rows": len(combined),
        "source_variable_occurrences": len(variables),
        "hl_matched": int(combined.hl_link_status.eq("matched").sum()),
        "hl_unmatched": int(combined.hl_link_status.ne("matched").sum()),
        "hh_unmatched": int((~combined.hh_link_matched).sum()),
        "roster_without_health_record": sum(s["roster_without_health_record"] for s in summaries),
        "all_native_fields_roundtrip_exact": True,
        "preflight": preflight,
        "remaining_publication_steps": metadata_todo,
        "artifacts": artifacts,
        "sources": [
            {
                k: s[k]
                for k in [
                    "source_id",
                    "source_file",
                    "source_sha256",
                    "survey_wave",
                    "member_chain",
                    "archive_relative_path",
                ]
            }
            for s in sources
        ],
        "input_sha256": {
            p: file_sha(root / p)
            for p in [
                SPEC,
                HEALTH + "/manifest.json",
                QUESTIONNAIRES + "/manifest.json",
                *BASELINES.values(),
                "rsc/cses_db/cses_hh_hl_common.py",
            ]
        },
        "implementation_sha256": file_sha(Path(__file__)),
    }
    lines = [
        "# Illness/care table preflight",
        "",
        f"Proposed target: `{plan['target']}`. Table not created.",
        "",
        f"{len(combined):,} source records retained in {len(spec['columns'])} storage columns. "
        "Storage columns are not counts of health questions. Native fields remain inside raw_record.",
        "",
        "| Wave | Source rows | HL matched | HL unmatched | Roster without health | HH unmatched |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for s in summaries:
        lines.append(
            f"| {s['survey_wave']} | {s['source_records']:,} | {s['hl_matched']:,} | "
            f"{s['person_not_in_roster'] + s['household_conflict']} | {s['roster_without_health_record']} | {s['hh_unmatched']} |"
        )
    lines.extend(
        [
            "",
            "Unmatched records are retained, not dropped, relabeled or supplemented with fabricated responses.",
            "",
            "[Source-preserving table](illness_source.parquet) · [Native variables](source_variables.json) · "
            "[Proposed DDL, not executed](proposed_schema.sql)",
            "",
            "[Health without roster](health_without_roster.parquet) · [Roster without health](roster_without_health.parquet)",
            "",
            "These audit files contain source identifiers and remain DVC-owned; do not paste individual records into public reports.",
            "",
            "## Publication still pending",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in metadata_todo)
    lines.append("")
    add_artifact(output, artifacts, "README.md", "\n".join(lines))
    put(output / "plan.json", plan)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-database", action="store_true")
    args = parser.parse_args()
    plan = build(args.root, args.output or args.root / OUTPUT, args.check_database)
    print(
        json.dumps(
            {
                k: plan[k]
                for k in [
                    "source_rows",
                    "source_variable_occurrences",
                    "hl_unmatched",
                    "roster_without_health_record",
                    "table_created",
                ]
            }
        )
    )


if __name__ == "__main__":
    main()
