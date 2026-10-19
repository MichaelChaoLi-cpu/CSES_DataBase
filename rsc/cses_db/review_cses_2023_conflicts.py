#!/usr/bin/env python3
"""Additive 2023 conflict review and conservative local projections; no publication."""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

import pandas as pd
from build_cses_additional_waves import OUTPUT as CANDIDATES
from build_cses_additional_waves import compare_variants, encoded, parquet_bytes, scalar, verify
from build_cses_health import read_stata
from cache_cses_questionnaires import file_sha, put, safe_path

OUTPUT = "data/processing/cses/additional_wave_review_v1"
KEYS = ["hhid", "persid"]


def classify_duplicate_groups(raw, special):
    """Fold only one strictly subsumed question row, with identical context.

    Every non-null answer in the subsumed row must be present and identical in
    the selected row. Contradictory, complementary, tied and special-missing
    cases remain unresolved. A higher answer count alone is not sufficient.
    """
    if raw[KEYS].isna().any().any():
        raise ValueError("Missing source keys")
    questions = [c for c in raw if c.startswith("q15_")]
    if not questions:
        raise ValueError("No recognized employment question columns")
    context = [c for c in raw if c not in questions]
    special_rows = {r["source_row_number"] for r in special}
    decisions = []
    duplicate = raw.duplicated(KEYS, keep=False)
    for key, group in raw.loc[duplicate].groupby(KEYS, sort=True, dropna=False):
        rows = [int(i) + 1 for i in group.index]
        blank = group[questions].isna().all(axis=1)
        context_agrees = all(group[c].nunique(dropna=False) == 1 for c in context)
        selected = None
        if len(group) == 2 and context_agrees and not special_rows.intersection(rows):
            for index in group.index:
                rich = group.loc[index, questions]
                sparse = group.loc[group.index[group.index != index][0], questions]
                present = sparse.notna()
                if rich.notna().sum() > present.sum() and rich[present].eq(sparse[present]).all():
                    selected = int(index) + 1
        allowed = selected is not None
        decisions.append({"key": [scalar(v) for v in key], "source_rows": rows,
                          "question_columns_checked": questions, "context_columns_checked": context,
                          "context_agrees": context_agrees, "special_missing_present": bool(special_rows.intersection(rows)),
                          "blank_question_rows": [int(i) + 1 for i in group.index[blank]],
                          "selected_source_row": selected,
                          "status": ("blank_placeholder_fold_candidate" if blank.sum() == 1
                                     else "strict_answer_subset_fold_candidate") if allowed else "unresolved",
                          "differing_columns": [c for c in raw if group[c].nunique(dropna=False) > 1]})
    return decisions


def fold_projection(candidate, decisions):
    if candidate["Source Row Number"].duplicated().any():
        raise ValueError("Source row numbers must be unique")
    result = candidate.copy()
    result["All Source Row Numbers"] = result["Source Row Number"].map(lambda n: json.dumps([int(n)]))
    result["Resolution Status"] = "unique_source_record"
    result.loc[result["Duplicate Key"], "Resolution Status"] = "unresolved_duplicate"
    omitted = set()
    for decision in decisions:
        if decision["status"] not in {"blank_placeholder_fold_candidate", "strict_answer_subset_fold_candidate"}:
            continue
        selected = decision["selected_source_row"]
        mask = result["Source Row Number"].eq(selected)
        if mask.sum() != 1:
            raise ValueError("Selected source row missing from candidate")
        result.loc[mask, "All Source Row Numbers"] = json.dumps(decision["source_rows"])
        result.loc[mask, "Resolution Status"] = decision["status"]
        omitted.update(set(decision["source_rows"]) - {selected})
    result = result.loc[~result["Source Row Number"].isin(omitted)].copy()
    # Historical Duplicate Key / Unique Source Record Eligible are never rewritten.
    result["Qualified Unique Record Eligible"] = (~result["Record Key"].duplicated(keep=False)
                                                  & result["Record Key"].notna()
                                                  & ~result["Source Variant Conflict"])
    return result.reset_index(drop=True)


def qualified_provider(series, dictionary):
    unknown_codes = {r["source_value"] for r in dictionary
                     if r["label"].strip().lower() in {"don't know", "dont know", "unknown"}}
    if not unknown_codes:
        raise ValueError("Provider dictionary lacks explicit unknown category")
    return series.mask(series.isin(unknown_codes)), series.isin(unknown_codes)


def build(root):
    root = root.resolve()
    verify(root)
    spec = json.loads((root / "rsc/specs/cses_additional_waves_v1.json").read_text())
    config = spec["waves"]["2023"]
    archive_path = safe_path(root, config["archive"])
    if file_sha(archive_path) != config["sha256"]:
        raise ValueError("2023 archive changed")
    output = root / OUTPUT
    artifacts = {}

    def save(name, payload):
        if not isinstance(payload, bytes):
            payload = encoded(payload)
        artifacts[name] = put(safe_path(output, name), payload)

    with zipfile.ZipFile(archive_path) as archive:
        ec_raw, _, ec_special = read_stata(archive.read("S15_PersonEcoCurrent.dta"))
        primary, pm, _ = read_stata(archive.read("S13_PersonIllness.dta"))
        alternate, am, _ = read_stata(archive.read("S13A_PersonIllness.dta"))
    decisions = classify_duplicate_groups(ec_raw, ec_special)
    ec_candidate = pd.read_parquet(root / CANDIDATES / "tables/2023/EC.parquet")
    ec_projection = fold_projection(ec_candidate, decisions)
    if not ec_projection["Qualified Unique Record Eligible"].all():
        raise ValueError("Unresolved keys remain: do not emit a unique-person projection")
    report = compare_variants(primary, alternate, KEYS)
    primary_meta = {m["variable_name"]: m for m in pm}
    alternate_meta = {m["variable_name"]: m for m in am}
    for column in ["q13bc06", "q13bc09a"]:
        if primary_meta[column]["value_labels"] != alternate_meta[column]["value_labels"]:
            raise ValueError("Variant dictionaries differ; separate dictionary review needed")
    provider_dict = primary_meta["q13bc09a"]["value_labels"]
    dictionary = {r["source_value"]: r["label"] for r in provider_dict}
    for row in report["differences"]:
        if row["variable"] == "q13bc06" and row["primary"] == 0 and row["alternate"] is None:
            row["interpretation"] = "both_versions_produce_missing_after_dictionary_validation"
        elif row["variable"] == "q13bc09a":
            row["primary_label"] = dictionary.get(row["primary"])
            row["alternate_label"] = dictionary.get(row["alternate"])
            row["interpretation"] = "unresolved_semantic_change_do_not_promote_unknown_to_other"
        else:
            raise ValueError("Unexpected new variant difference")
    health = pd.read_parquet(root / CANDIDATES / "tables/2023/HEALTH.parquet")
    raw_keys = primary[KEYS].reset_index(drop=True)
    if not raw_keys.equals(health[["source__hhid", "source__persid"]].rename(
            columns={"source__hhid": "hhid", "source__persid": "persid"})):
        raise ValueError("Health candidate/source order mismatch")
    alt = primary[KEYS].merge(alternate[KEYS + ["q13bc06", "q13bc09a"]], on=KEYS,
                              validate="one_to_one", how="left", indicator=True)
    if not alt["_merge"].eq("both").all():
        raise ValueError("Health variant key coverage mismatch")
    health["Alternate Treatment Source Response"] = alt.q13bc06
    health["Alternate First Provider Source Code"] = alt.q13bc09a
    health["First Provider Qualified Source Code"], unknown = qualified_provider(primary.q13bc09a, provider_dict)
    health["First Provider Evidence Status"] = "primary_native_code_not_harmonized"
    health.loc[primary.q13bc09a.isna(), "First Provider Evidence Status"] = "missing"
    health.loc[unknown, "First Provider Evidence Status"] = "dictionary_unknown_with_unresolved_version_change"
    health["Treatment Interpretation"] = "primary_dictionary_qualified"
    health.loc[primary.q13bc06.eq(0), "Treatment Interpretation"] = "invalid_zero_and_alternate_null_agree_on_missing"
    save("employment_duplicate_review.json", decisions)
    save("health_version_review.json", {**report, "provider_dictionary": provider_dict})
    save("EC_2023_unique_candidate.parquet", parquet_bytes(ec_projection))
    save("HEALTH_2023_qualified_candidate.parquet", parquet_bytes(health))
    summary = {"state": "local_review_candidates_not_published", "employment_source_rows": len(ec_candidate),
               "employment_unique_candidate_rows": len(ec_projection), "duplicate_groups": len(decisions),
               "subsumed_rows_represented_via_provenance": len(ec_candidate) - len(ec_projection),
               "blank_placeholder_groups": sum(d["status"] == "blank_placeholder_fold_candidate" for d in decisions),
               "strict_answer_subset_groups": sum(d["status"] == "strict_answer_subset_fold_candidate" for d in decisions),
               "employment_groups_resolved_structurally": sum(d["status"] != "unresolved"
                                                             for d in decisions),
               "health_rows": len(health), "health_unknown_provider_rows": int(unknown.sum()),
               "health_version_differences": len(report["differences"]),
               "health_treatment_interpretation_equivalent_rows": int(primary.q13bc06.eq(0).sum()),
               "raw_data_modified": False, "previous_candidates_modified": False, "database_modified": False}
    save("summary.json", summary)
    manifest = {"artifacts": artifacts, "reviewer_sha256": file_sha(Path(__file__)),
                "candidate_manifest_sha256": file_sha(root / CANDIDATES / "manifest.json"),
                "source_archive_sha256": config["sha256"]}
    put(output / "manifest.json", encoded(manifest))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    print(json.dumps(build(parser.parse_args().root), indent=2))
