"""Age bounds, population scope and non-imputing schooling route checks."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
from audit_cses_1999_school_routes import flag_routes  # noqa: E402
from cache_cses_questionnaires import file_sha  # noqa: E402
from qualify_cses_legacy_age import OUTPUT, qualify_age, scope_audit  # noqa: E402


def test_age_bounds_do_not_make_topcodes_exact():
    raw = pd.Series([0, 97, 98, None, 99, -1, 4.5, "bad", float("inf")])
    result = qualify_age(raw)
    assert result["Age Exact Years Qualified"][:2].tolist() == [0, 97]
    assert result["Age Exact Years Qualified"][2:].isna().all()
    assert result.loc[2, "Age Lower Bound Years Qualified"] == 98
    assert result.loc[2, "Age Topcoded Qualified"]
    assert result["Age Topcoded Qualified"][3:].isna().all()
    assert result.loc[3, "Age Qualification Status"] == "missing_source_age"
    assert result["Age Qualification Status"][4:].eq("invalid_source_age").all()


def test_scope_detects_exclusions_missing_and_unlinked():
    roster = pd.DataFrame({"Record Key": list("abcd"), "Age Source Value": [4, 5, 98, None]})
    module = pd.DataFrame({"Record Key": list("acdx")})
    report = scope_audit(roster, module)
    assert report["age_5_plus_roster"] == 2
    for name in ["eligible_absent_from_module", "under_5_module_rows", "unlinked_module_rows", "unknown_or_invalid_age_module_rows"]:
        assert report[name] == 1
    with pytest.raises(ValueError):
        scope_audit(roster, pd.concat([module, module]))


def test_routes_flag_without_imputation():
    frame = pd.DataFrame({"Ever Attended School": [0, 1, 1, 1, 1, 0, None],
                          "Currently Attending School": [None, None, None, 1, 0, 1, None],
                          "Highest Education Level Source Code": [None, 1, 1, 1, 1, None, None],
                          "Current Education Level Source Code": [None, None, 3, None, 3, 3, None]})
    result = flag_routes(frame)
    pd.testing.assert_frame_equal(result[frame.columns], frame)
    assert result["Route Review Status"].tolist() == ["never_attended_skip_observed", "current_attendance_missing_after_ever_yes",
        "current_attendance_missing_but_grade_present", "current_grade_missing_after_current_yes",
        "response_in_expected_skipped_item", "response_in_expected_skipped_item", "ever_attendance_missing"]


def test_age_output_integrity_and_original_columns():
    base = ROOT / OUTPUT
    manifest = json.loads((base / "manifest.json").read_text())
    assert manifest["builder_sha256"] == file_sha(ROOT / "rsc/cses_db/qualify_cses_legacy_age.py")
    for name, digest in manifest["artifacts"].items():
        assert file_sha(base / name) == digest
    for wave, count in [("1996", 4), ("1999", 2)]:
        before = pd.read_parquet(ROOT / f"data/processing/cses/additional_waves_v1/tables/{wave}/HL.parquet")
        after = pd.read_parquet(base / f"HL_{wave}_age_qualified.parquet")
        pd.testing.assert_frame_equal(before, after[before.columns])
        assert after["Age Topcoded Qualified"].sum() == count
        assert after.loc[after["Age Topcoded Qualified"], "Age Exact Years Qualified"].isna().all()


def test_school_output_integrity_and_counts():
    base = ROOT / "data/processing/cses/education_1999_route_review_v1"
    manifest = json.loads((base / "manifest.json").read_text())
    assert manifest["builder_sha256"] == file_sha(ROOT / "rsc/cses_db/audit_cses_1999_school_routes.py")
    for name, digest in manifest["artifacts"].items():
        assert file_sha(base / name) == digest
    before = pd.read_parquet(ROOT / "data/processing/cses/additional_waves_v1/tables/1999/ED.parquet")
    after = pd.read_parquet(base / "ED_1999_route_review.parquet")
    pd.testing.assert_frame_equal(before, after[before.columns])
    counts = after["Route Review Status"].value_counts()
    assert counts["current_attendance_missing_after_ever_yes"] == 11
    assert counts["current_attendance_missing_but_grade_present"] == 1
    assert counts["never_attended_skip_observed"] == 8255
