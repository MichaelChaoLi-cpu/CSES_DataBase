"""Source caches preserve evidence without implying health comparability."""

import io
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cses_db"))
from build_cses_health import (  # noqa: E402
    classify_source,
    key_profiles,
    read_stata,
    select_columns,
)
from cache_cses_questionnaires import (  # noqa: E402
    BASE,
    WAVE_NOTES,
    build,
    cached_source,
    leaf_name,
    member_bytes,
    put,
    safe_path,
    sha,
    source_id,
    verify_manifest,
)
from organize_cses_questionnaires import encoded  # noqa: E402

SPEC = json.loads((Path(__file__).resolve().parents[1] / "specs/cses_health_intake_v1.json").read_text())


def test_2007_spaced_village_folder_is_not_omitted():
    assert (
        classify_source("CSES 2007.zip::CSES 2007/Village data/Village2007/05_villhealth.dta", SPEC)
        == "village_health_context"
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("CSES2017.zip::2017hh_s13b_healthexpenses.dta", "illness_care"),
        ("CSES 2004.zip::2004hh_s10b_feedingvaccinations.dta", "child_feeding_vaccination"),
        ("CSES 2007.zip::code/dbo_c_kindillness.dta", None),
        ("CSES 2007.zip::Code/dbo_c_villmedicalservice.dta", None),
        ("CSES2016.zip::VCSES2016/medicine_prices.dta", "village_health_context"),
        ("CSES2021-Village_data.zip::S3C_Medical.dta", "village_health_context"),
        ("CSES2013.zip::nested.zip::HHOtherInfo.dta", "healthcare_access_mixed"),
        ("CSES2017.zip::2017hh_s15_labor7days.dta", None),
        ("CSES2004.zip::2004hh_s11_mortality.dta", "mortality"),
    ],
)
def test_topic_discovery_is_explicit(name, expected):
    assert classify_source(name, SPEC) == expected


def test_mixed_health_selection_preserves_case_and_excludes_other_questions():
    frame = pd.DataFrame(columns=["hhid", "Q13AQ1", "Q13AQ2A", "Q01DQ3C", "hw2021"])
    assert select_columns(frame, "healthcare_access_mixed", SPEC) == ["hhid", "Q13AQ1", "Q13AQ2A", "hw2021"]
    assert select_columns(frame[["hhid", "Q01DQ3C"]], "healthcare_access_mixed", SPEC) == []


def test_all_dedicated_columns_remain():
    frame = pd.DataFrame(columns=["hhid", "persid", "q1", "unknown"])
    assert select_columns(frame, "illness_care", SPEC) == list(frame)


def test_raw_codes_and_labels_not_harmonized():
    frame = pd.DataFrame({"hhid": [1, 2, 3, 4], "q1": [0.0, 9.0, 98.0, float("nan")]})
    buffer = io.BytesIO()
    frame.to_stata(
        buffer,
        write_index=False,
        variable_labels={"q1": "Original question"},
        value_labels={"q1": {0: "None", 9: "Missing", 98: "Unknown"}},
    )
    result, metadata, extended = read_stata(buffer.getvalue())
    assert result.q1.iloc[:3].tolist() == [0.0, 9.0, 98.0]
    assert pd.isna(result.q1.iloc[3]) and extended == []
    field = next(f for f in metadata if f["variable_name"] == "q1")
    assert field["non_null_records"] == 3
    assert field["variable_label"] == "Original question"
    assert field["value_labels"][1] == {"source_value": 9, "label": "Missing"}
    assert field["alignment_status"] == "not_reviewed"


def test_extended_missing_positions_are_preserved():
    frame = pd.DataFrame({"q1": [float("nan"), 1.0]})
    buffer = io.BytesIO()
    frame.to_stata(buffer, write_index=False, version=118)
    payload = buffer.getvalue()
    # Stata double .a: increment the system-missing bit pattern by 2**40.
    import struct

    begin = payload.index(b"<data>") + len(b"<data>")
    value = struct.unpack("<Q", payload[begin : begin + 8])[0]
    payload = payload[:begin] + struct.pack("<Q", value + 2**40) + payload[begin + 8 :]
    result, _, extended = read_stata(payload)
    assert pd.isna(result.q1.iloc[0])
    assert extended == [{"source_row_number": 1, "variable_name": "q1", "stata_missing_code": ".a"}]


def test_key_diagnostics_do_not_drop_or_deduplicate():
    frame = pd.DataFrame({"hhid": [1, 1, 2], "persid": [11, 11, None]})
    profile = key_profiles(frame)[0]
    assert profile["distinct_complete_keys"] == 1
    assert profile["records_in_duplicate_complete_keys"] == 2
    assert profile["missing_key_records"] == 1
    assert len(frame) == 3


@pytest.mark.parametrize("relative", ["../outside", "/absolute", "a/../../b"])
def test_manifest_path_traversal_rejected(tmp_path, relative):
    with pytest.raises(ValueError, match="Unsafe"):
        safe_path(tmp_path, relative)


def test_symlink_escape_rejected(tmp_path):
    (tmp_path / "link").symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(ValueError, match="Escaping"):
        safe_path(tmp_path, "link/outside")


def test_identity_keeps_same_leaf_variants_separate():
    assert source_id("a.zip::form.xls") != source_id("b.zip::form.xls")
    assert leaf_name("a.zip::../form\u200b.xls") == "form.xls"


def test_no_differing_overwrite(tmp_path):
    path = tmp_path / "a"
    put(path, b"same")
    put(path, b"same")
    with pytest.raises(ValueError, match="Refusing"):
        put(path, b"changed")
    assert path.read_bytes() == b"same"


def test_cache_build_nested_roundtrip_and_archive_free_verify(tmp_path):
    raw = tmp_path / "data/raw"
    raw.mkdir(parents=True)
    nested = io.BytesIO()
    payload = b"original workbook bytes"
    with zipfile.ZipFile(nested, "w") as z:
        z.writestr("form.xls", payload)
    archive = raw / "CSES2013.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("nested.zip", nested.getvalue())
    name = "data/raw/CSES2013.zip::nested.zip::form.xls"
    source = {
        "source_file": name,
        "survey_wave": "2013",
        "source_sha256": sha(payload),
        "instrument_type": "household_questionnaire",
        "language_code": "en",
        "documentation_status": "documented",
    }
    cells = [
        {
            "source_file": name,
            "source_sha256": sha(payload),
            "sheets": {"13 Health": {"A1": "What health?", "B2": "1 = yes\n2 = no"}},
        }
    ]
    inventory = {
        "sources": [source],
        "source_cells_sha256": sha(encoded(cells)),
        "archive_sha256": {"data/raw/CSES2013.zip": sha(archive.read_bytes())},
    }
    put(tmp_path / BASE / "source_inventory.json", inventory)
    put(tmp_path / BASE / "source_cells.json", cells)
    output = tmp_path / "library"
    result = build(tmp_path, output)
    assert build(tmp_path, output) == result
    assert member_bytes(tmp_path, name) == payload
    archive.rename(raw / "unavailable.zip")
    assert verify_manifest(output) == result
    path, record = cached_source(output, name)
    assert path.read_bytes() == payload
    assert record["cells_path"] is not None
    assert len(result["waves"]) == 10
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="changed"):
        cached_source(output, name)
    with pytest.raises(ValueError, match="changed"):
        verify_manifest(output)


def test_no_implicit_2017_or_2014_questionnaire_approval():
    assert "Do not substitute" in WAVE_NOTES["2017"]
    assert "draft" in WAVE_NOTES["2014"]
    assert SPEC["database_publication_authorized"] is False
