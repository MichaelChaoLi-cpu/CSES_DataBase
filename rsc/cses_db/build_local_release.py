#!/usr/bin/env python3
"""Build and validate the local CSES baseline without writing PostgreSQL."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pyarrow.parquet as pq

BUILD_SCRIPTS = (
    "build_cses_hl.py",
    "build_cses_ed.py",
    "build_cses_hh.py",
    "build_cses_ho.py",
    "build_cses_ec.py",
    "build_cses_vl.py",
    "build_cses_survey_dates.py",
)

BUILD_OUTPUTS = {
    "build_cses_hl.py": "final_HL_CSES.parquet",
    "build_cses_ed.py": "final_ED_CSES.parquet",
    "build_cses_hh.py": "final_HH_CSES.parquet",
    "build_cses_ho.py": "final_HO_CSES.parquet",
    "build_cses_ec.py": "final_EC_CSES.parquet",
    "build_cses_vl.py": "final_VL_CSES.parquet",
    "build_cses_survey_dates.py": "final_SURVEY_DATE_CSES.parquet",
}

VALIDATION_SCRIPTS = (
    "validate_cses_hh_hl.py",
    "validate_cses_ed.py",
    "validate_cses_ho.py",
    "validate_cses_ec.py",
    "validate_cses_vl.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], root: Path) -> None:
    print(f"running={' '.join(command)}", flush=True)
    subprocess.run(command, cwd=root, check=True)


def release_manifest(root: Path) -> dict[str, object]:
    output = root / "data" / "processing" / "cses"
    archives = []
    for path in sorted((root / "data" / "raw").glob("*.zip")):
        archives.append(
            {
                "path": str(path.relative_to(root)),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    artifacts = []
    for path in sorted(output.iterdir()):
        if not path.is_file() or path.name == "local_release_manifest.json":
            continue
        record: dict[str, object] = {
            "path": str(path.relative_to(root)),
            "size": path.stat().st_size,
            "sha256": sha256(path),
        }
        if path.suffix == ".parquet":
            metadata = pq.ParquetFile(path).metadata
            record["rows"] = metadata.num_rows
            record["columns"] = metadata.num_columns
        artifacts.append(record)

    return {
        "schema_version": 1,
        "database_writes": False,
        "raw_archives": archives,
        "artifacts": artifacts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--reference-root",
        type=Path,
        help="Optional earlier project root containing data/exp/database for content comparison.",
    )
    parser.add_argument("--skip-inventory", action="store_true")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip a build step when its expected Parquet output already exists.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    scripts = Path(__file__).resolve().parent

    if not args.skip_inventory:
        run(
            [
                sys.executable,
                str(scripts / "inventory_cses_archives.py"),
                "--root",
                str(root),
                "--pretty",
            ],
            root,
        )

    output = root / "data" / "processing" / "cses"
    for script in BUILD_SCRIPTS:
        expected = output / BUILD_OUTPUTS[script]
        if args.resume and expected.exists():
            print(f"skipping={script} existing={expected.relative_to(root)}", flush=True)
            continue
        run([sys.executable, str(scripts / script)], root)
    for script in VALIDATION_SCRIPTS:
        run([sys.executable, str(scripts / script)], root)

    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "local_release_manifest.json"
    manifest_path.write_text(
        json.dumps(release_manifest(root), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"manifest={manifest_path.relative_to(root)}", flush=True)

    if args.reference_root is not None:
        run(
            [
                sys.executable,
                str(scripts / "compare_reference_release.py"),
                "--root",
                str(root),
                "--reference-root",
                str(args.reference_root.resolve()),
            ],
            root,
        )


if __name__ == "__main__":
    main()
