"""Deterministic, read-only primary evidence for the narrowly approved 2021 resolution."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile

import pandas as pd
from cses_baseline_metadata import sha256_file
from cses_hh_hl_common import snake_case
from extract_cses_response_option_cells import read_xlsx_cells
from publish_cses_housing_interface import normalized_code, source_archive
from record_cses_value_mapping_decisions import require

RELEASE = "cses-housing-2021-resolution-v1"
SPEC = "rsc/specs/cses_housing_2021_resolution_v1.json"
HO = "data/processing/cses/final_HO_CSES.parquet"
HO_SHA = "e0dae1a43267250b22fd8e18070b4a9243cd8f451fd40511ac4f7666e4b4826d"


def options_from_cells(cells, coordinates):
    result = []
    for coordinate in coordinates:
        for line in cells[coordinate].splitlines():
            if not line.strip():
                continue
            match = re.fullmatch(r"\s*(\d+)\s*=\s*(.*?)\s*", line)
            require(match is not None, "Unparsed questionnaire option")
            result.append({"code": match[1], "label": " ".join(match[2].split()),
                           "raw_text": line, "source_cell": coordinate, "skip_instructions": []})
    require(len(result) == len({r["code"] for r in result}), "Duplicate option code")
    return result


def checked_evidence(root):
    spec = json.loads((root / SPEC).read_text())
    require(spec["release_id"] == RELEASE and sha256_file(root / spec["archive"]) == spec["archive_sha256"],
            "Source scope or archive changed")
    sources = []
    with zipfile.ZipFile(root / spec["archive"]) as archive:
        for item in spec["instruments"]:
            payload = archive.read(item["member"])
            require(hashlib.sha256(payload).hexdigest() == item["source_sha256"], "Questionnaire changed")
            cells = read_xlsx_cells(payload, item["source_sheet"])
            source = {k: v for k, v in item.items() if k != "questions"}
            source["questions"] = []
            for question in item["questions"]:
                expected = question["expected_cells"]
                require({c: cells[c] for c in expected} == expected, "Questionnaire cell transcription changed")
                loc = question["locators"]
                opts = options_from_cells(cells, loc["options"])
                expected_codes = range(1, 5) if question["question_code"] == "q04_28" else range(1, 9 if item["language_code"] == "en" else 10)
                require({o["code"] for o in opts} == {str(i) for i in expected_codes}, "Unexpected option set")
                source["questions"].append({"question_code": question["question_code"],
                    "question_text": " ".join(cells[loc["text"]].split()), "options": opts,
                    "locators": loc, "source_cells": expected,
                    "skip_text": "\n".join(cells[c] for c in [*loc["options"], *loc["skip"]]
                                             if ">>" in cells[c]) or None})
            sources.append(source)
    require(len(sources) == 2 and {s["language_code"] for s in sources} == {"en", "km"}, "Bilingual sources required")
    return {"sources": sources, "translation": spec["translation"], "decision": spec["decision"],
            "source_archives_modified": False, "macros_executed": False}


def local_plan(root):
    spec = json.loads((root / SPEC).read_text())
    require(sha256_file(root / HO) == HO_SHA, "Housing artifact changed")
    evidence = checked_evidence(root)
    with zipfile.ZipFile(root / spec["archive"]) as archive:
        payload = archive.read(spec["housing_member"])
    require(hashlib.sha256(payload).hexdigest() == spec["housing_sha256"], "Raw housing changed")
    with pd.io.stata.StataReader(io.BytesIO(payload), convert_categoricals=False) as reader:
        labels = reader.value_labels()
        assigned = dict(zip(reader._varlist, reader._lbllist, strict=True))
        raw = reader.read()
    lighting_labels = {str(int(k)): v for k, v in labels[assigned["q04_07"]].items()}
    require(lighting_labels["8"] == "ជីវឧស្ម័ន" and lighting_labels["9"] == "Other (specify)",
            "Released lighting labels differ")
    require({int(k) for k in labels[assigned["q04_28"]]} == {1, 2, 3, 4}, "Tenure label scope differs")
    questions = {s["language_code"]: {q["question_code"]: q for q in s["questions"]} for s in evidence["sources"]}
    english = {o["code"]: o["label"] for o in questions["en"]["q04_07"]["options"]}
    khmer = {o["code"]: o["label"] for o in questions["km"]["q04_07"]["options"]}
    require(khmer["8"] == lighting_labels["8"] and english["8"] == "Other (specify)" and "9" not in english,
            "Expected documented language-source conflict changed")
    local = pd.read_parquet(root / HO).rename(columns=snake_case)
    target = local.loc[local.survey_wave.eq("2021")].reset_index(drop=True)
    ordinals = target.source_row_id.str.rsplit(":", n=1).str[-1].astype(int)
    require(len(raw) == len(target) == 10080 and sorted(ordinals) == list(range(1, 10081)), "Non-bijective source rows")
    require(target.source_archive.map(source_archive).eq(spec["archive"]).all()
            and target.source_submodule.eq(spec["housing_member"]).all(), "Housing source identity differs")
    aligned = raw.iloc[ordinals.to_numpy() - 1].reset_index(drop=True)
    pd.testing.assert_series_equal(aligned.q04_07.astype("Float64"), target.main_lighting_source_code.astype("Float64"), check_names=False)
    pd.testing.assert_series_equal(aligned.q04_28.where(aligned.q04_28.isin([1, 2, 3, 4])).astype("Float64"),
                                   target.dwelling_tenure_source_code.astype("Float64"), check_names=False)
    require(list(raw.index[raw.q04_28.eq(0)] + 1) == [6458] and int(raw.q04_28.isna().sum()) == 3,
            "Tenure anomaly changed")
    require(int(target.main_lighting_source_code.eq(8).sum()) == 6, "Expected six biogas observations")
    anomaly = {"survey_wave": "2021", "source_row_id": "2021:S04_HHhousing.dta:6458",
               "source_variable": "q04_28", "raw_code": 0, "published_value": None,
               "quality_status": "undocumented_out_of_range_source_code", "intended_response": "unknown",
               "treatment": "Retain existing analytical NULL and raw archive; no category imputation"}
    source = {"archive": spec["archive"], "archive_sha256": spec["archive_sha256"],
              "member_chain": [spec["housing_member"]], "member_sha256": spec["housing_sha256"]}
    row = {"survey_wave": "2021", "field": "main_lighting_source_code", "source_variable": "q04_07",
           "source_code": "8", "category": "biogas", "label": "Biogas", "source_label": lighting_labels["8"],
           "observed_count": 6, "evidence": {"approval_basis": "user_approved_bilingual_evidence_resolution",
               "preferred_evidence": "Khmer questionnaire agrees with released Stata labels",
               "conflicting_evidence": "English questionnaire codes 8 as Other and lacks code 9",
               "conflict_cause": "not_established", "questionnaires": evidence["sources"],
               "translation": evidence["translation"], "decision": evidence["decision"], "housing_source": source}}
    coverage = [{"survey_wave": "2021", "field": field, "rows": 10080,
                 "nonnull": int(target[field].notna().sum()), "nulls": int(target[field].isna().sum()),
                 "observed_codes": {normalized_code(k): int(v) for k, v in target[field].value_counts().items()}}
                for field in ("dwelling_tenure_source_code", "main_cooking_fuel_source_code", "main_lighting_source_code")]
    return {"release_id": RELEASE, "spec_sha256": sha256_file(root / SPEC), "rows": [row],
            "sources": {"2021": source}, "coverage": coverage, "evidence": evidence,
            "tenure_anomaly": anomaly, "raw_codes_unchanged": True}
