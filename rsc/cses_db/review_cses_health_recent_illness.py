#!/usr/bin/env python3
"""Cache-only first HEALTH semantic review. No archive access or database writes."""

from __future__ import annotations

import argparse
import io
import json
import re
from pathlib import Path

import pandas as pd
from build_cses_health import ROW_NUMBER, load_source
from cache_cses_questionnaires import add_artifact, file_sha, put, require, verify_manifest
from plan_cses_health_illness import BASELINES, HEALTH, QUESTIONNAIRES, canonical_keys, link_keys, source_keys

SPEC = "rsc/specs/cses_health_recent_illness_v1.json"
OUTPUT = "data/processing/cses/health_recent_illness_v1"
LAYOUTS = {
    "2004": ("14 Health", "AA4", "AA12", "M3", "AA16"),
    "2009": ("Health Care Seeking _ Expen ", "AR7", "AR18", "AR4", "AR25"),
    "middle": ("13 Health Care Seeking _ Expen ", "AR8", "AR19", "AR5", "AR26"),
    "2021": ("13 Health Care Seeking _ 2", "C7", "C18", "B2", "C25"),
}
PROMPT_30 = (
    "Please tell me if any member of your household is sick, has an illness or injury now or at any time "
    "in the last 30 days."
)


def normalized(value):
    return " ".join(str(value).split())


def evidence(base, library, rule):
    if rule["form_id"] is None:
        return None
    matches = [s for s in library["sources"] if s["source_id"] == rule["form_id"]]
    require(len(matches) == 1, "Missing/ambiguous selected questionnaire")
    form = matches[0]
    require(form["language_code"] == "en" and form["registered_instrument_id"] is not None, "Wrong form role")
    sheet, prompt, options, universe, number = LAYOUTS[rule["layout"]]
    cells = json.loads((base / form["cells_path"]).read_text())["sheets"][sheet]
    expected = (
        "Did ..[NAME].. have any illness, injury or other health problem in the past 4 weeks?"
        if rule["layout"] == "2004"
        else PROMPT_30
    )
    require(normalized(cells[prompt]) == expected, "Question text changed")
    option_text = re.sub(r"\s", "", cells[options])
    if rule["layout"] == "2021":
        require(option_text == "1=sick/illness2=Injury(>>4)3=No(>>7)", "Three-code options changed")
    else:
        require(option_text.startswith("1=Yes2=No"), "Binary options changed")
    require("all members" in cells[universe] and "usually" in cells[universe], "Universe changed")
    # Include full header/branch context and adjacent printed question numbers, not isolated keywords.
    headers = {k: v for k, v in cells.items() if int(re.sub(r"\D", "", k)) <= 26}
    return {
        "form": form,
        "sheet": sheet,
        "locators": {"question": prompt, "options": options, "universe": universe, "printed_number": number},
        "header_cells": headers,
        "question": cells[prompt],
        "options": cells[options],
        "universe": cells[universe],
        "printed_number": cells[number],
    }


def recode(raw, rule):
    """Never infer mappings from observed code cardinality; preserve unknown vs missing."""
    mapping = {int(k): v for k, v in rule["mapping"].items()}
    result = raw.map(mapping).astype("Int8")
    status = pd.Series("unmapped_code", index=raw.index, dtype="string")
    if not mapping:
        status[:] = "unverified_semantics"
    status.loc[raw.isna()] = "source_null"
    status.loc[raw.isin(rule["missing_codes"])] = "explicit_missing_code"
    status.loc[result.notna()] = "mapped_native_answer"
    return result, status


def branch_flags(native, raw, rule):
    """Flag nonempty skipped branches; do not change the screening answer."""
    names = {n.lower(): n for n in native}
    flags = pd.DataFrame(False, index=native.index, columns=["no_with_followup", "injury_with_illness_only"])
    profile = {}
    no_codes = [int(k) for k, v in rule["mapping"].items() if v == 0]
    for low in ["q14a07", "q14ac07a", "q14ac07b", "q13bc2b", "q13bc03", "q13bc04", "q13bc05", "q13bc06"]:
        if low not in names:
            continue
        column = names[low]
        profile[column] = {
            str(code): {
                "rows": len(group),
                "nonnull": int(group[column].notna().sum()),
                "distinct_nonnull": int(group[column].nunique()),
                "minimum": None if group[column].notna().sum() == 0 else float(group[column].min()),
                "maximum": None if group[column].notna().sum() == 0 else float(group[column].max()),
            }
            for code, group in native.groupby(raw, dropna=False)
        }
        # No branch rule is asserted for unverified 2007/2017 or untranscribed 2019 forms.
        if rule["form_id"] is not None:
            flags["no_with_followup"] |= raw.isin(no_codes) & native[column].notna()
            if rule["layout"] == "2021" and low in {"q13bc2b", "q13bc03"}:
                flags["injury_with_illness_only"] |= raw.eq(2) & native[column].notna()
    return flags, profile


def analysis_eligible(frame):
    return (
        frame.alignment_status.eq("form_supported")
        & frame.recent_illness_injury_30d.notna()
        & frame.hl_link_status.eq("matched")
        & frame.hh_link_matched
        & ~frame.no_with_followup
        & ~frame.injury_with_illness_only
    )


def build(root, output):
    spec = json.loads((root / SPEC).read_text())
    require(not spec["database_publication_authorized"], "Review cannot authorize publication")
    intake = verify_manifest(root / HEALTH)
    library = verify_manifest(root / QUESTIONNAIRES)
    require(
        file_sha(root / QUESTIONNAIRES / "manifest.json") == intake["questionnaire_library_manifest_sha256"],
        "Intake questionnaire dependency changed",
    )
    baselines = {kind: canonical_keys(pd.read_parquet(root / path), kind) for kind, path in BASELINES.items()}
    frames, reviews = [], []
    for wave, rule in spec["waves"].items():
        sources = [s for s in intake["sources"] if s["source_id"] == rule["source_id"]]
        require(len(sources) == 1, "Missing/ambiguous health source")
        source = sources[0]
        require(source["survey_wave"] == wave and source["topic"] == "illness_care", "Wrong source scope")
        require(source["extended_missing_cells"] == 0, "Extended missing requires explicit review")
        native = load_source(root / HEALTH, rule["source_id"])
        field = next(f for f in source["fields"] if f["variable_name"] == rule["variable"])
        proof = evidence(root / QUESTIONNAIRES, library, rule)
        if proof:
            require(proof["form"]["survey_wave"] == wave, "Cross-wave questionnaire transfer forbidden")
        if wave in {"2019", "2021"}:
            labels = {v["source_value"]: v["label"] for v in field["value_labels"]}
            require(labels == {"1": "Diseases", "2": "Injury", "3": "No"}, "Native label drift")
        raw = native[rule["variable"]]
        mapped, state = recode(raw, rule)
        flags, branch_profile = branch_flags(native, raw, rule)
        keys = source_keys(native, wave)
        frame = link_keys(keys, baselines["hh"], baselines["hl"])
        frame["source_id"] = rule["source_id"]
        frame["source_row_number"] = native[ROW_NUMBER].astype("int64")
        frame["source_variable"] = rule["variable"]
        # All screened native values are numeric; Float64 retains null and all observed codes exactly.
        frame["raw_screen_code"] = raw.astype("Float64")
        require(frame.raw_screen_code.astype(raw.dtype).equals(raw), "Screen code roundtrip failed")
        frame["native_screen_present"] = mapped
        frame["response_status"] = state
        frame["reference_period_days"] = pd.Series(rule["period_days"], index=frame.index, dtype="Int16")
        frame["alignment_status"] = rule["status"]
        frame["recent_illness_injury_30d"] = (
            mapped if rule["period_days"] == 30 else pd.Series(pd.NA, index=frame.index, dtype="Int8")
        )
        for col in flags:
            frame[col] = flags[col]
        frame["strict_analysis_eligible"] = analysis_eligible(frame)
        roster = baselines["hl"].loc[baselines["hl"].survey_wave.eq(wave)]
        roster_only = roster.merge(keys, how="left", indicator=True, validate="one_to_one")._merge.eq("left_only")
        counts = {
            "source_person_wave_records": len(frame),
            "native_nonnull": int(raw.notna().sum()),
            "native_yes": int(mapped.eq(1).sum()),
            "native_no": int(mapped.eq(0).sum()),
            "uninterpreted_or_missing": int(mapped.isna().sum()),
            "mapped_30day_records_including_qualified": int(frame.recent_illness_injury_30d.notna().sum()),
            "hl_unmatched": int(frame.hl_link_status.ne("matched").sum()),
            "roster_only": int(roster_only.sum()),
            "no_with_followup": int(flags.no_with_followup.sum()),
            "injury_with_illness_only": int(flags.injury_with_illness_only.sum()),
            "unique_branch_flagged_records": int(flags.any(axis=1).sum()),
            "strict_eligible_records": int(frame.strict_analysis_eligible.sum()),
            "strict_eligible_yes": int(
                frame.loc[frame.strict_analysis_eligible, "recent_illness_injury_30d"].eq(1).sum()
            ),
        }
        reviews.append(
            {
                "survey_wave": wave,
                "rule": rule,
                "source_file": source["source_file"],
                "source_sha256": source["source_sha256"],
                "native_field": field,
                "questionnaire": proof,
                "raw_counts": {str(k): int(v) for k, v in raw.value_counts(dropna=False).sort_index().items()},
                "response_status_counts": {str(k): int(v) for k, v in state.value_counts().items()},
                "counts": counts,
                "adjacent_branch_profiles": branch_profile,
            }
        )
        frames.append(frame)
        print(wave, rule["status"], counts, flush=True)
    combined = pd.concat(frames, ignore_index=True)
    for column in combined:
        if pd.api.types.is_string_dtype(combined[column].dtype):
            combined[column] = combined[column].astype("string")
    require(not combined.duplicated(["source_id", "source_row_number"]).any(), "Duplicate provenance keys")
    require(not combined.duplicated(["survey_wave", "household_id", "person_id"]).any(), "Duplicate person-wave keys")
    artifacts = {}
    flagged = combined.no_with_followup | combined.injury_with_illness_only | combined.hl_link_status.ne("matched")
    for name, frame in [
        ("screening.parquet", combined),
        ("review_exceptions.parquet", combined.loc[flagged].reset_index(drop=True)),
    ]:
        payload = frame.to_parquet(index=False)
        pd.testing.assert_frame_equal(frame, pd.read_parquet(io.BytesIO(payload)), check_exact=True)
        add_artifact(output, artifacts, name, payload)
    add_artifact(output, artifacts, "wave_review.json", reviews)
    add_artifact(output, artifacts, "README.md", brief(spec, reviews))
    inputs = [SPEC, HEALTH + "/manifest.json", QUESTIONNAIRES + "/manifest.json", *BASELINES.values()]
    implementations = [
        "rsc/cses_db/" + name + ".py"
        for name in [
            "review_cses_health_recent_illness",
            "plan_cses_health_illness",
            "build_cses_health",
            "cache_cses_questionnaires",
            "cses_hh_hl_common",
            "organize_cses_questionnaires",
        ]
    ]
    manifest = {
        "review_id": spec["review_id"],
        "stage": "local_semantic_review_not_published",
        "database_mutated": False,
        "publication_approved": False,
        "source_rows": len(combined),
        "new_concepts_reviewed": 1,
        "fully_aligned_across_all_ten_waves": False,
        "strict_form_supported_waves": [r["survey_wave"] for r in reviews if r["rule"]["status"] == "form_supported"],
        "strict_eligible_records": int(combined.strict_analysis_eligible.sum()),
        "exception_records": int(flagged.sum()),
        "artifacts": artifacts,
        "input_sha256": {p: file_sha(root / p) for p in inputs},
        "implementation_sha256": {p: file_sha(root / p) for p in implementations},
    }
    put(output / "manifest.json", manifest)
    return manifest


def brief(spec, reviews):
    lines = [
        "# Recent illness/injury: first HEALTH variable review",
        "",
        spec["definition"],
        "",
        "Local derivation only; not a published database table or an all-ten-wave equivalence claim.",
        "",
        "| Wave | Native variable | Person-wave rows | Native yes | Native no | Missing/unverified | Strict eligible | Status |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for review in reviews:
        c, r = review["counts"], review["rule"]
        lines.append(
            f"| {review['survey_wave']} | {r['variable']} | {c['source_person_wave_records']:,} | {c['native_yes']:,} | {c['native_no']:,} | {c['uninterpreted_or_missing']:,} | {c['strict_eligible_records']:,} | {r['status']} |"
        )
    lines += [
        "",
        "Native yes/no are mapped answers, not 30-day estimates. Unverified waves have no interpreted answer.",
        "The 2019 native-label mapping establishes code meaning only, not a verified 30-day question.",
        "",
        "## Outputs and selection",
        "",
        "- `screening.parquet`: every source row, raw code, separate native interpretation, period, 30-day candidate, provenance and quality flags.",
        "- `wave_review.json`: exact form/source identities, cell locators, literal header evidence, native labels, counts and adjacent branch profiles.",
        "- `review_exceptions.parquet`: retained branch contradictions and unmatched HL people; do not expose individual identifiers in reports.",
        "- `manifest.json`: input, implementation and output fingerprints. Rebuild refuses differing overwrite.",
        "",
        "Select `strict_analysis_eligible == True` for the conservative local subset, then group by survey wave.",
        "This requires form-supported 30-day meaning, a mapped response, HH/HL linkage and no checked branch contradiction.",
        "2011-12 and 2014 have explicit qualified 30-day candidates but are excluded by this conservative default.",
        "2004 uses 28 days and a broader concept; 2007/2017 are unverified; 2019 lacks verified period evidence.",
        "No missing response or missing source person is assigned zero. A flagged raw no stays no, not automatically yes.",
        "Branch checks concern the screening question only; downstream items are not thereby certified.",
        "Counts are unweighted person-wave records, not unique longitudinal people or personally interviewed respondents.",
        "Do not sum waves to estimate a population. Weights/design variables and denominator choices need analysis-specific review.",
        "",
        "## Per-wave evidence and qualifications",
        "",
    ]
    for review in reviews:
        lines += [f"### {review['survey_wave']}", "", review["rule"]["note"], ""]
        q = review["questionnaire"]
        if q:
            lines += [
                f"Form `{q['form']['source_id']}`, sheet `{q['sheet']}`, cells `{q['locators']}`.",
                "",
                normalized(q["question"]),
                "",
                normalized(q["options"]),
                "",
            ]
        lines += [f"Aggregate checks: `{json.dumps(review['counts'], sort_keys=True)}`", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build(args.root, args.output or args.root / OUTPUT)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
