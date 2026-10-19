#!/usr/bin/env python3
"""Recover 2004 cover geography for an offline additive feasibility test."""
import io
import json
import subprocess
import zipfile
from pathlib import Path

import pandas as pd
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put
from test_cses_geography_local import code_components

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "data/processing/cses/geography_feasibility_v1"
OUT = ROOT / "data/processing/cses/geography_feasibility_2004_supplement_v1"
SHA = "5c33fa2b5883fc42929771ed16bd06c98f5bf7917229f9a671bb546e073b2cec"
FIELDS = ["q40_prov", "q40_dist", "q40_comm", "q40_vill"]


def attach_cover(roster, cover):
    if cover.hhid.isna().any() or cover.hhid.duplicated().any():
        raise ValueError("Ambiguous household source keys")
    complete = cover[FIELDS].notna().all(axis=1)
    if not cover.loc[complete, "psu"].eq(cover.loc[complete, "q40_psu"]).all():
        raise ValueError("Cover PSU conflict")
    if not cover.loc[complete, "province"].eq(cover.loc[complete, "q40_prov"]).all():
        raise ValueError("Cover province conflict")
    if cover.loc[complete].groupby("psu")[FIELDS].nunique().gt(1).any().any():
        raise ValueError("Multiple administrative locations within a PSU")
    result = roster.merge(cover[["hhid", "q40_psu", *FIELDS]], on="hhid", how="left", validate="many_to_one", indicator=True)
    if not result._merge.eq("both").all() or not result[FIELDS].notna().all().all():
        raise ValueError("Roster geography coverage incomplete")
    if not result.psu.eq(result.q40_psu).all() or not result.province.eq(result.q40_prov).all():
        raise ValueError("Roster/cover geography conflict")
    return result


def build():
    manifest = json.loads((BASE / "manifest.json").read_text())
    for name, digest in manifest["artifacts"].items():
        if file_sha(BASE / name) != digest:
            raise ValueError("Prior evidence modified")
    archive = ROOT / "data/raw/CSES 2004.zip"
    if file_sha(archive) != SHA:
        raise ValueError("2004 archive changed")
    with zipfile.ZipFile(archive) as z:
        def read(name):
            return pd.read_stata(io.BytesIO(z.read("CSES 2004/Stata 2004/" + name)), convert_categoricals=False)
        cover = read("2004hh_s99_singlequestions.dta")
        roster = read("2004hh_s01a_hhmembers.dta")
    linked = attach_cover(roster, cover)
    keys = code_components(linked, FIELDS)
    parser = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
    parsed = subprocess.run([str(parser), "-c", "import csv,io,json,sys;print(json.dumps(list(csv.DictReader(io.StringIO(sys.stdin.buffer.read().decode('utf-8-sig'))))))"],
                            input=(BASE / "official_village_directory.csv").read_bytes(), capture_output=True, check=True).stdout
    directory = pd.DataFrame(json.loads(parsed))
    usable = ~directory.village_code.duplicated(keep=False) & directory.village_code.str.fullmatch(r"[0-9]{8}").fillna(False)
    for field, width in [("province_code", 2), ("district_code", 4), ("commune_code", 6)]:
        usable &= directory.village_code.str[:width].eq(directory[field])
    report = json.loads((BASE / "summary.json").read_text())
    if int(usable.sum()) != report["directory_audit"]["usable_rows"]:
        raise ValueError("Reference filtering differs from previous test")
    row = next(r for r in report["waves"] if r["wave"] == "2004")
    matched = keys.admin4.isin(directory.loc[usable, "village_code"])
    excluded = keys.admin4.isin(directory.loc[~usable, "village_code"])
    row.update(roster_records=len(roster), complete_village_code_records=int(keys.admin4.notna().sum()),
               unique_source_village_codes=int(keys.admin4.nunique()), directory_code_matched_records=int(matched.sum()),
               directory_matched_unique_codes=int(keys.loc[matched, "admin4"].nunique()),
               directory_excluded_code_records=int(excluded.sum()))
    keys["directory_status"] = "not_in_usable_directory"
    keys.loc[matched, "directory_status"] = "unique_code_match_not_historical_identity"
    keys.loc[excluded, "directory_status"] = "excluded_reference_code"
    for level in [2, 3]:
        reference = json.loads((BASE / f"admin{level}_reference_snapshot.json").read_text())
        codes = {r[f"admin{level}_code"] for r in reference if r["geometry_geojson"].get("type") in {"Polygon", "MultiPolygon"}
                 and r["geometry_geojson"].get("coordinates")}
        keys[f"admin{level}_polygon_code_match"] = keys[f"admin{level}"].isin(codes)
        row[f"admin{level}_polygon_code_matched_records"] = int(keys[f"admin{level}_polygon_code_match"].sum())
    report["correction_2004"] = {"source_member": "2004hh_s99_singlequestions.dta", "source_fields": FIELDS,
        "household_rows": len(cover), "complete_household_rows": int(cover[FIELDS].notna().all(axis=1).sum()),
        "psu_count": int(linked.psu.nunique()), "psu_geography_conflicts": 0,
        "method": "Exact household-key join; no PSU imputation; all other waves retained from verified v1 snapshot.",
        "database_connection_opened": False}
    report["state"] = "local_2004_corrected_feasibility_not_published"
    aggregate = keys.groupby(list(keys.columns), dropna=False).size().reset_index(name="roster_records")
    artifacts = {"summary.json": put(OUT / "summary.json", encoded(report)),
                 "2004_geography_aggregate.json": put(OUT / "2004_geography_aggregate.json", encoded(aggregate.to_dict("records")))}
    put(OUT / "manifest.json", encoded({"artifacts": artifacts, "script_sha256": file_sha(Path(__file__)),
        "previous_manifest_sha256": file_sha(BASE / "manifest.json"), "source_archive_sha256": SHA,
        "key_helper_sha256": file_sha(ROOT / "rsc/cses_db/test_cses_geography_local.py")}))
    return row


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
