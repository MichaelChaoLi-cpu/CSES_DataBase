#!/usr/bin/env python3
"""Recheck the 140 approved housing meanings and prepare a read-only publication plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from correct_cses_housing_lighting import (
    PATH_COMPARISON,
    check_database_state,
    compare_database_to_local,
    database_snapshot,
    release_records,
    verify_release_records,
)
from cses_baseline_metadata import canonical_sha256, connect_database, sha256_file
from inventory_cses_archives import DataSource
from plan_cses_value_audit import parse_option_cell
from plan_cses_value_mapping_review import CODE_PATHS, build_review, load_inputs
from record_cses_value_mapping_decisions import require

SPEC = "rsc/specs/cses_value_mapping_release_v1.json"


def load_context(root: Path) -> tuple[dict, dict, dict]:
    spec = json.loads((root / SPEC).read_text())
    context = {}
    for name, descriptor in spec["inputs"].items():
        path = root / descriptor["path"]
        require(sha256_file(path) == descriptor["sha256"], f"Input fingerprint changed: {name}")
        context[name] = json.loads(path.read_text())
    # Historical outputs retain the hashes of their actual, possibly uncommitted implementation.
    for path, digest in context["review"]["provenance"]["code_files_sha256"].items():
        require(sha256_file(root / path) == digest, f"Review implementation changed: {path}")
    evidence = load_inputs(root, context["review_spec"])
    rebuilt = build_review(root, context["review_spec"], evidence)
    require(all(context["review"][key] == value for key, value in rebuilt.items()),
            "Fresh raw/local review differs from accepted evidence")
    return spec, context, evidence


def verify_questionnaire_options(root: Path, rows: list[dict], audit_spec: dict) -> int:
    descriptor = audit_spec["evidence"]["questionnaire_cells"]
    path = root / descriptor["path"]
    require(sha256_file(path) == descriptor["sha256"], "Questionnaire cell evidence changed")
    instruments = {i["source_file"]: i for i in json.loads(path.read_text())["instruments"]}
    for instrument in instruments.values():
        archive, member = instrument["source_file"].split("::", 1)
        payload = DataSource(root / archive, (member,)).read_bytes()
        require(hashlib.sha256(payload).hexdigest() == instrument["source_sha256"], "Questionnaire member changed")
    checked = 0
    for row in rows:
        option = row["questionnaire_option"]
        if option is None:
            require(bool(row["source_label"]), "No source label or questionnaire option")
            continue
        question = row["evidence"]["questionnaire"]
        instrument = instruments[question["source_file"]]
        require(question["source_sha256"] == instrument["source_sha256"], "Questionnaire identity mismatch")
        require(question["source_sheet"] == instrument["source_sheet"], "Questionnaire sheet mismatch")
        require(option["source_cell"] in question["option_cells"], "Option outside cataloged cells")
        parsed = parse_option_cell(instrument["cells"][option["source_cell"]], option["source_cell"])
        require([item for item in parsed if item["source_code"] == row["source_code"]] == [option],
                "Option code/label/skip text differs from retained cell")
        checked += 1
    return checked


def approved_rows(spec: dict, context: dict) -> list[dict]:
    source = context["review"]
    rows = [r for r in source["code_rows"] if r["review_bucket"] in spec["selected_buckets"]]
    require(Counter(r["review_bucket"] for r in rows) == {"candidate": 70, "manual_review": 70},
            "Approved buckets differ from the exact 70 + 70 scope")
    require(len({r["review_row_id"] for r in rows}) == 140, "Duplicate approved identity")
    manual = {r["review_row_id"]: r for r in context["manual_decisions"]["approved_decisions"]}
    require(set(manual) == {r["review_row_id"] for r in rows if r["review_bucket"] == "manual_review"},
            "Prior manual approval identities differ")
    labels = {**context["manual_spec"]["canonical_labels"], **spec["additional_labels"]}
    result = []
    for row in rows:
        require(row["code_kind"] == "numeric" and row["missing_class"] == "substantive", "Non-substantive selection")
        value = row["candidate_category"]
        require(value in labels, "Missing approved display label")
        require(row["review_row_id"] == canonical_sha256(row["source_key"]), "Source identity does not match row hash")
        require(row["category_key"] == f"{row['canonical_name']}:{value}", "Category identity differs from field/value")
        if row["review_row_id"] in manual:
            old = manual[row["review_row_id"]]
            require(old["approved_canonical_value"] == value and old["source_key"] == row["source_key"]
                    and old["approved_canonical_label"] == labels[value], "Prior approved decision changed")
        result.append({**row, "semantic_status": "approved", "approved_canonical_value": value,
                       "approved_canonical_label": labels[value], "publication_status": "planned"})
    result.sort(key=lambda r: (r["survey_wave"], r["canonical_name"], int(r["source_code"])))
    return result


def mapping_key(row: dict) -> tuple:
    key = row["source_key"]
    return tuple(key[name] for name in ("archive_relative_path", "member_path", "nested_member_path",
                                       "source_variable", "survey_wave", "canonical_name"))


def resolve_mappings(connection, rows: list[dict], spec: dict) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[mapping_key(row)].append(row)
    require(len(groups) == spec["expected_counts"]["variable_mappings"], "Expected 21 effective source rules")
    require(connection.execute("SELECT count(*) AS n FROM cses_alignment.cses_value_mapping").fetchone()["n"] == 0,
            "Value mappings already exist; replan against that release")
    require(not connection.execute("SELECT 1 FROM cses_meta.cses_alignment_release WHERE mapping_version=%s",
                                   (spec["release_id"],)).fetchone(), "Release already exists")
    mappings = []
    for key, group in sorted(groups.items()):
        versions = {r["effective_mapping_version"] for r in group}
        require(len(versions) == 1, "Ambiguous effective source version")
        observed = connection.execute("""
            SELECT m.variable_mapping_id, m.dataset_id, m.canonical_variable_id, m.source_variable_names,
                   m.source_kind, m.transformation_rule, m.alignment_status, r.mapping_version, r.status,
                   v.variable_label, v.value_labels
            FROM cses_alignment.cses_variable_mapping m
            JOIN cses_meta.cses_alignment_release r USING(alignment_release_id)
            JOIN cses_alignment.cses_canonical_variable c USING(canonical_variable_id)
            JOIN cses_meta.cses_dataset d USING(dataset_id)
            JOIN cses_meta.cses_survey s ON s.survey_id=d.survey_id
            JOIN cses_meta.cses_source_archive a USING(source_archive_id)
            JOIN cses_alignment.cses_source_variable v ON v.dataset_id=d.dataset_id AND v.variable_name=%s
            WHERE a.relative_path=%s AND d.member_path=%s AND coalesce(d.nested_member_path,'')=%s
              AND s.survey_wave=%s AND c.canonical_name=%s AND c.target_table='final_HO_CSES'
              AND r.mapping_version=%s
        """, (key[3], key[0], key[1], key[2], key[4], key[5], next(iter(versions)))).fetchall()
        require(len(observed) == 1, f"Effective source mapping is not unique: {key}")
        previous = observed[0]
        require(previous["status"] == "approved" and previous["source_variable_names"] == [key[3]],
                "Effective mapping release or source field differs")
        require(len({r["source_code"] for r in group}) == len(group), "Duplicate mapping/source-value pair")
        values = []
        for row in group:
            label = (previous["value_labels"] or {}).get(row["source_code"])
            require(label == row["source_label"], "Database source label differs from approved evidence")
            values.append({"source_value": row["source_code"], "source_label": row["source_label"],
                           "canonical_value": row["approved_canonical_value"],
                           "canonical_label": row["approved_canonical_label"], "alignment_status": "approved",
                           "review_row_id": row["review_row_id"]})
        # Labels derived from questionnaire options remain in the evidence, not misrepresented as Stata labels.
        mappings.append({"source_key": dict(zip(("archive_relative_path", "member_path", "nested_member_path",
                        "source_variable", "survey_wave", "canonical_name"), key, strict=True)),
                         "previous_mapping": previous, "planned_mapping": {
                             "dataset_id": previous["dataset_id"], "canonical_variable_id": previous["canonical_variable_id"],
                             "mapping_version": spec["release_id"], "source_variable_names": previous["source_variable_names"],
                             "source_kind": previous["source_kind"], "transformation_rule": previous["transformation_rule"],
                             "alignment_status": "approved"}, "value_mappings": values})
    return mappings


def database_plan(root: Path, spec: dict, context: dict, evidence: dict, rows: list[dict]) -> dict:
    correction = evidence["correction_spec"]
    with connect_database({"dbname": spec["database"]}) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL statement_timeout='55s'")
        require(connection.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on",
                "Read-only transaction required")
        require(connection.execute("SELECT current_database() AS db").fetchone()["db"] == spec["database"], "Wrong database")
        snapshot = database_snapshot(connection, correction)
        check_database_state(snapshot, evidence["correction_before"]["database"], correction, True)
        require(snapshot == evidence["correction_import"]["after_database"], "Database has drifted from approved baseline")
        verify_release_records(release_records(connection, correction), correction, evidence["correction_plan"],
                               context["review_spec"]["evidence"]["correction_plan"]["sha256"])
        compare_database_to_local(connection, correction, root / context["review_spec"]["evidence"]["current_housing"]["path"])
        mappings = resolve_mappings(connection, rows, spec)
    return {"transaction_read_only": True, "database_mutated": False, "protected_table_count": 35,
            "baseline_snapshot_sha256": canonical_sha256(snapshot), "path_comparison": PATH_COMPARISON,
            "physical_housing_matches_local": True, "planned_variable_mappings": mappings,
            "actions": {"alignment_releases": 1, "variable_mappings": len(mappings),
                        "value_mappings": sum(len(m["value_mappings"]) for m in mappings), "load_runs": 1,
                        "updates": 0, "deletes": 0, "ddl_changes": 0}}


def render(report: dict) -> str:
    rows = report["approved_rows"]
    lines = ["# CSES Housing Value Mapping v1: Approved Scope and Read-only Preflight", "",
             "The user has approved 140 category mappings: 70 prior manual-review rows and 70 candidates.",
             "Detailed verification passed. The database transaction is planned, not executed.", "",
             "## Exact scope", "", "| Wave | Field | Code | Approved value | Source label / questionnaire option |",
             "|---|---|---|---|---|"]
    for row in rows:
        labels = list(dict.fromkeys(v for v in (row["source_label"], (row["questionnaire_option"] or {}).get("label")) if v))
        values = [row["survey_wave"], row["canonical_name"], row["source_code"], row["approved_canonical_value"], " / ".join(labels)]
        lines.append("| " + " | ".join(str(v).replace("|", "\\|") for v in values) + " |")
    lines += ["", "## Interpretation", ""]
    lines += [f"- {k}: {v}" for k, v in report["interpretation_notes"].items()]
    lines += ["", "## Planned publication", "",
              "Append 1 alignment release, 21 versioned source rules, 140 value mappings and 1 load run (163 records).",
              "The planned source rules retain the effective builder transformation, including the accepted 2004 lighting",
              "correction. The semantic dictionary describes existing source codes; physical housing values and schemas",
              "remain unchanged. Preserve both source-rule and semantic-dictionary provenance for downstream consumers.",
              "", "The JSON contains the 21 resolved existing mapping identities and all intended value records, along",
              "with approval/evidence hashes, retained qualifiers, exclusions and the read-only baseline fingerprint.",
              "The 52 unresolved and 16 missing-only review rows remain outside the release.", "",
              "## Execution preparation remaining", ""]
    lines += [f"- {step}" for step in report["publication_design"]["later_execution_steps"]]
    return "\n".join(lines) + "\n"


def write_outputs(directory: Path, report: dict) -> None:
    outputs = {"plan.json": json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
               "approved_scope.md": render(report)}
    for name, value in outputs.items():
        require(not (directory / name).exists() or (directory / name).read_text() == value, "Existing release plan differs")
    directory.mkdir(parents=True, exist_ok=True)
    for name, value in outputs.items():
        if not (directory / name).exists():
            (directory / name).write_text(value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    spec, context, evidence = load_context(root)
    rows = approved_rows(spec, context)
    options = verify_questionnaire_options(root, rows, evidence["audit_spec"])
    print(f"source_checks_passed=True approved_rows={len(rows)} option_rows_checked={options}; checking database", flush=True)
    planned = database_plan(root, spec, context, evidence, rows)
    paths = set(CODE_PATHS) | {SPEC, "rsc/cses_db/plan_cses_value_mapping_release.py",
                              "rsc/cses_db/record_cses_value_mapping_decisions.py"}
    report = {"schema_version": 1, "release_id": spec["release_id"], "approval_basis": spec["approval_basis"],
              "semantic_status": "approved", "preflight_passed": True, "execution_ready": False,
              "database_mutated": False, "approved_rows": rows, "database_plan": planned,
              "questionnaire_option_rows_checked": options, "source_profiles_replayed": 30,
              "excluded_by_bucket": {"blocked": 52, "missing_only": 16},
              "interpretation_notes": spec["interpretation_notes"], "publication_design": spec["publication_design"],
              "summary": {"approved_rows": len(rows), "field_specific_categories": len({r["category_key"] for r in rows}),
                          "by_field": dict(sorted(Counter(r["canonical_name"] for r in rows).items())),
                          "by_wave": dict(sorted(Counter(r["survey_wave"] for r in rows).items())),
                          "zero_frequency_rows": sum(r["raw_count"] == 0 for r in rows)},
              "provenance": {"inputs": spec["inputs"], "spec_sha256": sha256_file(root / SPEC),
                             "implementation_sha256": {p: sha256_file(root / p) for p in sorted(paths)},
                             "base_git_revision": subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                                 capture_output=True, text=True).stdout.strip(),
                             "revision_note": "Base checkout plus file hashes identify the uncommitted preflight implementation."}}
    output = args.output_dir or root / "data/processing/cses/value_mapping_release_v1"
    write_outputs(output if output.is_absolute() else root / output, report)
    print(json.dumps({**report["summary"], "preflight_passed": True, "database_mutated": False}))


if __name__ == "__main__":
    main()
