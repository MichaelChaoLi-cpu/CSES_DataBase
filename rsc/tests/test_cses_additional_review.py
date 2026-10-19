"""Conservative duplicate resolution and immutable questionnaire evidence."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
from cache_cses_questionnaires import file_sha  # noqa: E402
from review_cses_2023_conflicts import classify_duplicate_groups, qualified_provider  # noqa: E402


@pytest.mark.parametrize("answers,status", [
    ([[None, None], [1, 2]], "blank_placeholder_fold_candidate"),
    ([[1, None], [1, 2]], "strict_answer_subset_fold_candidate"),
    ([[2, None], [1, 2]], "unresolved"),
    ([[1, None], [None, 2]], "unresolved"),
    ([[1, 2], [1, 2]], "unresolved"),
    ([[None, None], [None, None]], "unresolved"),
])
def test_duplicate_resolution_requires_strict_consistent_subset(answers, status):
    raw = pd.DataFrame(answers, columns=["q15_a", "q15_b"])
    raw["hhid"], raw["persid"], raw["context"] = 1, 1, 3
    assert classify_duplicate_groups(raw, [])[0]["status"] == status
    assert classify_duplicate_groups(raw.iloc[::-1], [])[0]["status"] == status
    if status != "unresolved":
        assert classify_duplicate_groups(raw, [])[0]["selected_source_row"] == 2
    assert classify_duplicate_groups(raw, [{"source_row_number": 1}])[0]["status"] == "unresolved"
    raw.loc[0, "context"] = 4
    assert classify_duplicate_groups(raw, [])[0]["status"] == "unresolved"


def test_provider_unknown_is_not_other():
    result, unknown = qualified_provider(pd.Series([98, 18, None]), [
        {"source_value": 98, "label": "Don't know"}, {"source_value": 18, "label": "Other"}])
    assert pd.isna(result[0]) and result[1] == 18
    assert unknown.tolist() == [True, False, False]


def test_review_outputs_preserve_original_columns_and_provenance():
    base = ROOT / "data/processing/cses/additional_wave_review_v1"
    original = ROOT / "data/processing/cses/additional_waves_v1"
    manifest = json.loads((base / "manifest.json").read_text())
    assert manifest["reviewer_sha256"] == file_sha(ROOT / "rsc/cses_db/review_cses_2023_conflicts.py")
    assert manifest["candidate_manifest_sha256"] == file_sha(original / "manifest.json")
    for name, digest in manifest["artifacts"].items():
        assert file_sha(base / name) == digest
    for module, filename in [("EC", "EC_2023_unique_candidate.parquet"),
                             ("HEALTH", "HEALTH_2023_qualified_candidate.parquet")]:
        before = pd.read_parquet(original / f"tables/2023/{module}.parquet").set_index("Source Row Number")
        after = pd.read_parquet(base / filename).set_index("Source Row Number")
        pd.testing.assert_frame_equal(before.loc[after.index], after[before.columns])
        assert len(after) == 51914
        if module == "EC":
            represented = [n for value in after["All Source Row Numbers"] for n in json.loads(value)]
            assert sorted(represented) == sorted(before.index.tolist())
            assert after["Qualified Unique Record Eligible"].all()
        else:
            mask = after["source__q13bc09a"].eq(98)
            assert mask.sum() == 3
            assert after.loc[mask, "First Provider Qualified Source Code"].isna().all()


def test_legacy_word_cache_integrity_and_age_evidence():
    base = ROOT / "data/processed/cses_questionnaires/additional_waves_v1"
    cache = base / "legacy_word_text_v1"
    manifest = json.loads((cache / "manifest.json").read_text())
    assert len(manifest["sources"]) == 5
    assert manifest["source_manifest_sha256"] == file_sha(base / "manifest.json")
    assert manifest["extractor_sha256"] == file_sha(ROOT / "rsc/cses_db/extract_cses_legacy_word.py")
    for source in manifest["sources"]:
        assert file_sha(base / source["original_path"]) == source["original_sha256"]
    for name, digest in manifest["artifacts"].items():
        assert file_sha(cache / name) == digest
    for name in ["1996/QuestENG_Form2.txt", "1999/QuestENG_Form3Page.txt"]:
        text = (cache / name).read_text()
        assert "98" in text and "over" in text
