#!/usr/bin/env python3
"""Create a deterministic, forced read-only CSES variable-catalog plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cses_baseline_metadata import connection_arguments
from cses_variable_catalog import (
    build_desired_state,
    connect_database,
    default_variable_catalog_spec_path,
    inspect_database,
    load_variable_catalog_spec,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--dbname")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    spec_path = args.spec or default_variable_catalog_spec_path(root)
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    spec = load_variable_catalog_spec(spec_path)
    output = args.output or root / "data" / "processing" / "cses" / "variable_catalog_plan_v1.json"
    if not output.is_absolute():
        output = root / output

    desired, diagnostics = build_desired_state(root, spec_path)
    arguments = connection_arguments(args.dbname or spec["database"], args.host, args.port, args.user)
    with connect_database(arguments) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            database_preflight = inspect_database(connection, desired, spec)

    checks = {**diagnostics["local_checks"], **database_preflight["checks"]}
    report = {
        "schema_version": 1,
        "catalog_release_id": spec["catalog_release_id"],
        "database_mutated": False,
        "explicit_write_approval_required": True,
        "approval_phrase": spec["approval_phrase"],
        "spec": diagnostics["spec"],
        "evidence": diagnostics["evidence"],
        "scope_counts": diagnostics["scope_counts"],
        "mapping_counts_by_target": diagnostics["mapping_counts_by_target"],
        "source_variable_counts_by_wave": diagnostics["source_variable_counts_by_wave"],
        "desired_record_counts": diagnostics["record_counts"],
        "desired_state": desired,
        "database_preflight": database_preflight,
        "checks": checks,
        "preflight_ready": all(checks.values()),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    display_path = output.relative_to(root) if output.is_relative_to(root) else output
    print(f"plan={display_path}")
    print(
        f"records={sum(diagnostics['record_counts'].values())} "
        f"actions={database_preflight['action_counts']}"
    )
    print(f"database_mutated=False preflight_ready={report['preflight_ready']}")
    if not report["preflight_ready"]:
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise SystemExit(f"Variable catalog preflight failed: {failed}")


if __name__ == "__main__":
    main()
