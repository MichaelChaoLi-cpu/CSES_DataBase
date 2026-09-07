"""Release scope, original-data preservation, nullable interpretation and graph guards."""
import ast
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
import publish_cses_employment_correction as pub  # noqa: E402
from cses_archive_source_policy import archive_source_policy  # noqa: E402
from plan_cses_age_topcode import qualify  # noqa: E402
from review_cses_employment_hours_status import registry  # noqa: E402


def sample():
    frame = pd.DataFrame({
        "survey_wave": pd.Series(["2004"] * 4 + ["2009", "2017", "2021", "2004"], dtype="string"),
        "person_id": pd.Series([f"p{x}" for x in range(8)], dtype="string"),
        "source_row_id": pd.Series([f"r{x}" for x in range(8)], dtype="string"),
        "age": pd.Series([96, 20, pd.NA, 60, 20, 25, 30, pd.NA], dtype="Int16"),
        pub.DAY: pd.Series([3, 4, pd.NA, 2, pd.NA, 6, 7, pd.NA], dtype="Int16"),
        pub.STATUS[0]: pd.Series([9, 1, pd.NA, 5, 9, 9, 9, pd.NA], dtype="Int16"),
        pub.STATUS[1]: pd.Series([1, 9, 9, 4, 9, 9, 9, pd.NA], dtype="Int16"),
        pub.HOUR: pd.Series([96, 40, pd.NA, 97, 96, 96, 96, pd.NA], dtype="Int16")})
    recovery = frame.loc[[4], pub.RECOVERY_COLUMNS].copy()
    recovery[pub.DAY] = pd.Series([12], index=[4], dtype="Int16")
    return qualify(frame, "age"), recovery


def test_only_missing_2009_days_recovered_with_original_values_preserved():
    before, recovery = sample()
    after = pub.corrected(before, recovery)
    assert after[pub.DAY].iloc[4] == 12 and after[pub.EXTRAS[1]].notna().sum() == 1
    assert pd.isna(before[pub.DAY].iloc[4])
    restored = after[list(before)].copy()
    restored[pub.DAY] = after[pub.EXTRAS[0]]
    pd.testing.assert_frame_equal(restored, before)


def test_status_code_columns_retained_and_interpretation_scoped_to_2004():
    before, recovery = sample()
    after = pub.corrected(before, recovery)
    for source, target in zip(pub.STATUS, pub.INTERPRETED, strict=True):
        pd.testing.assert_series_equal(before[source], after[source])
        assert after[target].iloc[4:7].tolist() == [9, 9, 9]
    assert pd.isna(after[pub.INTERPRETED[0]].iloc[0])
    assert after[pub.MISSING[0]].iloc[0]
    assert not after[pub.MISSING[0]].iloc[1]
    assert after[pub.MISSING[0]].iloc[4:7].isna().all()


def test_hours_lower_bound_not_exact_and_other_waves_not_certified():
    before, recovery = sample()
    after = pub.corrected(before, recovery)
    assert after[pub.EXTRAS[6]].iloc[0] and after[pub.EXTRAS[7]].iloc[0] == 96
    assert pd.isna(after[pub.EXTRAS[8]].iloc[0]) and after[pub.HOUR].iloc[0] == 96
    assert after[pub.EXTRAS[8]].iloc[1] == 40
    assert after[pub.EXTRAS[9]].iloc[3] == "unexpected_2004_code"
    assert after[pub.EXTRAS[6]].iloc[4:7].isna().all()
    assert after[pub.EXTRAS[9]].iloc[4:7].eq("outside_rule_scope").all()


def test_missing_source_values_are_not_zero_or_false():
    before, recovery = sample()
    after = pub.corrected(before, recovery)
    for field in [*pub.INTERPRETED, *pub.MISSING, *pub.EXTRAS[6:9]]:
        assert pd.isna(after[field].iloc[7])
    assert after[pub.EXTRAS[9]].iloc[7] == "missing_hours"


@pytest.mark.parametrize("mutation", ["duplicate", "wrong_wave", "wrong_row", "overwrite", "fractional", "missing"])
def test_recovery_rejects_scope_or_identity_changes(mutation):
    before, recovery = sample()
    if mutation == "duplicate":
        recovery = pd.concat([recovery, recovery])
    elif mutation == "wrong_wave":
        recovery.loc[:, "survey_wave"] = "2017"
    elif mutation == "wrong_row":
        recovery.loc[:, "source_row_id"] = "not-the-original-row"
    elif mutation == "overwrite":
        before.loc[4, pub.DAY] = 20
    elif mutation == "fractional":
        recovery[pub.DAY] = 1.5
    else:
        recovery.loc[:, pub.DAY] = pd.NA
    with pytest.raises(ValueError):
        pub.corrected(before, recovery)


@pytest.fixture(scope="module")
def plan():
    if not (ROOT / pub.REVIEW).exists():
        pytest.skip("DVC-owned review not present")
    with archive_source_policy():
        return pub.source_plan(ROOT)


def test_full_scope_74_columns_13830_recoveries_256_missing_and_six_topcodes(plan):
    p, frame, recovery = plan
    assert frame.shape == (332903, 74) and recovery.shape == (13830, 4)
    assert frame[pub.EXTRAS[1]].notna().sum() == 13830
    assert [frame[c].sum() for c in pub.MISSING] == [185, 71]
    assert frame[pub.EXTRAS[6]].sum() == 6
    assert frame.age_2004_is_topcoded.sum() == 3
    assert p["existing_physical_changes"] == p["existing_interfaces_replaced"] == 0
    assert list(frame.columns[-10:]) == pub.EXTRAS


def test_four_rule_rows_locate_original_variables_and_labels(plan):
    rules = plan[0]["rules"]
    assert len(rules) == 4 and rules[0]["source_variable_id"] == 989
    assert [r["affected_cells_or_records"] for r in rules] == [13830, 185, 71, 6]
    assert [r["source_value_label"] for r in rules] == [None, "missing", "missing", "96 and more hours"]
    assert all(r["data_source_sha256"] and r["questionnaire_sha256"] for r in rules)


def test_graph_preserves_v12_and_explicitly_adds_recovery_dependencies(plan):
    def key(rows):
        return {json.dumps(r, sort_keys=True) for r in rows}

    before = json.loads((ROOT / pub.GRAPH).read_text())
    after = pub.graph_extension(before, plan[0], "test", registry(ROOT), [])
    for kind, delta in [("nodes", 3), ("edges", 10)]:
        assert key(before[kind]) <= key(after[kind])
        assert len(after[kind]) == len(before[kind]) + delta


def test_confirmation_guard_precedes_backup_or_database_access(monkeypatch):
    monkeypatch.setattr(pub, "execution", lambda root: ({}, "expected", {}, None, None))
    with pytest.raises(ValueError, match="Verified execution hash"):
        pub.apply(ROOT, "wrong")


def test_writer_never_replaces_or_updates_historical_objects():
    tree = ast.parse((ROOT / pub.SELF).read_text())
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not any(s.lstrip().upper().startswith(("DROP ", "DELETE ", "UPDATE ", "TRUNCATE ", "CREATE OR REPLACE")) for s in strings)
    body = ast.unparse(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "apply"))
    assert body.index("result = checks") < body.index("conn.commit()")
    assert body.index("Historical data/interfaces changed") < body.index("conn.commit()")
    assert "conn.rollback()" in body and "rollback_test.json" in body
