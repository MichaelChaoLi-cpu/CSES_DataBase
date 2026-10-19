"""Local feasibility must not confuse directory matches with village geometry."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
from cache_cses_questionnaires import file_sha  # noqa: E402
from test_cses_geography_local import OUTPUT, code_components  # noqa: E402


def test_geography_composite_keys_preserve_parents_and_missing():
    f = pd.DataFrame({"p": [1, 2, 1], "d": [2, 2, None], "c": [3, 3, 3], "v": [4, 4, 4]})
    keys = code_components(f, ["p", "d", "c", "v"])
    assert keys.admin4[:2].tolist() == ["01020304", "02020304"]
    assert pd.isna(keys.admin4[2]) and keys.admin1[2] == "01"


@pytest.mark.parametrize("value", [123, 1.5, "bad", -1])
def test_invalid_local_code_is_not_silently_truncated(value):
    f = pd.DataFrame({"p": [1], "d": [value], "c": [1], "v": [1]})
    with pytest.raises(ValueError):
        code_components(f, list(f.columns))


def test_feasibility_manifest_and_metric_boundaries():
    manifest = json.loads((OUTPUT / "manifest.json").read_text())
    assert manifest["script_sha256"] == file_sha(ROOT / "rsc/cses_db/test_cses_geography_local.py")
    for name, digest in manifest["artifacts"].items():
        assert file_sha(OUTPUT / name) == digest
    report = json.loads((OUTPUT / "summary.json").read_text())
    assert not report["database_modified"] and len(report["waves"]) == 15
    assert report["directory_rows"] == 14576
    assert report["directory_audit"]["usable_rows"] + report["directory_audit"]["excluded_rows"] == 14576
    for wave in report["waves"]:
        n = wave["roster_records"]
        for key in ["directory_code_matched_records", "admin2_polygon_code_matched_records", "admin3_polygon_code_matched_records"]:
            assert 0 <= wave[key] <= n
        assert wave["village_geometry_status"].startswith("not_testable")
        assert wave["historical_identity_status"] == "not_verified_code_equality_only"
        assert wave["directory_matched_unique_codes"] <= wave["unique_source_village_codes"]
        if wave["wave"] == "2004":
            assert wave["complete_village_code_records"] == 0
