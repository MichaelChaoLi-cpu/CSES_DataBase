#!/usr/bin/env python3
"""Flag 1999 schooling route anomalies without imputing answers."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from build_cses_additional_waves import OUTPUT as CANDIDATES
from build_cses_additional_waves import encoded, parquet_bytes, verify
from cache_cses_questionnaires import file_sha, put

OUTPUT = "data/processing/cses/education_1999_route_review_v1"


def flag_routes(frame):
    result = frame.copy()
    ever = frame["Ever Attended School"]
    current = frame["Currently Attending School"]
    grade = frame["Current Education Level Source Code"]
    highest = frame["Highest Education Level Source Code"]
    result["Route Review Status"] = "no_detected_route_anomaly"
    result.loc[ever.eq(0), "Route Review Status"] = "never_attended_skip_observed"
    result.loc[ever.eq(1) & current.isna(), "Route Review Status"] = "current_attendance_missing_after_ever_yes"
    result.loc[ever.eq(1) & current.isna() & grade.notna(), "Route Review Status"] = "current_attendance_missing_but_grade_present"
    conflict = (ever.eq(0) & (current.notna() | highest.notna() | grade.notna())) | (current.eq(0) & grade.notna())
    result.loc[conflict, "Route Review Status"] = "response_in_expected_skipped_item"
    result.loc[current.eq(1) & grade.isna(), "Route Review Status"] = "current_grade_missing_after_current_yes"
    result.loc[ever.isna(), "Route Review Status"] = "ever_attendance_missing"
    return result


def build(root):
    verify(root)
    source = root / CANDIDATES / "tables/1999/ED.parquet"
    frame = pd.read_parquet(source)
    result = flag_routes(frame)
    base = root / "data/processed/cses_questionnaires/additional_waves_v1/legacy_word_text_v1"
    manifest = json.loads((base / "manifest.json").read_text())
    name = "1999/QuestENG_Form3Page.json"
    if file_sha(base / name) != manifest["artifacts"][name]:
        raise ValueError("Questionnaire text changed")
    lines = json.loads((base / name).read_text())["lines"]
    # Preserve the entire extracted schooling section: text order alone is not a
    # new visual certification of table-column alignment.
    start = next(i for i, line in enumerate(lines) if line["text"].strip() == "II. SCHOOLING")
    end = next(i for i, line in enumerate(lines) if line["text"].strip() == "III. ECONOMIC  ACTIVITY")
    evidence = lines[start:end]
    if sum("No (>> Col.9)" in line["text"] for line in evidence) != 2:
        raise ValueError("Expected both schooling skip instructions")
    report = {"wave": "1999", "rows": len(result), "status_counts": result["Route Review Status"].value_counts().to_dict(),
              "evidence": evidence, "interpretation": "Candidate route audit; no answer imputation or whole-module certification.",
              "database_modified": False, "original_tables_modified": False}
    output = root / OUTPUT
    artifacts = {"ED_1999_route_review.parquet": put(output / "ED_1999_route_review.parquet", parquet_bytes(result)),
                 "summary.json": put(output / "summary.json", encoded(report))}
    put(output / "manifest.json", encoded({"artifacts": artifacts, "builder_sha256": file_sha(Path(__file__)),
        "source_table_sha256": file_sha(source), "questionnaire_text_sha256": file_sha(base / name)}))
    return report["status_counts"]


if __name__ == "__main__":
    print(json.dumps(build(Path(__file__).resolve().parents[2]), indent=2))
