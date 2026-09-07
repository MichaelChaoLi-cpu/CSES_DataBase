#!/usr/bin/env python3
"""Recover three 2021 categories from the cached Khmer form; retain immutable v1.

Run `forms` with bundled Python for workbook inspection, then `build` with project
Python for the native-data projection. Neither command uses archives, network or DB.
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from cache_cses_questionnaires import add_artifact, file_sha, put, require, verify_manifest

SPEC = "rsc/specs/cses_health_illness_type_khmer_v2.json"
UPSTREAM = "data/processing/cses/health_illness_type_v1"
QUESTIONNAIRES = "data/processed/cses_questionnaires/v1"
OUTPUT = "data/processing/cses/health_illness_type_khmer_v2"
IMPLEMENTATION = "rsc/cses_db/recover_cses_2021_illness_dictionary.py"


def extract_tail(text):
    """Read only explicitly numbered 19–21; never derive meanings from frequencies."""
    pairs = re.findall(r"(?:^|\s)(19|20|21)\s*=\s*(.*?)(?=\s+(?:19|20|21|22)\s*=|$)", text, re.S)
    result = {k: " ".join(v.split()) for k, v in pairs}
    require(len(result) == len(pairs) == 3, "Missing/duplicate recovered option codes")
    return result


def forms(root, output):
    spec = json.loads((root / SPEC).read_text())
    library = verify_manifest(root / QUESTIONNAIRES)
    records = []
    for identity in [spec["questionnaire_id"], "715917b0b0b7597b"]:
        form = next(s for s in library["sources"] if s["source_id"] == identity)
        require(form["survey_wave"] == "2021", "Wrong questionnaire wave")
        sheets = json.loads((root / QUESTIONNAIRES / form["cells_path"]).read_text())["sheets"]
        if identity == spec["questionnaire_id"]:
            require(
                form["language_code"] == "km" and form["source_sha256"] == spec["questionnaire_sha256"],
                "Wrong Khmer source",
            )
            cells = sheets[spec["sheet"]]
            tail = extract_tail(cells["B47"])
            require(tail == {k: v["khmer"] for k, v in spec["mapping"].items()}, "Khmer options changed")
            require(cells["F30"] == "(2b)" and "2b" in cells["B46"], "Wrong printed question")
            require("30" in cells["F9"] and "30" in cells["B5"], "Missing 30-day context")
            selected = {k: cells[k] for k in spec["locators"]}
            sheet = spec["sheet"]
        else:
            sheet = "13 Health Care Seeking _ 2"
            selected = {k: sheets[sheet][k] for k in ["C7", "C18", "I8", "I25", "C42"]}
            require("19 = Other diseases" in selected["C42"], "English conflict changed")
        with zipfile.ZipFile(root / QUESTIONNAIRES / form["local_path"]) as z:
            ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            wb = ET.fromstring(z.read("xl/workbook.xml"))
            hidden = [
                s.attrib["name"]
                for s in wb.findall("s:sheets/s:sheet", ns)
                if s.attrib.get("state", "visible") != "visible"
            ]
            comments = {
                n: " ".join(ET.fromstring(z.read(n)).itertext())
                for n in z.namelist()
                if "comment" in n.lower() and n.endswith(".xml")
            }
        records.append(
            {"form": form, "sheet": sheet, "cells": selected, "hidden_sheets": hidden, "comment_text": comments}
        )
    proof = {
        "records": records,
        "spec_sha256": file_sha(root / SPEC),
        "questionnaire_manifest_sha256": file_sha(root / QUESTIONNAIRES / "manifest.json"),
        "implementation_sha256": file_sha(root / IMPLEMENTATION),
    }
    put(output / "questionnaire_evidence.json", proof)
    return {"forms_checked": len(records), "recovered_codes": [19, 20, 21]}


def recover(frame, spec):
    import pandas as pd

    result = frame.copy(deep=True)
    target = result.survey_wave.eq("2021") & result.raw_type_code.isin([int(k) for k in spec["mapping"]])
    for col in [
        "category",
        "category_status",
        "source_interpreted_label",
        "type_alignment_status",
        "type_needs_code_review",
    ]:
        result[col + "_v1"] = frame[col]
    result["source_label_km_v2"] = pd.Series(pd.NA, index=result.index, dtype="string")
    for code, mapping in spec["mapping"].items():
        chosen = target & result.raw_type_code.eq(int(code))
        result.loc[chosen, "category"] = mapping["category"]
        result.loc[chosen, "category_status"] = "khmer_form_supported_version_qualified"
        result.loc[chosen, "source_interpreted_label"] = mapping["english_gloss"]
        result.loc[chosen, "source_label_km_v2"] = mapping["khmer"]
        result.loc[chosen, "type_needs_code_review"] = False
    result.loc[result.survey_wave.eq("2021"), "type_alignment_status"] = "partial_khmer21_unresolved_extensions"
    # Original conservative eligibility stays unchanged; acceptance of the form-version evidence is explicit.
    result["version_qualified_analysis_eligible"] = (
        target & result.strict_screening_eligible & result.raw_screen_code.eq(1)
    )
    result["within_wave_eligible_with_qualifications"] = (
        result.within_wave_analysis_eligible | result.version_qualified_analysis_eligible
    )
    return result, target


def build(root, output):
    import io

    import pandas as pd

    spec = json.loads((root / SPEC).read_text())
    require(not spec["publication_approved"], "No publication authority")
    require(file_sha(root / UPSTREAM / "manifest.json") == spec["upstream_manifest_sha256"], "Upstream review changed")
    upstream = verify_manifest(root / UPSTREAM)
    for group in ["input_sha256", "implementation_sha256"]:
        for name, digest in upstream[group].items():
            require(file_sha(root / name) == digest, f"Upstream dependency changed: {name}")
    proof = json.loads((output / "questionnaire_evidence.json").read_text())
    require(proof["spec_sha256"] == file_sha(root / SPEC), "Evidence spec changed")
    require(proof["implementation_sha256"] == file_sha(root / IMPLEMENTATION), "Evidence implementation changed")
    require(
        proof["questionnaire_manifest_sha256"] == file_sha(root / QUESTIONNAIRES / "manifest.json"),
        "Evidence library changed",
    )
    verify_manifest(root / QUESTIONNAIRES)
    km = next(r for r in proof["records"] if r["form"]["source_id"] == spec["questionnaire_id"])
    require(
        extract_tail(km["cells"]["B47"]) == {k: v["khmer"] for k, v in spec["mapping"].items()}, "Evidence text changed"
    )
    original = pd.read_parquet(root / UPSTREAM / "illness_type.parquet")
    result, target = recover(original, spec)
    changed = {
        "category",
        "category_status",
        "source_interpreted_label",
        "type_alignment_status",
        "type_needs_code_review",
    }
    preserved = [c for c in original if c not in changed]
    pd.testing.assert_frame_equal(result[preserved], original[preserved], check_exact=True)
    for col in changed - {"type_alignment_status"}:
        pd.testing.assert_series_equal(result.loc[~target, col], original.loc[~target, col], check_exact=True)
    require(
        len(result) == len(original) and not result.duplicated(["source_id", "source_row_number"]).any(),
        "Row/key integrity failed",
    )
    artifacts = {"questionnaire_evidence.json": file_sha(output / "questionnaire_evidence.json")}
    flagged = (
        result.type_recorded_outside_branch | result.type_missing_in_illness_branch | result.type_needs_code_review
    )
    for name, frame in [
        ("illness_type.parquet", result),
        ("type_exceptions.parquet", result.loc[flagged].reset_index(drop=True)),
    ]:
        payload = frame.to_parquet(index=False)
        pd.testing.assert_frame_equal(frame, pd.read_parquet(io.BytesIO(payload)), check_exact=True)
        add_artifact(output, artifacts, name, payload)
    counts = []
    for code, mapping in spec["mapping"].items():
        mask = target & result.raw_type_code.eq(int(code))
        counts.append(
            {
                "code": int(code),
                **mapping,
                "source_records": int(mask.sum()),
                "eligible_records_with_version_qualification": int(
                    (mask & result.version_qualified_analysis_eligible).sum()
                ),
                "outside_branch": int((mask & result.type_recorded_outside_branch).sum()),
            }
        )
    remaining = result.loc[result.survey_wave.eq("2021") & result.raw_type_code.gt(21)]
    unresolved = [
        {"code": int(k), "source_records": int(v), "label": None}
        for k, v in remaining.raw_type_code.value_counts().sort_index().items()
    ]
    add_artifact(output, artifacts, "recovered_codes.json", counts)
    add_artifact(output, artifacts, "unresolved_codes.json", unresolved)
    summary = {
        "review_id": spec["review_id"],
        "database_mutated": False,
        "publication_approved": False,
        "stage": "partial_dictionary_recovery_with_language_version_qualification",
        "source_rows": len(result),
        "recovered_label_records": int(target.sum()),
        "new_version_qualified_eligible_records": int(result.version_qualified_analysis_eligible.sum()),
        "remaining_unresolved_2021_records": len(remaining),
        "remaining_unresolved_2021_codes": len(unresolved),
        "2021_eligible_with_qualifications": int(
            result.loc[result.survey_wave.eq("2021"), "within_wave_eligible_with_qualifications"].sum()
        ),
        "original_conservative_eligibility_unchanged": True,
        "type_exception_records": int(flagged.sum()),
        "artifacts": artifacts,
        "input_sha256": {
            p: file_sha(root / p) for p in [SPEC, UPSTREAM + "/manifest.json", QUESTIONNAIRES + "/manifest.json"]
        },
        "implementation_sha256": {
            p: file_sha(root / p) for p in [IMPLEMENTATION, "rsc/cses_db/cache_cses_questionnaires.py"]
        },
    }
    add_artifact(output, artifacts, "README.md", make_brief(summary, counts, spec))
    put(output / "manifest.json", summary)
    return summary


def make_brief(summary, counts, spec):
    lines = [
        "# 2021 illness-type dictionary: Khmer-form recovery",
        "",
        spec["qualification"],
        "",
        "| Code | Original Khmer | Review English gloss | Source rows | Version-qualified eligible |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    lines += [
        f"| {c['code']} | {c['khmer']} | {c['english_gloss']} | {c['source_records']} | {c['eligible_records_with_version_qualification']} |"
        for c in counts
    ]
    lines += [
        "",
        f"Remaining unresolved codes: {summary['remaining_unresolved_2021_codes']}; records: {summary['remaining_unresolved_2021_records']}.",
        "",
        "Original conservative `within_wave_analysis_eligible` stays unchanged. Use `within_wave_eligible_with_qualifications` only when explicitly accepting the Khmer-form version evidence. Keep `category_status` in every extract.",
        "`category`, `category_status` and the review English label change only for 2021 codes 19–21. Prior interpretations remain in `_v1` fields. All native codes, answers, IDs and upstream screening values are unchanged.",
        "Codes 22–73 are not assigned to other, and 2019 labels are not shifted into 2021. Code 20 is a questionnaire flu/cold category, not a virologically verified diagnosis.",
        "The main projection retains 358,859 person-wave rows. No missing/no-illness/injury record receives a fabricated illness. One code-21 injury-branch answer has a recovered label but remains excluded.",
        "This is local processing evidence, not a new database table or published lineage graph. No Git or DVC push was performed.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["forms", "build"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    fn = forms if args.command == "forms" else build
    print(json.dumps(fn(args.root, args.output or args.root / OUTPUT), indent=2))


if __name__ == "__main__":
    main()
