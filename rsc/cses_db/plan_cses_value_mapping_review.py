#!/usr/bin/env python3
"""Build a non-publishable housing value review against the corrected release, read-only."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
from collections import Counter
from pathlib import Path

import pandas as pd
from correct_cses_housing_lighting import (
    IMPLEMENTATION,
    PATH_COMPARISON,
    check_database_state,
    compare_database_to_local,
    compare_local,
    database_snapshot,
    release_records,
    require,
    verify_release_records,
)
from cses_baseline_metadata import canonical_sha256, connect_database, sha256_file
from inventory_cses_archives import DataSource
from plan_cses_value_audit import DATASET_KEY, code_identity, dataset_key, frequencies, reconcile_value

SPEC = "rsc/specs/cses_value_mapping_review_v1.json"
BUCKETS = ("candidate", "manual_review", "blocked", "missing_only")
CODE_PATHS = tuple(sorted(set(IMPLEMENTATION) | {
    SPEC, "rsc/cses_db/plan_cses_value_mapping_review.py", "rsc/cses_db/plan_cses_value_audit.py",
    "rsc/cses_db/cses_questionnaire_provenance.py", "rsc/cses_db/cses_variable_catalog.py",
    "rsc/cses_db/cses_schema_contract.py",
}))


def load_inputs(root: Path, spec: dict) -> dict:
    require(spec["database_write_allowed"] is False and spec["status"] == "proposed", "Review-only scope required")
    evidence = {}
    for name, descriptor in spec["evidence"].items():
        path = root / descriptor["path"]
        require(sha256_file(path) == descriptor["sha256"], f"Evidence fingerprint changed: {name}")
        if path.suffix == ".json":
            evidence[name] = json.loads(path.read_text())
    audit = evidence["audit"]
    require(audit["technical_checks_passed"] and not audit["publication_ready"], "Historical audit is not valid")
    require(len(audit["profiles"]) == 30 and len(audit["code_rows"]) == 208, "Unexpected pilot scope")
    require(evidence["correction_validation"]["validation_passed"], "Correction was not validated")
    require(evidence["correction_import"]["plan_sha256"] == spec["evidence"]["correction_plan"]["sha256"],
            "Correction import/plan mismatch")
    # Preserve the implementation gate for the already applied correction.
    for path, digest in evidence["correction_plan"]["implementation_sha256"].items():
        require(sha256_file(root / path) == digest, f"Correction implementation changed: {path}")
    return evidence


def verify_raw_profiles(root: Path, audit: dict) -> None:
    for path, digest in audit["archive_fingerprints"].items():
        require(sha256_file(root / path) == digest, f"Raw archive changed: {path}")
    cache = {}
    for profile in audit["profiles"]:
        key = dataset_key(profile)
        if key not in cache:
            payload = DataSource(root / key[0], tuple(p for p in key[1:] if p)).read_bytes()
            names = [p["source_variable"] for p in audit["profiles"] if dataset_key(p) == key]
            with pd.io.stata.StataReader(io.BytesIO(payload), convert_categoricals=False,
                                        convert_missing=True) as reader:
                label_sets = reader.value_labels()
                assigned = dict(zip(reader._varlist, reader._lbllist, strict=True))
                labels = {name: {code_identity(k)[1]: str(v) for k, v in
                          label_sets.get(assigned[name], {}).items()} or None for name in names}
                frame = reader.read(columns=names)
            cache[key] = (frame, labels, hashlib.sha256(payload).hexdigest())
        frame, labels, member_hash = cache[key]
        expected = {(r["code_kind"], r["source_code"]): r["raw_count"] for r in audit["code_rows"]
                    if r["profile_id"] == profile["profile_id"] and r["raw_count"]}
        require(member_hash == profile["member_sha256"], "Source member changed")
        require(len(frame) == profile["raw_row_count"], "Source row count changed")
        require(labels[profile["source_variable"]] == profile["source_value_labels"], "Source labels changed")
        require(frequencies(frame[profile["source_variable"]]) == expected, "Source frequencies changed")


def triage(row: dict, spec: dict) -> tuple[str, list[str]]:
    flags = set(row["flags"])
    if row["missing_class"] == "unresolved" or "source_label_option_conflict" in flags:
        return "blocked", sorted(flags | {"meaning_unresolved"})
    if row["missing_class"] != "substantive":
        return "missing_only", ["source_missing_evidence_not_a_substantive_category"]
    require(row["candidate_category"] is not None, "Substantive row needs a candidate label")
    reasons = sorted(flags & set(spec["manual_review_flags"]))
    return ("manual_review", reasons) if reasons else ("candidate", ["documented_label_interpretation_only"])


def build_review(root: Path, spec: dict, evidence: dict) -> dict:
    audit, correction = evidence["audit"], evidence["correction_spec"]
    verify_raw_profiles(root, audit)
    before = pd.read_parquet(root / spec["evidence"]["before_housing"]["path"])
    current = pd.read_parquet(root / spec["evidence"]["current_housing"]["path"])
    difference = compare_local(before, current, correction)
    variables = {v["canonical_name"]: v["local_column"] for v in evidence["audit_spec"]["variables"]}
    profiles, rows, identities = [], [], set()
    for profile in audit["profiles"]:
        selected = current.loc[current["Survey Wave"].eq(profile["survey_wave"]), variables[profile["canonical_name"]]]
        counts = frequencies(selected)
        baseline_counts = {(r["code_kind"], r["source_code"]): r["count"]
                           for r in profile["local_published_frequencies"]}
        original = before.loc[before["Survey Wave"].eq(profile["survey_wave"]), variables[profile["canonical_name"]]]
        require(frequencies(original) == baseline_counts, "Historical profile does not match retained before image")
        mapping_version = (correction["release_id"] if (profile["survey_wave"], profile["canonical_name"]) ==
                           (correction["survey_wave"], correction["column"]) else profile["mapping_version"])
        group = []
        for source in audit["code_rows"]:
            if source["profile_id"] != profile["profile_id"]:
                continue
            question = profile["questionnaire"]
            decision = reconcile_value(source["source_code"], source["code_kind"], source["source_label"],
                                       source["questionnaire_option"],
                                       bool(question and question["documentation_status"] == "provisional"),
                                       evidence["audit_spec"])
            require(all(source[k] == decision[k] for k in ("candidate_category", "missing_class")),
                    "Historical semantic interpretation differs from pinned aliases")
            bucket, reasons = triage(source, spec)
            natural_key = {**{f: profile[f] for f in DATASET_KEY}, "source_variable": source["source_variable"],
                           "survey_wave": source["survey_wave"], "canonical_name": source["canonical_name"],
                           "code_kind": source["code_kind"], "source_code": source["source_code"]}
            identity = canonical_sha256(natural_key)
            require(identity not in identities, "Duplicate review identity")
            identities.add(identity)
            numeric = source["code_kind"] == "numeric"
            published = counts.get(("numeric", source["source_code"]), 0) if numeric else None
            resolution = None
            if (source["survey_wave"], source["canonical_name"], source["source_code"], numeric) == (
                    correction["survey_wave"], correction["column"], str(correction["old_value"]), True):
                require(published == 0, "Documented lighting sentinel remains published")
                resolution = {"release_id": correction["release_id"], "status": "corrected_to_null",
                              "before_code_count": source["local_published_code_count"], "after_code_count": 0}
            row = {**source, "review_row_id": identity, "source_key": natural_key, "review_bucket": bucket,
                   "review_reasons": reasons, "baseline_published_code_count": source["local_published_code_count"],
                   "current_published_code_count": published, "effective_mapping_version": mapping_version,
                   "category_key": f"{source['canonical_name']}:{source['candidate_category']}"
                                   if source["candidate_category"] is not None else None,
                   "review_status": "proposed", "publication_ready": False, "correction_resolution": resolution,
                   "evidence": {"archive_sha256": audit["archive_fingerprints"][profile["archive_relative_path"]],
                                "member_sha256": profile["member_sha256"], "questionnaire": question}}
            # Keep historical flags explicitly historical rather than presenting a resolved issue as current.
            row["historical_flags"] = row.pop("flags")
            row.pop("local_published_code_count")
            rows.append(row)
            group.append(row)
        allocated = sum(r["current_published_code_count"] or 0 for r in group)
        require(allocated + counts.get(("system_missing", "NULL"), 0) == len(selected),
                "Current profile has unaccounted codes")
        bucket_counts = dict(Counter(r["review_bucket"] for r in group))
        coverage = {b: sum(r["current_published_code_count"] or 0 for r in group if r["review_bucket"] == b)
                    for b in BUCKETS}
        profiles.append({**profile, "effective_mapping_version": mapping_version,
                         "current_published_row_count": len(selected), "review_bucket_code_rows": bucket_counts,
                         "current_numeric_counts_by_bucket": coverage,
                         "current_sql_null_count": counts.get(("system_missing", "NULL"), 0),
                         "current_published_frequencies": [{"code_kind": k, "source_code": c, "count": n}
                                                           for (k, c), n in sorted(counts.items())]})
    return {"schema_version": 1, "review_id": spec["review_id"], "review_status": "proposed",
            "publication_ready": False, "database_mutated": False, "policies": spec["policies"],
            "local_correction_check": difference, "profiles": profiles, "code_rows": rows,
            "cross_wave_conflicts": audit["cross_wave_conflicts"],
            "questionnaire_coverage_gaps": audit["questionnaire_coverage_gaps"],
            "summary": {"profiles": len(profiles), "code_rows": len(rows),
                        "review_bucket_code_rows": dict(sorted(Counter(r["review_bucket"] for r in rows).items())),
                        "resolved_correction_code_rows": sum(r["correction_resolution"] is not None for r in rows),
                        "publishable_rows": 0}}


def verify_database(root: Path, spec: dict, evidence: dict) -> dict:
    correction = evidence["correction_spec"]
    with connect_database({"dbname": spec["database"]}) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL statement_timeout='55s'")
        require(connection.execute("SELECT current_database() AS name").fetchone()["name"] == spec["database"],
                "Unexpected database")
        read_only = connection.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on"
        require(read_only, "Read-only transaction required")
        snapshot = database_snapshot(connection, correction)
        check_database_state(snapshot, evidence["correction_before"]["database"], correction, True)
        require(snapshot == evidence["correction_import"]["after_database"], "Database changed after correction")
        verify_release_records(release_records(connection, correction), correction, evidence["correction_plan"],
                               spec["evidence"]["correction_plan"]["sha256"])
        compare_database_to_local(connection, correction, root / spec["evidence"]["current_housing"]["path"])
    return {"database": spec["database"], "transaction_read_only": read_only, "isolation_level": "repeatable read",
            "database_mutated": False, "validation_passed": True,
            "protected_table_count": len(snapshot["protected_relations"]),
            "snapshot_sha256": canonical_sha256(snapshot), "full_housing_matches_local": True,
            "path_comparison": PATH_COMPARISON, "canonical_value_mapping_count": 0}


def markdown(report: dict) -> str:
    def cell(value):
        return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")

    lines = ["# CSES Housing Value Mapping Review v1", "", "Proposed review only; no category is approved or imported.",
             "Candidates express documented labels, not proven full cross-wave comparability.", "",
             "Counts are unweighted records per wave/field, never population estimates. SQL NULL reasons are not inferred.",
             "The pinned historical audit remains unchanged; current counts include the separately approved lighting correction.",
             "", "## Review queue", "", "| Bucket | Code rows |", "|---|---:|"]
    for bucket, count in report["summary"]["review_bucket_code_rows"].items():
        lines.append(f"| {bucket} | {count} |")
    lines += ["", "## Policy", ""]
    lines += [f"- {key}: {value}" for key, value in report["policies"].items()]
    lines += ["", "## Current published coverage", "",
              "Candidate/manual/blocked columns count numeric observations; missing-only evidence is not a category.",
              "NULL totals can include undocumented numeric codes already excluded by historical builders.", "",
              "| Wave / field | Total | Candidate | Manual | Blocked | Missing-only numeric | SQL NULL |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for p in report["profiles"]:
        counts = p["current_numeric_counts_by_bucket"]
        lines.append(f"| {p['profile_id']} | {p['current_published_row_count']} | " +
                     " | ".join(str(counts[b]) for b in BUCKETS) + f" | {p['current_sql_null_count']} |")
    lines += ["", "## Priority decisions", "",
              "- 2021 tenure code 0: one raw observation, zero published numeric occurrences; meaning remains unresolved.",
              "- 2021 lighting code 8: retain the untranslated source label; obtain authoritative bilingual evidence.",
              "- 2007/2013/2017: do not infer unlabeled codes from neighboring waves.",
              "- 2014 draft, residual Other, compound categories and skip instructions remain manual-review items.",
              "- 2004 lighting code 9 is resolved by the separate correction, not by this proposed category review.",
              "", "## Complete review by wave and field", ""]
    for p in report["profiles"]:
        lines += [f"### {p['profile_id']}", "", f"Source: `{p['archive_relative_path']}::{p['member_path']}"
                  f"{'::' + p['nested_member_path'] if p['nested_member_path'] else ''}`; `{p['source_variable']}`.",
                  f"Effective source rule: `{p['effective_mapping_version']}`.", "",
                  "| Code / kind | Raw n | Baseline n | Current n | Label / option | Category | Bucket | Reasons |",
                  "|---|---:|---:|---:|---|---|---|---|"]
        for r in report["code_rows"]:
            if r["profile_id"] != p["profile_id"]:
                continue
            option = r["questionnaire_option"]
            label = r["source_label"] or (option["label"] if option else None)
            if option:
                label = f"{label}; option: {option['label']} ({option['source_cell']})"
            values = [f"{r['source_code']} / {r['code_kind']}", r["raw_count"], r["baseline_published_code_count"],
                      r["current_published_code_count"], label, r["candidate_category"], r["review_bucket"],
                      ", ".join(r["review_reasons"])]
            lines.append("| " + " | ".join(cell(v) for v in values) + " |")
        lines.append("")
    lines += ["## Validation and reproducibility", "", "All ten raw datasets were re-read and matched the pinned audit.",
              "All-cell local before/after comparison permits only the accepted lighting correction. A fresh read-only",
              "database check verified 35 protected tables, correction provenance, and full housing-table equality",
              "after the documented comparison-only archive-path normalization. No database writes were performed.",
              "The companion JSON retains all hashes, exact source keys, questionnaire locations, original flags,",
              "cross-wave conflicts, and publication_ready=false on every row.", ""]
    return "\n".join(lines)


def overview(report: dict) -> str:
    counts = report["summary"]["review_bucket_code_rows"]
    lines = ['flowchart LR', '    AUDIT["Immutable value audit v1<br/>208 code rows"]',
             '    CORRECTION["Accepted one-cell lighting correction"]',
             '    CURRENT["Current local table and mda<br/>read-only validation"]',
             '    REVIEW["Proposed value review<br/>no database write"]',
             '    AUDIT --> REVIEW', '    CORRECTION --> REVIEW', '    CURRENT -.-> REVIEW']
    for bucket in BUCKETS:
        lines += [f'    {bucket}["{bucket}<br/>{counts.get(bucket, 0)} code rows"]', f'    REVIEW --> {bucket}']
    return "\n".join(lines) + "\n"


def write_outputs(directory: Path, report: dict) -> None:
    outputs = {"review.json": json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
               "review.md": markdown(report), "overview.mmd": overview(report)}
    # Check all targets before writing any: a new result requires a new output directory.
    for name, content in outputs.items():
        path = directory / name
        require(not path.exists() or path.read_text() == content, f"Existing review differs: {path}")
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        path = directory / name
        if not path.exists():
            path.write_text(content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    spec = json.loads((root / SPEC).read_text())
    evidence = load_inputs(root, spec)
    report = build_review(root, spec, evidence)
    print("local_checks_passed=True profiles=30 code_rows=208; checking database read-only", flush=True)
    report["database_validation"] = verify_database(root, spec, evidence)
    report["technical_checks_passed"] = True
    report["provenance"] = {"evidence": spec["evidence"], "source_data_dvc_revision": spec["source_data_dvc_revision"],
                            "spec_sha256": sha256_file(root / SPEC),
                            "code_files_sha256": {p: sha256_file(root / p) for p in CODE_PATHS},
                            "code_git_revision": subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                                check=True, capture_output=True, text=True).stdout.strip(),
                            "code_revision_note": "HEAD is the base checkout; file hashes identify review implementation, including uncommitted changes."}
    output = args.output_dir or root / "data/processing/cses/value_mapping_review_v1"
    if not output.is_absolute():
        output = root / output
    write_outputs(output, report)
    print(json.dumps({**report["summary"], "database_mutated": False, "publication_ready": False}, sort_keys=True))


if __name__ == "__main__":
    main()
