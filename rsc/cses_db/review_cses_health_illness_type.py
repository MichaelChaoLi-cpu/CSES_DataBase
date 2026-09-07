#!/usr/bin/env python3
"""Review illness-type families using extracted caches; never publish or alter source data."""

from __future__ import annotations

import argparse
import io
import json
import re
from pathlib import Path

import pandas as pd
from build_cses_health import ROW_NUMBER, load_source
from cache_cses_questionnaires import add_artifact, file_sha, put, require, verify_manifest
from plan_cses_health_illness import HEALTH, QUESTIONNAIRES, raw_json_records, source_keys
from review_cses_health_recent_illness import OUTPUT as SCREENING

SPEC = "rsc/specs/cses_health_illness_type_v1.json"
OUTPUT = "data/processing/cses/health_illness_type_v1"


def parse_options(text):
    """Literal numbered option lists, including the flattened 2021 workbook cell."""
    pairs = re.findall(r"(?:^|\s)(\d{1,2})\s*=\s*(.*?)(?=\s+\d{1,2}\s*=|$)", text, re.S)
    result = {int(k): " ".join(v.split()) for k, v in pairs}
    require(len(result) == len(pairs) and bool(result), "Empty/duplicate option numbers")
    return result


def type_evidence(root, previous, rule, spec):
    proof = previous["questionnaire"]
    if proof is None:
        return None, {}
    form = proof["form"]
    cells = json.loads((root / QUESTIONNAIRES / form["cells_path"]).read_text())["sheets"][proof["sheet"]]
    selected = {k: cells[k] for k in rule["option_cells"] + rule["context_cells"]}
    options = parse_options("\n".join(cells[k] for k in rule["option_cells"])) if rule["option_cells"] else {}
    family = rule["family"]
    if family == "early_28day_41":
        require(set(options) == set(range(1, 42)), "2004 option domain changed")
        require("most important" in cells["AG15"], "Early selection rule changed")
    elif family == "five_symptom_categories":
        normalized = {k: v.replace("Diarrhoea", "Diarrhea") for k, v in options.items()}
        require(
            normalized == {1: "Fever", 2: "Cough", 3: "Diarrhea", 4: "Flu", 5: "Other (specify)"},
            "Five-category list changed",
        )
    elif family in {"detailed_19", "core18_plus_unresolved_extensions"}:
        require(options == dict(enumerate(spec["core18_labels"] + ["Other diseases"], 1)), "Detailed list changed")
    if family in {"five_symptom_categories", "detailed_19", "core18_plus_unresolved_extensions"}:
        prompt = cells["I8"] if family == "core18_plus_unresolved_extensions" else cells["AX9"]
        require("main presenting" in prompt and "last 30 days" in prompt, "Type question changed")
    return {
        "form": form,
        "sheet": proof["sheet"],
        "selected_cells": selected,
        "screening_context": proof,
        "printed_options": options,
    }, options


def decode(raw, rule, options, labels, spec):
    """A category name is not, by itself, permission to pool unlike question families."""
    family = rule["family"]
    label = pd.Series(pd.NA, index=raw.index, dtype="string")
    category = label.copy()
    status = pd.Series("unresolved_code", index=raw.index, dtype="string")
    if family.startswith("unverified"):
        status[:] = "unverified_semantics"
    elif family == "absent_from_illness_section":
        status[:] = "not_collected_in_reviewed_section"
        return label, category, status
    else:
        dictionary = labels if family == "native_dictionary_72" else options
        label = raw.map(dictionary).astype("string")
        if family == "early_28day_41":
            mapping = {k: f"early_28day_{k:02d}" for k in options}
            status.loc[label.notna()] = "separate_28day_category"
        elif family == "five_symptom_categories":
            mapping = dict(enumerate(spec["five_categories"], 1))
            status.loc[label.notna()] = "five_category_form_supported"
        else:
            mapping = dict(enumerate(spec["core18_categories"], 1))
            if family == "detailed_19":
                mapping[19] = "other_in_nineteen_option_list"
                status.loc[label.notna()] = "nineteen_category_form_supported"
            elif family == "native_dictionary_72":
                status.loc[label.notna()] = "native_label_only"
            else:
                status.loc[raw.isin(range(1, 19))] = "core18_form_and_native_supported"
                # Printed other (19) is not native-confirmed in the expanded 2021 coding scheme.
                status.loc[raw.eq(19)] = "form_only_residual_unverified"
        category = raw.map(mapping).astype("string")
    missing = raw.isin(rule["missing_codes"])
    category.loc[missing] = pd.NA
    label.loc[missing] = pd.NA
    status.loc[missing] = "explicit_missing_code"
    status.loc[raw.isna()] = "source_null"
    return label, category, status


def type_population(screen, wave):
    raw = screen.raw_screen_code
    result = pd.Series("screen_missing_or_unverified", index=screen.index, dtype="string")
    if wave == "2009":
        result[:] = "not_collected_in_reviewed_section"
    elif wave not in {"2007", "2017"}:
        result.loc[raw.eq(1)] = "illness_or_injury_conditional" if wave not in {"2019", "2021"} else "illness_branch"
        result.loc[raw.eq(2)] = "not_applicable_no_problem" if wave not in {"2019", "2021"} else "not_applicable_injury"
        if wave in {"2019", "2021"}:
            result.loc[raw.eq(3)] = "not_applicable_no_problem"
    return result


def eligibility(frame, wave):
    supported = frame.category_status.isin(
        [
            "five_category_form_supported",
            "nineteen_category_form_supported",
            "core18_form_and_native_supported",
        ]
    )
    within = frame.strict_screening_eligible & frame.raw_screen_code.eq(1) & supported & frame.category.notna()
    # These are label-level candidate records, not a complete common multinomial variable.
    core = within & frame.raw_type_code.isin(range(1, 19)) & (wave in {"2016", "2021"})
    return within, core


def build(root, output):
    spec = json.loads((root / SPEC).read_text())
    require(not spec["database_publication_authorized"], "Publication outside review scope")
    require(
        file_sha(root / SCREENING / "manifest.json") == spec["screening_manifest_sha256"], "Screening release changed"
    )
    upstream = verify_manifest(root / SCREENING)
    for group in ["input_sha256", "implementation_sha256"]:
        for path, expected in upstream[group].items():
            require(file_sha(root / path) == expected, f"Screening dependency changed: {path}")
    intake = verify_manifest(root / HEALTH)
    verify_manifest(root / QUESTIONNAIRES)
    screen = pd.read_parquet(root / SCREENING / "screening.parquet")
    prior = {r["survey_wave"]: r for r in json.loads((root / SCREENING / "wave_review.json").read_text())}
    frames, reviews, crosswalk = [], [], []
    for wave, rule in spec["waves"].items():
        source = next(s for s in intake["sources"] if s["source_id"] == prior[wave]["rule"]["source_id"])
        native = load_source(root / HEALTH, source["source_id"])
        require(source["extended_missing_cells"] == 0, "Extended missing requires explicit handling")
        frame = screen.loc[screen.survey_wave.eq(wave)].reset_index(drop=True).copy()
        require(len(frame) == len(native), "Screen/source count mismatch")
        require(frame.source_id.eq(source["source_id"]).all(), "Wrong source identity")
        require(frame.source_row_number.tolist() == native[ROW_NUMBER].tolist(), "Row locator mismatch")
        pd.testing.assert_frame_equal(
            frame[["survey_wave", "household_id", "person_id"]], source_keys(native, wave), check_exact=True
        )
        frame = frame.rename(
            columns={
                "strict_analysis_eligible": "strict_screening_eligible",
                "alignment_status": "screening_alignment_status",
            }
        )
        fields = rule["fields"]
        require(set(fields).issubset(native.columns), "Expected type fields absent")
        if wave == "2009":
            require(not any(c.lower() in {"q13bc2b", "q13bc02b"} for c in native), "New 2009 type field needs review")
        metadata = [f for f in source["fields"] if f["variable_name"] in fields]
        proof, options = type_evidence(root, prior[wave], rule, spec)
        labels = {int(v["source_value"]): v["label"] for f in metadata for v in f["value_labels"]}
        if wave in {"2019", "2021"}:
            require(
                {k: labels.get(k) for k in range(1, 19)} == dict(enumerate(spec["core18_labels"], 1)),
                "Native core18 labels changed",
            )
            require(len(labels) == (72 if wave == "2019" else 18), "Native dictionary extent changed")
        raw = (
            native[fields[0]].astype("Float64")
            if len(fields) == 1
            else pd.Series(pd.NA, index=frame.index, dtype="Float64")
        )
        frame["raw_type_code"] = raw
        frame["raw_type_answers"] = (
            raw_json_records(native[fields]) if fields else pd.Series("{}", index=frame.index, dtype="string")
        )
        frame["source_type_variables"] = json.dumps(fields)
        frame["type_family"] = rule["family"]
        frame["type_alignment_status"] = rule["status"]
        label, category, state = decode(raw, rule, options, labels, spec)
        if len(fields) > 1:
            state[:] = "unverified_semantics"  # single-code null is an intentional non-flattening representation
        frame["source_interpreted_label"] = label
        frame["category"] = category
        frame["category_status"] = state
        frame["type_population_status"] = type_population(frame, wave)
        frame["within_wave_analysis_eligible"], frame["core18_comparison_candidate"] = eligibility(frame, wave)
        nonnull = native[fields].notna().any(axis=1) if fields else pd.Series(False, index=frame.index)
        nonnull_slots = native[fields].notna().sum(axis=1) if fields else pd.Series(0, index=frame.index)
        frame["type_recorded_outside_branch"] = nonnull & frame.type_population_status.isin(
            ["not_applicable_injury", "not_applicable_no_problem"]
        )
        frame["type_missing_in_illness_branch"] = ~nonnull & frame.type_population_status.eq("illness_branch")
        frame["type_blank_in_conditional_branch"] = ~nonnull & frame.type_population_status.eq(
            "illness_or_injury_conditional"
        )
        frame["type_needs_code_review"] = nonnull & state.isin(
            ["unresolved_code", "form_only_residual_unverified", "explicit_missing_code"]
        )
        distributions = {
            c: {str(k): int(v) for k, v in native[c].value_counts(dropna=False).sort_index().items()} for c in fields
        }
        counts = {
            "source_person_wave_rows": len(frame),
            "records_with_type_answer": int(nonnull.sum()),
            "non_null_slots": int(nonnull_slots.sum()),
            "records_with_multiple_slots": int(nonnull_slots.gt(1).sum()),
            "printed_options": len(options) if options else None,
            "native_label_entries": len(labels),
            "observed_codes": sorted({float(v) for c in fields for v in native[c].dropna().unique()}),
            "within_wave_analysis_eligible": int(frame.within_wave_analysis_eligible.sum()),
            "core18_comparison_candidate": int(frame.core18_comparison_candidate.sum()),
            "outside_branch": int(frame.type_recorded_outside_branch.sum()),
            "missing_in_illness_branch": int(frame.type_missing_in_illness_branch.sum()),
            "blank_in_conditional_branch": int(frame.type_blank_in_conditional_branch.sum()),
            "explicit_missing_codes": int(state.eq("explicit_missing_code").sum()),
            "unresolved_codes": int(state.eq("unresolved_code").sum()),
            "form_only_residual": int(state.eq("form_only_residual_unverified").sum()),
        }
        for field in fields:
            # Catalog observed values and all dictionary/printed options, including unobserved options.
            domain = sorted(set(native[field].dropna().tolist()) | set(options) | set(labels))
            for code in domain:
                _, cat, code_state = decode(pd.Series([code]), rule, options, labels, spec)
                crosswalk.append(
                    {
                        "survey_wave": wave,
                        "source_variable": field,
                        "source_code": float(code),
                        "printed_label": options.get(code),
                        "native_label": labels.get(code),
                        "category": None if pd.isna(cat.iloc[0]) else cat.iloc[0],
                        "status": code_state.iloc[0],
                        "observed_records": int(native[field].eq(code).sum()),
                    }
                )
        reviews.append(
            {
                "survey_wave": wave,
                "rule": rule,
                "source_id": source["source_id"],
                "source_sha256": source["source_sha256"],
                "source_file": source["source_file"],
                "fields": metadata,
                "questionnaire": proof,
                "counts": counts,
                "raw_distributions": distributions,
                "category_status_counts": {str(k): int(v) for k, v in state.value_counts().items()},
                "eligible_category_counts": {
                    str(k): int(v)
                    for k, v in frame.loc[frame.within_wave_analysis_eligible, "category"].value_counts().items()
                },
            }
        )
        frames.append(frame)
        print(wave, json.dumps(counts), flush=True)
    combined = pd.concat(frames, ignore_index=True)
    for c in combined:
        if pd.api.types.is_string_dtype(combined[c].dtype):
            combined[c] = combined[c].astype("string")
    require(len(combined) == len(screen), "Source rows lost")
    require(not combined.duplicated(["source_id", "source_row_number"]).any(), "Duplicate provenance key")
    artifacts = {}
    flagged = (
        combined.type_recorded_outside_branch
        | combined.type_missing_in_illness_branch
        | combined.type_needs_code_review
    )
    for name, data in [
        ("illness_type.parquet", combined),
        ("type_exceptions.parquet", combined.loc[flagged].reset_index(drop=True)),
    ]:
        payload = data.to_parquet(index=False)
        pd.testing.assert_frame_equal(data, pd.read_parquet(io.BytesIO(payload)), check_exact=True)
        add_artifact(output, artifacts, name, payload)
    add_artifact(output, artifacts, "wave_review.json", reviews)
    add_artifact(output, artifacts, "code_crosswalk.json", crosswalk)
    add_artifact(output, artifacts, "README.md", brief(reviews))
    manifest = {
        "review_id": spec["review_id"],
        "stage": "local_partial_semantic_review_not_published",
        "database_mutated": False,
        "publication_approved": False,
        "source_rows": len(combined),
        "fully_aligned_all_ten_waves": False,
        "common_detailed_label_categories": 18,
        "within_wave_eligible_records": int(combined.within_wave_analysis_eligible.sum()),
        "core18_candidate_records": int(combined.core18_comparison_candidate.sum()),
        "exception_records": int(flagged.sum()),
        "artifacts": artifacts,
        "input_sha256": {
            p: file_sha(root / p)
            for p in [SPEC, SCREENING + "/manifest.json", HEALTH + "/manifest.json", QUESTIONNAIRES + "/manifest.json"]
        },
        "implementation_sha256": {
            p: file_sha(root / p)
            for p in [
                "rsc/cses_db/review_cses_health_illness_type.py",
                "rsc/cses_db/review_cses_health_recent_illness.py",
                "rsc/cses_db/plan_cses_health_illness.py",
                "rsc/cses_db/build_cses_health.py",
                "rsc/cses_db/cache_cses_questionnaires.py",
            ]
        },
    }
    put(output / "manifest.json", manifest)
    return manifest


def brief(reviews):
    lines = [
        "# Illness type: local alignment",
        "",
        "One concept reviewed, not 18 newly published variables. All original rows/slots retained. No database writes.",
        "",
        "| Wave | Family | Rows with answer | Non-null slots | Printed options | Native label entries | Within-wave eligible | Core18 candidates |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in reviews:
        c = r["counts"]
        lines.append(
            f"| {r['survey_wave']} | {r['rule']['family']} | {c['records_with_type_answer']:,} | {c['non_null_slots']:,} | {c['printed_options']} | {c['native_label_entries']} | {c['within_wave_analysis_eligible']:,} | {c['core18_comparison_candidate']:,} |"
        )
    lines += [
        "",
        "## Use and limits",
        "",
        "- `illness_type.parquet` is a source-person-wave projection. `raw_type_answers` retains all native slots and numeric sentinels; never flatten 2007 into a first-choice answer.",
        "- `category` is partial semantic naming, NOT full distributional equivalence. Filter `within_wave_analysis_eligible` and keep wave/family when describing categories.",
        "- `core18_comparison_candidate` retains only verified labels 1–18 in 2016/2021 with clean screening. Unresolved or other categories are not zeros. This is not a representative denominator for disease prevalence.",
        "- The 2011-12/2014 five-category candidates and 2019 native-label candidates are qualified and excluded from the strict default.",
        "- 2004 remains a broader 28-day most-important health problem; 2007 repeated slots have unverified semantics; 2009 has no type item in this reviewed section; 2017 is unverified.",
        "- A null type among binary screen-positive members can be an injury skip OR nonresponse. Do not assert a missing illness response. In 2021 the separate illness branch permits that narrower check.",
        "- 2019 code 19 is Fever/Cold, not the 2016 Other diseases. 2021 code 19 is form-only Other diseases and is held out; codes 20–73 have no available native labels. Do not infer a shifted 2019 dictionary.",
        "- Native dictionary size, printed response options and observed distinct codes are different quantities. Label entries may include explicit missing codes.",
        "- `code_crosswalk.json` lists exact native/printed labels, status and counts. `wave_review.json` contains form locators, dictionaries and aggregate checks.",
        "- `type_exceptions.parquet` retains code-resolution issues, explicit missing codes, outside-branch responses and missing responses in a known illness branch. Conditional blanks and unverified waves remain in the main projection without being called data errors.",
        "- Record totals are unweighted person-wave observations, not unique longitudinal respondents or population estimates. No missing health response is set to no disease.",
        "",
        "## Per-wave checks",
        "",
    ]
    for r in reviews:
        lines += [
            f"### {r['survey_wave']}",
            "",
            f"Status: `{r['rule']['status']}`.",
            "",
            f"Counts: `{json.dumps(r['counts'], sort_keys=True)}`",
            "",
        ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.root, args.output or args.root / OUTPUT), indent=2))


if __name__ == "__main__":
    main()
