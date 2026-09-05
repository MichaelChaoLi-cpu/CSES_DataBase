#!/usr/bin/env python3
"""Materialize exact user-approved value decisions without publishing them."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

from cses_baseline_metadata import canonical_sha256, sha256_file

SPEC = "rsc/specs/cses_value_mapping_manual_decisions_v1.json"
CODE_PATHS = (SPEC, "rsc/cses_db/record_cses_value_mapping_decisions.py", "pyproject.toml", "uv.lock")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_review(root: Path, spec: dict) -> dict:
    descriptor = spec["source_review"]
    path = root / descriptor["path"]
    require(sha256_file(path) == descriptor["sha256"], "Source review fingerprint changed")
    review = json.loads(path.read_text())
    require(review["technical_checks_passed"] is True, "Source review checks did not pass")
    require(review["database_mutated"] is False, "Source review unexpectedly mutated the database")
    require(review["publication_ready"] is False, "Source review must remain non-publishable")
    require(review["summary"]["review_bucket_code_rows"]["manual_review"] == spec["selection"]["expected_rows"],
            "Source review manual-review count changed")
    return review


def build_decisions(review: dict, spec: dict) -> dict:
    selector = spec["selection"]
    selected = [row for row in review["code_rows"] if row[selector["field"]] == selector["value"]]
    require(len(selected) == selector["expected_rows"], "Approved selection does not contain exactly 70 rows")
    require(len({row["review_row_id"] for row in selected}) == len(selected), "Approved row identities are not unique")
    labels = spec["canonical_labels"]
    decisions = []
    for row in selected:
        value = row["candidate_category"]
        require(value in labels, f"Approved category has no canonical label: {value}")
        require(row["review_status"] == "proposed" and row["publication_ready"] is False,
                "Source review status changed")
        require(row["review_reasons"], "Manual-review row has no retained qualification")
        decisions.append({
            "review_row_id": row["review_row_id"],
            "source_key": row["source_key"],
            "effective_mapping_version": row["effective_mapping_version"],
            "source_label": row["source_label"],
            "questionnaire_option": row["questionnaire_option"],
            "raw_count": row["raw_count"],
            "current_published_code_count": row["current_published_code_count"],
            "approved_canonical_value": value,
            "approved_canonical_label": labels[value],
            "category_key": row["category_key"],
            "retained_qualifications": row["review_reasons"],
            "historical_flags": row["historical_flags"],
            "decision_status": "approved",
            "publication_ready": False,
        })
    decisions.sort(key=lambda row: (row["source_key"]["survey_wave"], row["source_key"]["canonical_name"],
                                    row["source_key"]["code_kind"], row["source_key"]["source_code"]))
    selected_ids = {row["review_row_id"] for row in decisions}
    remaining = [row for row in review["code_rows"] if row["review_row_id"] not in selected_ids]
    remaining_counts = Counter(row["review_bucket"] for row in remaining)
    qualification_counts = Counter(reason for row in decisions for reason in row["retained_qualifications"])
    return {
        "schema_version": 1,
        "decision_id": spec["decision_id"],
        "decision_date": spec["decision_date"],
        "decision_status": spec["status"],
        "approval_basis": spec["approval_basis"],
        "database_write_allowed": False,
        "database_mutated": False,
        "publication_ready": False,
        "qualifications": spec["qualifications"],
        "approved_decisions": decisions,
        "summary": {
            "approved_rows": len(decisions),
            "approved_distinct_categories": len({row["category_key"] for row in decisions}),
            "approved_by_field": dict(sorted(Counter(
                row["source_key"]["canonical_name"] for row in decisions).items())),
            "approved_by_wave": dict(sorted(Counter(row["source_key"]["survey_wave"] for row in decisions).items())),
            "retained_qualification_counts": dict(sorted(qualification_counts.items())),
            "remaining_review_rows": len(remaining),
            "remaining_by_bucket": dict(sorted(remaining_counts.items())),
        },
        "source_review": spec["source_review"],
        "source_review_database_snapshot_sha256": review["database_validation"]["snapshot_sha256"],
        "source_review_row_id_set_sha256": canonical_sha256(sorted(selected_ids)),
    }


def markdown(record: dict) -> str:
    summary = record["summary"]
    lines = [
        "# CSES Housing Manual-Review Decisions v1",
        "",
        "The user approved the exact proposed categories for all 70 rows previously classified as manual review.",
        "This is a semantic decision record, not database-write authorization or a completed value-mapping release.",
        "",
        "## Decision boundary",
        "",
        f"Approved rows: {summary['approved_rows']}; field-specific categories: "
        f"{summary['approved_distinct_categories']}; publication-ready rows: 0.",
        "Draft provenance, skip-routing limitations, residual/compound qualifications, wave-specific source codes,",
        "and original evidence status are retained. Composite categories are not collapsed.",
        "",
        "The separate candidate bucket (70 rows), blocked bucket (52 rows), and missing-only bucket (16 rows)",
        "remain unchanged. A future import requires an explicit selected release scope and reviewed transaction plan.",
        "",
        "## Approved rows",
        "",
        "| Wave | Field | Code | Approved value | Label | Current n | Retained qualifications |",
        "|---|---|---|---|---|---:|---|",
    ]
    for row in record["approved_decisions"]:
        key = row["source_key"]
        values = [key["survey_wave"], key["canonical_name"], key["source_code"],
                  row["approved_canonical_value"], row["approved_canonical_label"],
                  row["current_published_code_count"], ", ".join(row["retained_qualifications"])]
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in values) + " |")
    lines += [
        "",
        "## Reproducibility",
        "",
        "The companion JSON pins the source review hash, all 70 review-row identities, exact source keys,",
        "approved values, original labels/options, current frequencies, and retained qualifications.",
        "Differing existing output files are never overwritten. No database connection or mutation is used.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(directory: Path, record: dict) -> None:
    outputs = {
        "decisions.json": json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        "decisions.md": markdown(record),
    }
    for name, content in outputs.items():
        path = directory / name
        require(not path.exists() or path.read_text() == content, f"Existing decision evidence differs: {path}")
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
    require(spec["database_write_allowed"] is False and spec["publication_ready"] is False,
            "Decision recorder cannot authorize publication")
    record = build_decisions(load_review(root, spec), spec)
    record["provenance"] = {
        "spec_sha256": sha256_file(root / SPEC),
        "code_files_sha256": {path: sha256_file(root / path) for path in CODE_PATHS},
        "code_git_revision": subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                                            capture_output=True, text=True).stdout.strip(),
        "code_revision_note": "HEAD is the base checkout; file hashes identify the uncommitted decision recorder.",
    }
    output = args.output_dir or root / "data/processing/cses/value_mapping_manual_decisions_v1"
    if not output.is_absolute():
        output = root / output
    write_outputs(output, record)
    print(json.dumps({**record["summary"], "database_mutated": False, "publication_ready": False}, sort_keys=True))


if __name__ == "__main__":
    main()
