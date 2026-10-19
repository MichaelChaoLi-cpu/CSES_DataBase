"""2004 recovered geography must be exact, additive and traceable."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
from cache_cses_questionnaires import file_sha  # noqa: E402
from retest_cses_2004_geography import BASE, FIELDS, OUT, attach_cover  # noqa: E402


def fixtures():
    cover = pd.DataFrame({"hhid": [1, 2], "psu": [10, 10], "province": [1, 1], "q40_psu": [10, 10],
                          "q40_prov": [1, 1], "q40_dist": [2, 2], "q40_comm": [3, 3], "q40_vill": [4, 4]})
    roster = pd.DataFrame({"hhid": [2, 1, 1], "psu": [10, 10, 10], "province": [1, 1, 1]})
    return roster, cover


def test_exact_join_preserves_members():
    roster, cover = fixtures()
    linked = attach_cover(roster, cover.iloc[::-1])
    assert len(linked) == 3 and linked[FIELDS].notna().all().all()
    pd.testing.assert_frame_equal(linked[roster.columns], roster)


@pytest.mark.parametrize("problem", ["duplicate", "missing", "psu", "province", "within_psu"])
def test_unsafe_bridge_rejected(problem):
    roster, cover = fixtures()
    if problem == "duplicate":
        cover = pd.concat([cover, cover])
    elif problem == "missing":
        cover.loc[0, "q40_vill"] = None
    elif problem == "psu":
        cover.loc[0, "q40_psu"] = 11
    elif problem == "province":
        cover.loc[0, "q40_prov"] = 2
    else:
        cover.loc[0, "q40_vill"] = 5
    with pytest.raises(ValueError):
        attach_cover(roster, cover)


def test_actual_results_and_other_waves_unchanged():
    manifest = json.loads((OUT / "manifest.json").read_text())
    assert manifest["script_sha256"] == file_sha(ROOT / "rsc/cses_db/retest_cses_2004_geography.py")
    assert manifest["previous_manifest_sha256"] == file_sha(BASE / "manifest.json")
    for name, digest in manifest["artifacts"].items():
        assert file_sha(OUT / name) == digest
    before = json.loads((BASE / "summary.json").read_text())
    after = json.loads((OUT / "summary.json").read_text())
    for old, new in zip(before["waves"], after["waves"], strict=True):
        if old["wave"] != "2004":
            assert old == new
        else:
            assert new["complete_village_code_records"] == new["roster_records"] == 74719
            assert new["directory_code_matched_records"] == 60218
            assert new["admin3_polygon_code_matched_records"] == 65544
            assert new["admin2_polygon_code_matched_records"] == 70247
    records = pd.DataFrame(json.loads((OUT / "2004_geography_aggregate.json").read_text()))
    assert records.roster_records.sum() == 74719
    assert records.loc[records.directory_status.str.startswith("unique_code"), "roster_records"].sum() == 60218
    assert not after["database_modified"]
