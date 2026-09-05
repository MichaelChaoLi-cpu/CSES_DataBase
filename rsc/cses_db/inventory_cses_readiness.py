#!/usr/bin/env python3
"""Inventory seven CSES tables by field and wave without changing PostgreSQL or old evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from cses_baseline_metadata import canonical_sha256, connect_database, sha256_file
from cses_hh_hl_common import snake_case
from cses_lineage_graph import build_lineage_graph, read_lineage_snapshot
from cses_survey_date_contract import ACTUAL_DATE_COLUMNS, EXPECTED_EXACT_COVERAGE, enrich_hh_frame
from psycopg import sql
from publish_cses_value_mappings import DIRECTORY, existing_records, expected_records, frozen_plan

OUTPUT = "data/processing/cses/readiness_inventory_v1"
VALIDATORS = ("validate_cses_hh_hl.py", "validate_cses_ed.py", "validate_cses_ho.py",
              "validate_cses_ec.py", "validate_cses_vl.py")
LINKS = (("HL", "HH", ("survey_wave", "household_id")),
         ("HO", "HH", ("survey_wave", "household_id")),
         ("ED", "HL", ("survey_wave", "person_id")),
         ("EC", "HL", ("survey_wave", "person_id")),
         ("SURVEY_DATE", "HH", ("survey_wave", "household_id")),
         ("VL", "HH", ("survey_wave", "psu")))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def code_key(value):
    """Never turn NULL into a substantive category or a numeric missing sentinel."""
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)) and float(value).is_integer():
        return str(int(value))
    return str(value)


def availability(rows, nonnull):
    if rows == 0:
        return "wave_absent_from_table"
    if nonnull == 0:
        return "all_null_reason_not_inferred"
    return "partially_observed" if nonnull < rows else "fully_observed"


def local_frames(root, tables):
    frames = {t: pd.read_parquet(root / f"data/processing/cses/{t}.parquet")
              .rename(columns=snake_case) for t in tables}
    frames["final_HH_CSES"] = enrich_hh_frame(frames["final_HH_CSES"], frames["final_SURVEY_DATE_CSES"])
    return frames


def profile_database(connection, table, columns, keys):
    relation = sql.Identifier("cses_data", table)
    counts = sql.SQL(", ").join(sql.SQL("count({}) AS {}").format(sql.Identifier(c), sql.Identifier(c))
                               for c in columns if c != "survey_wave")
    profiles = connection.execute(sql.SQL("SELECT survey_wave, count(*) AS _rows, {} FROM {} "
        "GROUP BY survey_wave ORDER BY survey_wave").format(counts, relation)).fetchall()
    for row in profiles:
        row["_survey_wave_nonnull"] = row["_rows"] if row["survey_wave"] is not None else 0
    key_sql = sql.SQL(", ").join(map(sql.Identifier, keys))
    null_sql = sql.SQL(" OR ").join(sql.SQL("{} IS NULL").format(sql.Identifier(k)) for k in keys)
    integrity = connection.execute(sql.SQL("SELECT count(*) AS rows, count(*) FILTER (WHERE {}) AS null_key_rows, "
        "count(*)-count(DISTINCT ({})) AS duplicate_key_excess FROM {}").format(null_sql, key_sql, relation)).fetchone()
    require(integrity["null_key_rows"] == integrity["duplicate_key_excess"] == 0, f"Invalid natural key: {table}")
    return {r["survey_wave"]: r for r in profiles}, integrity


def link_inventory(connection, frames):
    result = []
    for child, parent, keys in LINKS:
        left, right = f"final_{child}_CSES", f"final_{parent}_CSES"
        # DISTINCT is intentional for VL -> HH: many households share one PSU.
        target = frames[right][list(keys)].drop_duplicates()
        checked = frames[left][list(keys)].merge(target, how="left", on=list(keys), validate="m:1", indicator=True)
        local = checked.assign(_unmatched=checked["_merge"].eq("left_only")).groupby("survey_wave")["_unmatched"].sum()
        predicate = sql.SQL(" AND ").join(sql.SQL("p.{}=c.{}").format(sql.Identifier(k), sql.Identifier(k)) for k in keys)
        actual = connection.execute(sql.SQL("SELECT c.survey_wave, count(*) AS child_rows, "
            "count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM {} p WHERE {})) AS unmatched_rows "
            "FROM {} c GROUP BY c.survey_wave ORDER BY c.survey_wave").format(
                sql.Identifier("cses_data", right), predicate, sql.Identifier("cses_data", left))).fetchall()
        for row in actual:
            require(row["unmatched_rows"] == int(local[row["survey_wave"]]), f"Local/live linkage differs: {left}")
        result.append({"child_table": left, "parent_table": right, "keys": list(keys),
                       "parent_keys_unique": not frames[right].duplicated(list(keys)).any().item(),
                       "join_warning": "Deduplicate parent PSU keys or aggregate first" if child == "VL"
                                       else "Retain unmatched child rows; do not silently inner-join",
                       "waves": actual})
    return result


def field_rows(snapshot, frames, profiles, approved, review):
    waves = sorted(r["survey_wave"] for r in snapshot["surveys"])
    survey_waves = {r["survey_id"]: r["survey_wave"] for r in snapshot["surveys"]}
    datasets = {r["dataset_id"]: r for r in snapshot["datasets"]}
    sources = {(r["dataset_id"], r["variable_name"]): r for r in snapshot["source_variables"]}
    questions = {r["question_id"]: r for r in snapshot["questions"]}
    mappings = defaultdict(list)
    for mapping in snapshot["variable_mappings"]:
        wave = survey_waves[datasets[mapping["dataset_id"]]["survey_id"]]
        mappings[(mapping["canonical_variable_id"], wave)].append(mapping)
    approved_index, review_index = defaultdict(list), defaultdict(list)
    for row in approved:
        approved_index[(row["canonical_name"], row["survey_wave"])].append(row)
    for row in review:
        review_index[(row["canonical_name"], row["survey_wave"])].append(row)
    records = []
    for canonical in snapshot["canonical_variables"]:
        table, column = canonical["target_table"], canonical["canonical_name"]
        if table not in frames:
            continue
        frame = frames[table]
        for wave in waves:
            selected = frame.loc[frame["survey_wave"].eq(wave), column]
            total, nonnull = len(selected), int(selected.notna().sum())
            live = profiles[table].get(wave, {})
            live_nonnull = live.get("_survey_wave_nonnull" if column == "survey_wave" else column, 0)
            require(live.get("_rows", 0) == total and live_nonnull == nonnull, f"Profile mismatch: {table}/{column}/{wave}")
            rules = mappings[(canonical["canonical_variable_id"], wave)]
            source_keys = sorted({(m["dataset_id"], name) for m in rules for name in m["source_variable_names"]})
            evidence = []
            for key in source_keys:
                source = sources[key]
                question = questions.get(source["question_id"])
                evidence.append({"dataset_id": key[0], "variable": key[1], "source_label": source["variable_label"],
                    "question_id": source["question_id"], "question_link_status": source["question_link_status"],
                    "question_documentation_status": question["documentation_status"] if question else None,
                    "is_exact_question_text": question["is_exact_question_text"] if question else None})
            approved_codes = approved_index[(column, wave)] if table == "final_HO_CSES" else []
            reviewed = review_index[(column, wave)] if table == "final_HO_CSES" else []
            allowed = {r["source_code"] for r in approved_codes}
            observed = Counter(code_key(v) for v in selected.dropna()) if reviewed else Counter()
            covered = sum(n for code, n in observed.items() if code in allowed)
            records.append({"table": table, "field": column, "survey_wave": wave,
                "database_type": canonical["database_type"], "measure_type": canonical["measure_type"],
                "definition": canonical["canonical_definition"], "catalog_status": canonical["status"],
                "row_count": total, "nonnull_count": nonnull, "null_count": total - nonnull,
                "distinct_nonnull_local": int(selected.nunique()), "availability": availability(total, nonnull),
                "structure_and_nonnull_profile": "local_live_match" if total else "wave_absent_from_table",
                "cell_equality_scope": "Not tested by aggregate profile; see separate accepted release validation",
                "mapping_record_ids": [m["variable_mapping_id"] for m in rules],
                "mapping_versions": sorted({m["mapping_version"] for m in rules}),
                "mapping_note": "Historical versions retained; IDs are not an effective-rule selection",
                "source_evidence": evidence,
                "source_rule_coverage": "registered" if rules else "no_direct_mapping_record_not_proof_of_missing_provenance",
                "published_dictionary_entries": len(approved_codes),
                "dictionary_matched_nonnull_rows": covered if reviewed else None,
                "dictionary_unmatched_nonnull_rows": nonnull - covered if reviewed else None,
                "review_bucket_counts": dict(sorted(Counter(r["review_bucket"] for r in reviewed).items())),
                "semantic_readiness": "approved_dictionary_scope_with_qualifications" if approved_codes
                                      else "builder_definition_recorded_not_reaudited_for_analysis",
                "units_and_missingness_review": "existing_definition_retained_not_reaudited",
                "cross_wave_comparability": "not_certified_by_this_inventory",
                "housing_review_row_ids": [r["review_row_id"] for r in reviewed]})
    return records


def render(report):
    lines = ["# CSES Core Table Readiness Inventory v1", "",
        "Read-only inventory, not semantic approval or an analysis-ready certification.", "",
        "## Table summary", "", "| Table | Rows | Fields | Waves | Key/profile checks | Dictionary field-wave cells |",
        "|---|---:|---:|---:|---|---:|"]
    for table in report["tables"]:
        lines.append(f'| {table["table"]} | {table["rows"]} | {table["columns"]} | {table["waves"]} | passed | {table["dictionary_field_wave_cells"]} |')
    lines += ["", "HH is enriched in memory with three existing date components before comparison; its base Parquet has 32 fields, the database has 35.",
        "Every table field is listed for all ten catalog waves, including absent table/wave combinations.", "",
        "## Linkage findings", "", "| Child → parent | Wave | Child rows | Unmatched child rows |", "|---|---|---:|---:|"]
    for link in report["links"]:
        for wave in link["waves"]:
            if wave["unmatched_rows"]:
                lines.append(f'| {link["child_table"]} → {link["parent_table"]} | {wave["survey_wave"]} | {wave["child_rows"]} | {wave["unmatched_rows"]} |')
    lines += ["", "VL → HH uses distinct PSU keys: an ordinary household join multiplies village records.",
        "Unmatched records are retained source exceptions, not authorization to delete them.", "",
        "## Housing dictionary coverage", "", "| Field | Wave | Non-null rows | Approved codes | Matched rows | Unmatched rows |",
        "|---|---|---:|---:|---:|---:|"]
    for row in report["fields"]:
        if row["housing_review_row_ids"]:
            lines.append(f'| {row["field"]} | {row["survey_wave"]} | {row["nonnull_count"]} | {row["published_dictionary_entries"]} | {row["dictionary_matched_nonnull_rows"]} | {row["dictionary_unmatched_nonnull_rows"]} |')
    lines += ["", "Counts above are per-field observations, not additive household populations. SQL NULL reasons are not inferred.",
        "The 140 published codes retain draft, skip, compound and residual qualifications; 52 unresolved and 16 missing-only review codes remain excluded.",
        "", "## Next work and boundaries", "",
        "1. Housing: design a version-selected, left-joined dictionary interface retaining raw codes and explicit unmatched/missing states; no database view is created here.",
        "2. Household/member spine: review weights, identifier meanings and retained linkage exceptions before defining analytic samples.",
        "3. Education/employment: review population eligibility, coding, periods and units using their existing builder definitions as evidence, not a new approval.",
        "4. Village/date: respect PSU grain; exact household dates exist only for 2004, 2019 and 2021. Do not impute an interview day from release year.",
        "", "## Complete field × wave checklist", "",
        "Detailed definitions, source labels/question links, historical mapping IDs and review identities are in `inventory.json`.",
        "Observed/non-null coverage is not semantic completeness. No overall percentage is assigned.", "",
        "| Table | Field | Wave | Non-null / rows | Availability | Source rules | Dictionary entries |", "|---|---|---|---:|---|---:|---:|"]
    for row in report["fields"]:
        lines.append(f'| {row["table"]} | {row["field"]} | {row["survey_wave"]} | {row["nonnull_count"]}/{row["row_count"]} | {row["availability"]} | {len(row["mapping_record_ids"])} | {row["published_dictionary_entries"]} |')
    return "\n".join(lines) + "\n"


def write_outputs(directory, report):
    outputs = {"inventory.json": json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
               "inventory.md": render(report)}
    for name, content in outputs.items():
        require(not (directory / name).exists() or (directory / name).read_text() == content,
                f"Existing inventory differs; choose a new output directory: {name}")
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        if not (directory / name).exists():
            (directory / name).write_text(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    contract = json.loads((root / "rsc/specs/cses_schema_v1.json").read_text())
    targets = [r for r in contract["relations"] if r["family"] == "final"]
    require(len(targets) == 7, "Expected seven core tables")
    plan = frozen_plan(root)
    execution = json.loads((root / DIRECTORY / "execution.json").read_text())
    imported = json.loads((root / DIRECTORY / "import.json").read_text())
    execution_hash = sha256_file(root / DIRECTORY / "execution.json")
    require(execution_hash == imported["execution_sha256"], "Execution binding changed")
    desired = expected_records(plan, execution, execution_hash)
    require(canonical_sha256(desired) == imported["published_records_sha256"], "Import binding changed")
    review = json.loads((root / "data/processing/cses/value_mapping_review_v1/review.json").read_text())
    evidence_paths = sorted(set(
        [p.relative_to(root).as_posix() for folder in ("rsc/cses_db", "rsc/specs")
         for p in (root / folder).iterdir() if p.suffix in {".py", ".json"}]
        + [p.relative_to(root).as_posix() for p in (root / "data/processing/cses").iterdir()
           if p.is_file() and p.suffix in {".parquet", ".csv", ".md"}]
        + [f"{DIRECTORY}/{name}.json" for name in ("execution", "import", "validation")]
        + ["data/lineage/cses_lineage_graph_v6.json", "data/processing/cses/value_mapping_release_v1/plan.json",
           "data/processing/cses/value_mapping_review_v1/review.json", "data.dvc"]))
    hashes = {p: sha256_file(root / p) for p in evidence_paths}
    validators = []
    for script in VALIDATORS:
        run = subprocess.run([sys.executable, str(root / "rsc/cses_db" / script)], cwd=root,
                             capture_output=True, text=True, check=True)
        validators.append({"script": script, "passed": True, "stdout": run.stdout, "stderr": run.stderr})
        print(f"validator_passed={script}", flush=True)
    frames = local_frames(root, [r["name"] for r in targets])
    dates = frames["final_SURVEY_DATE_CSES"]
    exact = dates.groupby("survey_wave")["candidate_reference_date"].count().to_dict()
    require({k: int(v) for k, v in exact.items() if v} == EXPECTED_EXACT_COVERAGE, "Exact-date coverage differs")
    profiles, tables = {}, []
    with connect_database({"dbname": "mda"}) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL statement_timeout='55s'")
        snapshot = read_lineage_snapshot(connection)
        require(snapshot["database"] == {"database": "mda", "transaction_read_only": "on"}, "Read-only mda required")
        graph = json.loads((root / "data/lineage/cses_lineage_graph_v6.json").read_text())
        require(build_lineage_graph(snapshot, graph["source"]["exporter_code_git_revision"]) == graph,
                "Catalog projection changed from accepted v6")
        require(existing_records(connection) == desired, "Published dictionary differs from approved plan")
        canonical = {(r["target_table"], r["canonical_name"]): r for r in snapshot["canonical_variables"]}
        for target in targets:
            table = target["name"]
            frame = frames[table]
            columns = connection.execute("SELECT a.attname, format_type(a.atttypid,a.atttypmod) AS data_type "
                "FROM pg_attribute a WHERE a.attrelid=%s::regclass AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum",
                (f'cses_data."{table}"',)).fetchall()
            require([r["attname"] for r in columns] == list(frame.columns), f"Column order differs: {table}")
            require(all(canonical[(table, r["attname"])]["database_type"] == r["data_type"] for r in columns),
                    f"Catalog type differs: {table}")
            profiles[table], integrity = profile_database(connection, table, list(frame.columns), target["natural_key"])
            require(integrity["rows"] == len(frame), f"Row count differs: {table}")
            tables.append({"table": table, "rows": len(frame), "columns": len(frame.columns),
                "waves": frame["survey_wave"].nunique(), "natural_key": target["natural_key"],
                "key_checks": integrity, "column_order_and_catalog_types_match": True,
                "in_memory_extension": ACTUAL_DATE_COLUMNS if table == "final_HH_CSES" else [],
                "dictionary_field_wave_cells": 0})
            print(f"database_profile_passed={table}", flush=True)
        links = link_inventory(connection, frames)
        fields = field_rows(snapshot, frames, profiles, plan["approved_rows"], review["code_rows"])
    require(len(fields) == 2800, "Expected 280 fields times ten catalog waves")
    for table in tables:
        table["dictionary_field_wave_cells"] = sum(r["table"] == table["table"] and r["published_dictionary_entries"] > 0 for r in fields)
    require({p: sha256_file(root / p) for p in evidence_paths} == hashes, "Inputs changed while inventory ran")
    report = {"schema_version": 1, "inventory_id": "cses-readiness-inventory-v1", "database_mutated": False,
        "transaction_read_only": True, "checks_passed": True, "table_count": len(tables), "field_wave_count": len(fields),
        "evidence_sha256": hashes, "code_base_git_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "code_provenance_note": "Base commit may precede new inventory code; exact executed files are bound by SHA-256.",
        "tables": tables, "fields": fields, "links": links, "local_validators": validators,
        "exact_date_coverage": {k: int(v) for k, v in exact.items()},
        "semantic_scope": "No new semantic approval; builder definitions and approved housing dictionary remain qualified",
        "verification_limit": "Live structure, natural keys, wave rows and per-field non-null counts; not full seven-table cell equality or fresh raw-data rebuild"}
    write_outputs((root / args.output_dir) if args.output_dir else root / OUTPUT, report)
    print(f"inventory_passed=True tables={len(tables)} field_wave_cells={len(fields)} database_mutated=False", flush=True)


if __name__ == "__main__":
    main()
