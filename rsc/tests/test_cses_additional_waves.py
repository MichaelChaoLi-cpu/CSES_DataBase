"""Additional-wave alignment is explicit, conservative and separate from publication."""
import io
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
from build_cses_additional_waves import (  # noqa: E402
    OUTPUT,
    SPEC,
    build_table,
    combine_tables,
    compare_variants,
    component,
    fields_for,
    source_keys,
    transform,
    verify,
)
from cache_cses_questionnaires import file_sha, put  # noqa: E402


@pytest.mark.parametrize("value", [1.5, float("inf"), 2**54])
def test_non_integer_or_unsafe_identifier_rejected(value):
    with pytest.raises(ValueError):
        component(value)


def test_identifiers_preserve_strings_and_missing():
    assert component("001") == "001"
    assert component(1.0) == "1"
    assert component(None) is None
    assert component("") is None


def test_composite_keys_are_unambiguous_and_wave_scoped():
    f = pd.DataFrame({"a": ["1:2", "1", None], "b": ["3", "2:3", "3"]})
    keys = source_keys(f, ["a", "b"], "1996")
    assert keys[0] != keys[1]
    assert pd.isna(keys[2])
    assert keys[0] != source_keys(f, ["a", "b"], "1997")[0]


def test_binary_requires_dictionary_and_preserves_unknown_as_null():
    raw = pd.Series([1, 2, 0, 9, None])
    meta = {"value_labels": [{"source_value": 1, "label": " Yes "}, {"source_value": 2, "label": "No"}]}
    mapped, state, bad = transform(raw, meta, "binary")
    assert mapped[:2].tolist() == [1, 0]
    assert mapped[2:].isna().all() and bad == 2
    assert state == "label_verified_recode_scope_qualified"
    missing, state, bad = transform(raw, {"value_labels": []}, "binary")
    assert missing.isna().all() and bad == 4 and state == "blocked_missing_value_labels"


def test_reversed_codes_use_labels_not_numeric_assumptions():
    meta = {"value_labels": [{"source_value": 1, "label": "No"}, {"source_value": 2, "label": "Yes"}]}
    assert transform(pd.Series([1, 2]), meta, "binary")[0].tolist() == [0, 1]


def test_native_codes_are_never_filtered():
    raw = pd.Series([-98.0, 99.0, None])
    pd.testing.assert_series_equal(transform(raw, {}, "native")[0], raw)


def test_union_preserves_string_code_leading_zeros():
    result, converted = combine_tables([pd.DataFrame({"code": [12]}), pd.DataFrame({"code": ["0012"]})])
    assert converted == ["code"] and result["code"].tolist() == ["12", "0012"]


def test_variant_comparison_ignores_dtype_only_changes_not_value_changes():
    a = pd.DataFrame({"id": [1, 2], "v": [1.0, 2.0]})
    b = pd.DataFrame({"id": [2, 1], "v": [3, 1]})
    result = compare_variants(a, b, ["id"])
    assert result["differences"] == [{"key": [2], "variable": "v", "primary": 2.0, "alternate": 3}]
    assert result["primary_only"] == result["alternate_only"] == 0


def test_variant_comparison_rejects_duplicate_keys():
    a = pd.DataFrame({"id": [1, 1], "v": [1, 2]})
    with pytest.raises(ValueError, match="unique"):
        compare_variants(a, a, ["id"])


def test_table_retains_duplicate_and_missing_rows():
    raw = pd.DataFrame({"h": [1, 1, None], "p": [1, 1, 3], "v": [5, 6, 7]})
    config = {"household_key": ["h"], "person_key": "p", "note": "test"}
    meta = [{"variable_name": "v", "variable_label": "native", "value_labels": []}]
    table, _ = build_table("1996", config, "EC", {"member": "x.dta", "grain": "person"},
                           {"Value": ["v", "native"]}, raw, meta, "archive.zip")
    assert len(table) == 3 and table["Duplicate Key"].sum() == 2 and table["Missing Key"].sum() == 1
    assert not table["Unique Source Record Eligible"].any()
    assert table["source__v"].tolist() == [5, 6, 7]


def test_differing_artifacts_cannot_be_overwritten(tmp_path):
    p = tmp_path / "immutable.json"
    put(p, b"first")
    put(p, b"first")
    with pytest.raises(ValueError, match="overwrite"):
        put(p, b"second")
    assert p.read_bytes() == b"first"


def test_registered_waves_and_dangerous_aliases():
    spec = json.loads((ROOT / SPEC).read_text())
    assert set(spec["waves"]) == {"1996", "1997", "1999", "2023", "2025"}
    modern = spec["waves"]["2025"]["modules"]
    ec = fields_for(spec, modern["EC"])
    assert ec["Paid Work Past Week"][0] == "q15_c02"
    assert ec["Platform Income Activity Past Week"][0] == "q15_c03"
    assert "Main Hours Past Week Source Value" not in ec
    assert modern["HEALTH"]["member"] == "S13B_PersonIllness.dta"
    assert fields_for(spec, modern["HO"])["Dwelling Tenure Source Code"][0] == "q04_36"
    for wave in ["1996", "1997", "1999"]:
        assert "Can Read" not in fields_for(spec, spec["waves"][wave]["modules"]["ED"])


def test_new_archives_are_fingerprinted():
    spec = json.loads((ROOT / SPEC).read_text())
    for cfg in spec["waves"].values():
        assert file_sha(ROOT / cfg["archive"]) == cfg["sha256"]


def test_searchable_questionnaires_match_original_cache_and_revised_sheet():
    base = ROOT / "data/processed/cses_questionnaires/additional_waves_v1"
    manifest = json.loads((base / "text_manifest.json").read_text())
    assert file_sha(base / "manifest.json") == manifest["source_manifest_sha256"]
    assert file_sha(ROOT / "rsc/cses_db/extract_cses_additional_questionnaires.py") == manifest["extractor_sha256"]
    for path, digest in manifest["artifacts"].items():
        assert file_sha(base / path) == digest
    workbook = json.loads((base / "2025/text/CSES2025_Household_Questionnaire_ENG.json").read_text())
    cells = workbook["sheets"]["Labor (2)"]
    assert cells["F6"] == "2" and "someone else for pay" in cells["F7"]
    assert cells["G6"] == "3" and "web-based platforms" in cells["G7"]
    assert cells["AQ6"] == "31" and "hours per day" in cells["AQ7"]
    cover = json.loads((base / "2023/text/CSES2023 HH Quest ENG.json").read_text())
    assert len(cover["pages"]) == 1


def test_local_output_integrity_and_independent_source_counts():
    result = verify(ROOT)
    assert result["verified_artifacts"] > 30
    spec = json.loads((ROOT / SPEC).read_text())
    summary = json.loads((ROOT / OUTPUT / "summary.json").read_text())
    expected = {"1996": (9000, 46811), "1997": (6010, 29931), "1999": (6000, 32348),
                "2023": (12096, 51914), "2025": (12338, 51775)}
    assert {r["wave"]: (r["households"], r["roster_records"]) for r in summary["wave_counts"]} == expected
    for wave, cfg in spec["waves"].items():
        with zipfile.ZipFile(ROOT / cfg["archive"]) as archive:
            for name, module in cfg["modules"].items():
                table = pd.read_parquet(ROOT / OUTPUT / f"tables/{wave}/{name}.parquet")
                fields = fields_for(spec, module)
                columns = list(dict.fromkeys([*cfg["household_key"], *(x[0] for x in fields.values())]))
                raw = pd.read_stata(io.BytesIO(archive.read(module["member"])), columns=columns,
                                    convert_categoricals=False, convert_dates=False)
                assert len(table) == len(raw)
                for source in columns:
                    pd.testing.assert_series_equal(table[f"source__{source}"], raw[source], check_names=False)
    ec = pd.read_parquet(ROOT / OUTPUT / "tables/2023/EC.parquet")
    assert len(ec) == 51917 and ec["Duplicate Key"].sum() == 6
    health = pd.read_parquet(ROOT / OUTPUT / "tables/2023/HEALTH.parquet")
    assert health["Source Variant Conflict"].sum() > 0
