#!/usr/bin/env python3
"""Read-only database / official gazetteer geography feasibility test; local output only."""
from __future__ import annotations

import io
import json
import subprocess
import zipfile
from pathlib import Path

import pandas as pd
import psycopg
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data/processing/cses/geography_feasibility_v1"
URL = "https://data.mef.gov.kh/api/v1/public-datasets/pd_66a8603a00604c000123e147/file"


def code_components(frame, columns):
    parts = []
    for column in columns:
        raw = frame[column]
        number = pd.to_numeric(raw, errors="coerce")
        if (raw.notna() & (~number.between(0, 99) | number.mod(1).ne(0))).any():
            raise ValueError(f"Not a two-digit local component: {column}")
        parts.append(number.astype("Int64").astype("string").str.zfill(2))
    result = pd.DataFrame(index=frame.index)
    for level in range(1, 5):
        value = parts[0].copy()
        for part in parts[1:level]:
            value = value + part
        result[f"admin{level}"] = value
    return result


def build():
    source = OUTPUT / "official_village_directory.csv"
    if source.exists():
        payload = source.read_bytes()
    else:
        payload = subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error", "--max-time", "30", URL],
                                 check=True, capture_output=True).stdout
    # Use the bundled document runtime to parse the source CSV as strings. The
    # remaining repository analysis consumes JSON, never inferred numeric codes.
    parser = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
    parsed = subprocess.run([str(parser), "-c", "import csv,io,json,sys; print(json.dumps(list(csv.DictReader(io.StringIO(sys.stdin.buffer.read().decode('utf-8-sig'))))))"],
                            input=payload, check=True, capture_output=True).stdout
    directory = pd.DataFrame(json.loads(parsed))
    if len(directory) != 14576:
        raise ValueError("Directory count differs from observed official API total 14576")
    duplicate = directory.village_code.duplicated(keep=False)
    valid_format = directory.village_code.str.fullmatch(r"[0-9]{8}").fillna(False)
    hierarchy = pd.Series(True, index=directory.index)
    for parent, length in [("province_code", 2), ("district_code", 4), ("commune_code", 6)]:
        hierarchy &= directory.village_code.str[:length].eq(directory[parent])
    usable = ~duplicate & valid_format & hierarchy
    accepted_codes = set(directory.loc[usable, "village_code"])
    excluded_codes = set(directory.loc[~usable, "village_code"])
    directory_audit = {"usable_rows": int(usable.sum()), "excluded_rows": int((~usable).sum()),
                       "duplicate_code_count": int(directory.loc[duplicate, "village_code"].nunique()),
                       "duplicate_rows": int(duplicate.sum()), "invalid_format_rows": int((~valid_format).sum()),
                       "inconsistent_parent_rows": int((~hierarchy).sum())}
    put(source, payload)
    snapshots = {}
    with psycopg.connect(dbname="mda", connect_timeout=5,
                         options="-c default_transaction_read_only=on -c statement_timeout=60000") as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        if conn.execute("show transaction_read_only").fetchone()[0] != "on":
            raise ValueError("Database transaction must be read only")
        def query(statement):
            cursor = conn.execute(statement)
            return pd.DataFrame(cursor.fetchall(), columns=[c.name for c in cursor.description])
        legacy = query('select survey_wave,province_code,district_code,commune_code,village_code,count(*) as respondents from cses_data."final_HL_CSES" group by 1,2,3,4,5')
        for level in [2, 3]:
            snapshots[str(level)] = query(f'select admin{level}_code,admin1_code,geometry_geojson,boundary_date,valid_on from public.dim_admin{level}_cambodia')
        conn.rollback()
    spatial_codes = {}
    spatial_metadata = {}
    for level, frame in snapshots.items():
        key = f"admin{level}_code"
        if frame[key].duplicated().any():
            raise ValueError("Ambiguous spatial code")
        geometry = frame.geometry_geojson.map(lambda s: json.loads(s) if isinstance(s, str) else s)
        valid = geometry.map(lambda g: isinstance(g, dict) and g.get("type") in {"Polygon", "MultiPolygon"}
                             and bool(g.get("coordinates")))
        spatial_codes[level] = set(frame.loc[valid, key])
        spatial_metadata[level] = {"rows": len(frame), "nonempty_polygon_rows": int(valid.sum()),
            "boundary_dates": sorted(str(x) for x in frame.boundary_date.unique()),
            "valid_on": sorted(str(x) for x in frame.valid_on.unique())}
        frame["geometry_geojson"] = geometry
        for field in ["boundary_date", "valid_on"]:
            frame[field] = frame[field].astype(str)
        put(OUTPUT / f"admin{level}_reference_snapshot.json", encoded(frame.to_dict("records")))
    frames = {}
    for wave, frame in legacy.groupby("survey_wave"):
        frame = frame.reset_index(drop=True)
        frames[wave] = (code_components(frame, ["province_code", "district_code", "commune_code", "village_code"]), frame.respondents)
    spec = json.loads((ROOT / "rsc/specs/cses_additional_waves_v1.json").read_text())
    archive_hashes = {}
    for wave, cfg in spec["waves"].items():
        archive = ROOT / cfg["archive"]
        if file_sha(archive) != cfg["sha256"]:
            raise ValueError("Additional-wave archive changed")
        archive_hashes[wave] = cfg["sha256"]
        columns = (["pro", "dis", "com", "vil"] if wave in {"1997", "1999"}
                   else ["province_id", "district_id", "commune_id", "village_id"] if wave == "2025"
                   else ["province", "district", "commune", "village"])
        with zipfile.ZipFile(archive) as z:
            frame = pd.read_stata(io.BytesIO(z.read(cfg["modules"]["HL"]["member"])),
                                  columns=columns, convert_categoricals=False)
        frames[wave] = (code_components(frame, columns), pd.Series(1, index=frame.index))
    records = []
    for wave, (keys, weights) in sorted(frames.items()):
        n = int(weights.sum())
        match = keys.admin4.isin(accepted_codes)
        row = {"wave": wave, "roster_records": n,
               "complete_village_code_records": int(weights[keys.admin4.notna()].sum()),
               "unique_source_village_codes": int(keys.admin4.nunique()),
               "directory_code_matched_records": int(weights[match].sum()),
               "directory_matched_unique_codes": int(keys.loc[match, "admin4"].nunique()),
               "directory_excluded_code_records": int(weights[keys.admin4.isin(excluded_codes)].sum()),
               "village_geometry_status": "not_testable_no_verified_village_geometry_reference",
               "historical_identity_status": "not_verified_code_equality_only"}
        for level in [2, 3]:
            row[f"admin{level}_polygon_code_matched_records"] = int(weights[keys[f"admin{level}"].isin(spatial_codes[str(level)])].sum())
        records.append(row)
    put(OUTPUT / "legacy_aggregate_input.json", encoded(json.loads(legacy.sort_values(
        ["survey_wave", "province_code", "district_code", "commune_code", "village_code"]).to_json(orient="records"))))
    report = {"state": "local_feasibility_test_not_published", "database_modified": False,
              "directory_url": URL, "directory_rows": len(directory), "directory_columns": directory.columns.tolist(),
              "directory_audit": directory_audit,
              "spatial_references": spatial_metadata, "waves": records,
              "limitations": ["Roster members, not distinct humans across years.", "Code equality is not historical identity verification.",
                              "No fuzzy-name matching, no village coordinates inferred from commune polygons.",
                              "Polygon presence checked; geometric validity and historical boundary equivalence not certified."]}
    put(OUTPUT / "summary.json", encoded(report))
    artifacts = {p.name: file_sha(p) for p in sorted(OUTPUT.iterdir()) if p.name != "manifest.json" and p.is_file()}
    put(OUTPUT / "manifest.json", encoded({"artifacts": artifacts, "script_sha256": file_sha(Path(__file__)),
                                           "additional_archive_sha256": archive_hashes}))
    return report


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
