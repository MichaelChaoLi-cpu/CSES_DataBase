"""Regression checks for semantic and missing-code mistakes in the read-only pilot."""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from pandas.io.stata import StataMissingValue

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))

from plan_cses_value_audit import (  # noqa: E402
    frequencies,
    parse_option_cell,
    read_evidence,
    reconcile_value,
)


@pytest.fixture
def spec():
    return json.loads((ROOT / "rsc/specs/cses_value_audit_v1.json").read_text())


def test_nine_is_missing_only_with_explicit_same_source_evidence(spec):
    old = reconcile_value("9", "numeric", "missing", None, False, spec)
    recent = reconcile_value("9", "numeric", "Other (specify)", None, False, spec)
    unknown = reconcile_value("9", "numeric", None, None, False, spec)
    assert old["missing_class"] == "unspecified_missing"
    assert recent["missing_class"] == "substantive"
    assert recent["candidate_category"] == "other"
    assert unknown["missing_class"] == "unresolved"


def test_numbered_options_exclude_followup_questions_and_keep_skip_routing():
    parsed = parse_option_cell("01 = Firewood\n04 = LPG (=>> 24)\n", "D95")
    assert parsed[0]["source_code"] == "1"
    assert parsed[1]["label"] == "LPG"
    assert parsed[1]["skip_text"] == "(=>> 24)"
    assert parsed[1]["source_cell"] == "D95"
    with pytest.raises(ValueError, match="Unparsed option"):
        parse_option_cell("Which members collect firewood?", "D100")


def test_conflicting_missing_and_valid_evidence_does_not_choose_a_meaning(spec):
    result = reconcile_value("9", "numeric", "missing", {"label": "Other"}, False, spec)
    assert result["candidate_category"] is None
    assert result["missing_class"] == "unresolved"
    assert "source_label_option_conflict" in result["flags"]


def test_draft_and_untranslated_labels_remain_visible(spec):
    draft = reconcile_value("1", "numeric", None, {"label": "Firewood"}, True, spec)
    untranslated = reconcile_value("8", "numeric", "ជីវឧស្ម័ន", None, False, spec)
    assert draft["candidate_category"] == "firewood"
    assert "draft_questionnaire" in draft["flags"]
    assert untranslated["candidate_category"] is None
    assert "source_label_translation_required" in untranslated["flags"]


def test_compound_fuels_are_not_silently_merged(spec):
    single = reconcile_value("4", "numeric", "Kerosene", None, False, spec)
    combined = reconcile_value("4", "numeric", "Kerosene/Diesel", None, False, spec)
    assert single["candidate_category"] == "kerosene"
    assert combined["candidate_category"] == "kerosene_or_diesel"
    assert "category_comparability_review" in combined["flags"]


def test_stata_extended_missing_numeric_sentinel_and_null_stay_distinct():
    counts = frequencies([9, 9.0, StataMissingValue(101), StataMissingValue(102), pd.NA, "9"])
    assert counts == {("numeric", "9"): 2, ("stata_missing", "."): 1,
                      ("stata_missing", ".a"): 1, ("system_missing", "NULL"): 1, ("string", "9"): 1}


def test_evidence_tampering_fails_before_build_or_database_access(tmp_path):
    source = tmp_path / "evidence.json"
    source.write_text("{}")
    with pytest.raises(ValueError, match="fingerprint changed"):
        read_evidence(tmp_path, {"evidence": {"input": {"path": "evidence.json", "sha256": "0" * 64}}})
