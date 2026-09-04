#!/usr/bin/env python3
"""Compare local core CSES tables with the earlier MJ02b baseline release."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

TABLES = (
    "final_HH_CSES.parquet",
    "final_HL_CSES.parquet",
    "final_ED_CSES.parquet",
    "final_HO_CSES.parquet",
    "final_EC_CSES.parquet",
    "final_VL_CSES.parquet",
    "final_SURVEY_DATE_CSES.parquet",
)


def normalized(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.select_dtypes(include=["object", "string"]).columns:
        result[column] = result[column].str.replace("data/raw/CSE/", "data/raw/", regex=False)
    return result


def content_sha256(frame: pd.DataFrame) -> str:
    hashes = pd.util.hash_pandas_object(frame, index=False, categorize=True)
    return hashlib.sha256(hashes.to_numpy().tobytes()).hexdigest()


def compare(local_path: Path, reference_path: Path) -> dict[str, object]:
    local = normalized(pd.read_parquet(local_path))
    reference = normalized(pd.read_parquet(reference_path))
    columns_match = list(local.columns) == list(reference.columns)
    dtypes_match = [str(value) for value in local.dtypes] == [str(value) for value in reference.dtypes]
    rows_match = len(local) == len(reference)
    values_match = columns_match and rows_match and local.equals(reference)
    return {
        "table": local_path.name,
        "local_rows": len(local),
        "reference_rows": len(reference),
        "columns_match": columns_match,
        "dtypes_match": dtypes_match,
        "values_match_after_path_normalization": values_match,
        "local_content_sha256": content_sha256(local),
        "reference_content_sha256": content_sha256(reference),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--reference-root", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    local_dir = root / "data" / "processing" / "cses"
    reference_dir = args.reference_root.resolve() / "data" / "exp" / "database"

    results = []
    for name in TABLES:
        local_path = local_dir / name
        reference_path = reference_dir / name
        if not local_path.exists() or not reference_path.exists():
            raise FileNotFoundError(f"Missing comparison input: {local_path} or {reference_path}")
        results.append(compare(local_path, reference_path))

    report = {
        "schema_version": 1,
        "reference_release": "MJ02b:data/exp/database",
        "path_normalization": "data/raw/CSE/ -> data/raw/",
        "tables": results,
        "all_values_match": all(result["values_match_after_path_normalization"] for result in results),
    }
    output = local_dir / "reference_comparison.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"comparison={output.relative_to(root)} all_values_match={report['all_values_match']}")
    for result in results:
        print(
            f"{result['table']}: local_rows={result['local_rows']} "
            f"reference_rows={result['reference_rows']} "
            f"values_match={result['values_match_after_path_normalization']}"
        )
    if not report["all_values_match"]:
        raise SystemExit("Local release differs from the reference release")


if __name__ == "__main__":
    main()
