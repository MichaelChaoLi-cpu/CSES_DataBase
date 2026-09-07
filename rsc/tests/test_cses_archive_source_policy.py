"""Source aliases require exact extraction paths AND exact bytes; originals stay intact."""
import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cses_db"))
import inventory_cses_archives as inventory  # noqa: E402
from cses_archive_source_policy import (  # noqa: E402
    LEGACY_DISCOVER,
    archive_source_policy,
    discover_sources,
    extraction_aliases,
    resolve_sources,
)


def make_zip(path, members):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, value in members.items():
            archive.writestr(name, value)


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def test_identical_extracted_member_prefers_original_archive(tmp_path):
    raw = tmp_path / "data/raw"
    make_zip(raw / "CSES2007.zip", {"CSES2007/member.dta": b"native bytes"})
    put(raw / "CSES2007/member.dta", b"native bytes")
    result, report = resolve_sources(tmp_path, LEGACY_DISCOVER(tmp_path))
    assert len(result) == 1 and result[0].archive_members == ("CSES2007/member.dta",)
    assert len(report["identical_aliases"]) == 1 and not report["source_files_mutated"]
    assert (raw / "CSES2007/member.dta").read_bytes() == b"native bytes"


def test_changed_copy_remains_visible(tmp_path):
    raw = tmp_path / "data/raw"
    make_zip(raw / "CSES2007.zip", {"CSES2007/member.dta": b"original"})
    put(raw / "CSES2007/member.dta", b"changed")
    result, report = resolve_sources(tmp_path, LEGACY_DISCOVER(tmp_path))
    assert len(result) == 2 and len(report["changed_copies_retained"]) == 1
    assert not report["identical_aliases"]


def test_nested_zip_and_its_extracted_member_are_aliases(tmp_path):
    raw = tmp_path / "data/raw"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("members.dta", b"native")
    make_zip(raw / "CSES2013.zip", {"CSES2013/inner.zip": stream.getvalue()})
    put(raw / "CSES2013/inner.zip", stream.getvalue())
    put(raw / "CSES2013/inner/members.dta", b"native")
    result, report = resolve_sources(tmp_path, LEGACY_DISCOVER(tmp_path))
    assert len(result) == 1
    assert result[0].archive_members == ("CSES2013/inner.zip", "members.dta")
    assert len(report["identical_aliases"]) == 2


def test_identical_independent_file_is_not_content_deduplicated(tmp_path):
    raw = tmp_path / "data/raw"
    make_zip(raw / "CSES2007.zip", {"CSES2007/member.dta": b"same"})
    put(raw / "independent/member.dta", b"same")
    make_zip(raw / "CSES2009.zip", {"CSES2009/member.dta": b"same"})
    result, report = resolve_sources(tmp_path, LEGACY_DISCOVER(tmp_path))
    assert len(result) == 3 and not report["identical_aliases"]


def test_loose_only_sources_are_retained(tmp_path):
    put(tmp_path / "data/raw/CSES2017/members.dta", b"native")
    result, report = resolve_sources(tmp_path, LEGACY_DISCOVER(tmp_path))
    assert len(result) == 1 and report["discovered"] == report["retained"]


def test_macos_sidecars_are_not_stata_sources(tmp_path):
    raw = tmp_path / "data/raw"
    put(raw / "CSES2016/._members.dta", b"macos resource fork")
    put(raw / "__MACOSX/members.dta", b"macos resource fork")
    put(raw / "CSES2016/members.dta", b"actual")
    result, report = resolve_sources(tmp_path, LEGACY_DISCOVER(tmp_path))
    assert len(result) == 1 and len(report["macos_noise_excluded"]) == 2


@pytest.mark.parametrize("member", ["../outside.dta", "/outside.dta"])
def test_extraction_aliases_do_not_escape_raw(tmp_path, member):
    raw = tmp_path / "data/raw"
    source = inventory.DataSource(raw / "CSES2013.zip", (member,))
    assert list(extraction_aliases(source, raw)) == []


def test_context_restores_legacy_discovery_after_error():
    with pytest.raises(RuntimeError):
        with archive_source_policy():
            assert inventory.discover_sources is discover_sources
            raise RuntimeError("test")
    assert inventory.discover_sources is LEGACY_DISCOVER


def test_nested_context_keeps_outer_policy():
    with archive_source_policy():
        with archive_source_policy():
            assert inventory.discover_sources is discover_sources
        assert inventory.discover_sources is discover_sources
    assert inventory.discover_sources is LEGACY_DISCOVER
