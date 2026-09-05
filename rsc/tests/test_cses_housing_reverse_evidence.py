"""Diagnostic profiles cannot silently become semantic approvals."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cses_db"))
import profile_cses_housing_reverse_evidence as evidence  # noqa: E402


def test_missing_is_not_zero():
    result = evidence.stats(pd.Series([None, 0, 100, 200], dtype="Float64"))
    assert result == {"rows": 4, "observed": 3, "missing": 1, "positive": 2, "zero": 1,
                      "positive_fraction_of_observed": 2 / 3}


def test_all_missing_is_not_no_spending():
    assert evidence.stats(pd.Series([None, None]))["positive_fraction_of_observed"] is None


def test_profile_excludes_circular_harmonized_field():
    frame = pd.DataFrame({"Dwelling Tenure Source Code": [1, 2, 1],
                          "Dwelling Tenure Harmonized": [99, 88, 77],
                          "Monthly Rent Paid Riel": [None, 10, 0],
                          "Monthly Imputed Rent Riel": [100, None, 200]})
    result = evidence.profile(frame, "dwelling_tenure_source_code", 1)
    assert set(result["expenses"]) == {"paid_rent", "imputed_rent"}
    assert result["rows"] == 2
    assert result["sparse_under_20"] is True
    assert result["expenses"]["paid_rent"]["observed"] == 1


def test_raw_replay_uses_one_based_source_id_not_local_order():
    raw = pd.DataFrame({"x": [10, 20, 30]})
    local = pd.DataFrame({"Source Row ID": ["2007:raw:3", "2007:raw:1", "2007:raw:2"]})
    assert evidence.align_raw(raw, local)["x"].tolist() == [30, 10, 20]


@pytest.mark.parametrize("ids", [[1, 1, 3], [0, 1, 2], [1, 2], [1, 2, 4]])
def test_raw_replay_rejects_non_bijection(ids):
    with pytest.raises(ValueError, match="one-to-one"):
        evidence.align_raw(pd.DataFrame({"x": [1, 2, 3]}),
                           pd.DataFrame({"Source Row ID": [f"w:s:{i}" for i in ids]}))


def test_evidence_cannot_be_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence, "render", lambda report: "test\n")
    evidence.write_outputs(tmp_path, {"value": 1})
    first = (tmp_path / "evidence.json").read_bytes()
    evidence.write_outputs(tmp_path, {"value": 1})
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        evidence.write_outputs(tmp_path, {"value": 2})
    assert (tmp_path / "evidence.json").read_bytes() == first
