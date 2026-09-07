"""The screening review separates equivalent wording, code semantics and publication."""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cses_db"))
from review_cses_health_recent_illness import analysis_eligible, branch_flags, evidence, recode  # noqa: E402

SPEC = json.loads((Path(__file__).resolve().parents[1] / "specs/cses_health_recent_illness_v1.json").read_text())
RULES = SPEC["waves"]


@pytest.mark.parametrize("wave", ["2009", "2011-12", "2013", "2014", "2016"])
def test_old_binary_mapping_does_not_accept_new_codes(wave):
    result, state = recode(pd.Series([1, 2, 3, 9, 98, 99, None]), RULES[wave])
    assert result.iloc[:2].tolist() == [1, 0]
    assert result.iloc[2:].isna().all()
    assert state.iloc[2] == "unmapped_code"
    assert state.iloc[-1] == "source_null"


@pytest.mark.parametrize("wave", ["2019", "2021"])
def test_injury_is_yes_not_no_in_recent_waves(wave):
    result, _ = recode(pd.Series([1, 2, 3, 0, 9, None]), RULES[wave])
    assert result.iloc[:3].tolist() == [1, 1, 0]
    assert result.iloc[3:].isna().all()


@pytest.mark.parametrize("wave", ["2007", "2017"])
def test_binary_looking_values_without_evidence_remain_uninterpreted(wave):
    result, state = recode(pd.Series([1, 2, None]), RULES[wave])
    assert result.isna().all()
    assert state.tolist() == ["unverified_semantics", "unverified_semantics", "source_null"]


def test_2004_missing_and_period_are_not_zero_or_thirty_days():
    result, state = recode(pd.Series([1, 2, 9, None]), RULES["2004"])
    assert result.iloc[:2].tolist() == [1, 0]
    assert result.iloc[2:].isna().all()
    assert state.iloc[2] == "explicit_missing_code"
    assert RULES["2004"]["period_days"] == 28
    assert RULES["2019"]["period_days"] is None


def test_branch_flags_preserve_raw_answers_and_distinguish_injury():
    raw = pd.Series([1, 2, 3, 3])
    native = pd.DataFrame({"Q13BC2B": [1, 21, 12, None], "Q13BC03": [2, None, None, None]})
    before = native.copy(deep=True)
    flags, profile = branch_flags(native, raw, RULES["2021"])
    assert flags.no_with_followup.tolist() == [False, False, True, False]
    assert flags.injury_with_illness_only.tolist() == [False, True, False, False]
    assert profile["Q13BC2B"]["3"]["nonnull"] == 1
    pd.testing.assert_frame_equal(native, before)
    assert raw.tolist() == [1, 2, 3, 3]


def test_no_form_does_not_assert_skip_rules():
    flags, profile = branch_flags(pd.DataFrame({"q13bc2b": [1, 2]}), pd.Series([2, 3]), RULES["2019"])
    assert not flags.any().any()
    assert profile  # descriptive evidence survives even without adjudication


def test_strict_subset_rejects_qualified_missing_orphan_and_branch_flags():
    frame = pd.DataFrame(
        {
            "alignment_status": ["form_supported"] * 7,
            "recent_illness_injury_30d": pd.Series([0, 1, 1, 1, 1, 1, None], dtype="Int8"),
            "hl_link_status": ["matched"] * 7,
            "hh_link_matched": [True] * 7,
            "no_with_followup": [False] * 7,
            "injury_with_illness_only": [False] * 7,
        }
    )
    frame.loc[1, "alignment_status"] = "qualified_draft_form"
    frame.loc[2, "hl_link_status"] = "person_not_in_roster"
    frame.loc[3, "hh_link_matched"] = False
    frame.loc[4, "no_with_followup"] = True
    frame.loc[5, "injury_with_illness_only"] = True
    assert analysis_eligible(frame).tolist() == [True, False, False, False, False, False, False]


def test_review_is_one_concept_and_does_not_authorize_publication():
    assert not SPEC["database_publication_authorized"]
    assert len(RULES) == 10
    assert [w for w, r in RULES.items() if r["status"] == "form_supported"] == ["2009", "2013", "2016", "2021"]
    assert evidence(Path("/nonexistent"), {"sources": []}, RULES["2017"]) is None


def test_missing_selected_form_fails_without_archive_fallback():
    with pytest.raises(ValueError, match="selected questionnaire"):
        evidence(Path("/nonexistent"), {"sources": []}, RULES["2021"])


def test_local_cached_form_evidence_and_options():
    root = Path(__file__).resolve().parents[2]
    base = root / "data/processed/cses_questionnaires/v1"
    if not (base / "manifest.json").exists():
        pytest.skip("DVC questionnaire cache not available")
    library = json.loads((base / "manifest.json").read_text())
    for wave, rule in RULES.items():
        proof = evidence(base, library, rule)
        if proof:
            assert proof["form"]["survey_wave"] == wave
            assert proof["locators"]["question"] in proof["header_cells"]
    assert "Injury" in evidence(base, library, RULES["2021"])["options"]
