#!/usr/bin/env python3
"""Import the reviewed CSES baseline metadata in one guarded transaction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cses_baseline_metadata import (
    apply_baseline_metadata,
    build_desired_state,
    connect_database,
    connection_arguments,
    default_baseline_spec_path,
    load_baseline_spec,
    sha256_file,
)


def validate_apply_gate(apply: bool, confirmation: str | None, spec: dict[str, Any]) -> None:
    if not apply:
        raise ValueError("Refusing database mutation without --apply")
    expected = spec["approval_phrase"]
    if confirmation != expected:
        raise ValueError(f"Refusing database mutation without --confirm {expected}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--dbname")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    spec_path = args.spec or default_baseline_spec_path(root)
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    spec = load_baseline_spec(spec_path)
    validate_apply_gate(args.apply, args.confirm, spec)
    desired, diagnostics = build_desired_state(root, spec_path)
    if not all(diagnostics["local_checks"].values()):
        failed = sorted(name for name, passed in diagnostics["local_checks"].items() if not passed)
        raise SystemExit(f"Local baseline metadata checks failed: {failed}")

    arguments = connection_arguments(args.dbname or spec["database"], args.host, args.port, args.user)
    with connect_database(arguments) as connection:
        with connection.transaction():
            result = apply_baseline_metadata(connection, desired, spec["baseline_id"])

    output = args.output or root / "data" / "processing" / "cses" / "baseline_metadata_import_v1.json"
    if not output.is_absolute():
        output = root / output
    report = {
        "schema_version": 1,
        "baseline_id": spec["baseline_id"],
        "database": spec["database"],
        "spec": {
            "path": str(spec_path.relative_to(root)),
            "sha256": sha256_file(spec_path),
        },
        **result,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"import_evidence={output.relative_to(root)}")
    print(f"database_mutated={result['database_mutated']} inserted={result['inserted_record_counts']}")


if __name__ == "__main__":
    main()
