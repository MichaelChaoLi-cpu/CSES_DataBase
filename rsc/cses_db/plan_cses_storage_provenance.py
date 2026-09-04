#!/usr/bin/env python3
"""Create a deterministic, forced read-only CSES storage-provenance plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cses_baseline_metadata import canonical_sha256, connection_arguments
from cses_storage_provenance import (
    build_desired_state,
    connect_database,
    default_storage_provenance_spec_path,
    inspect_database,
    load_storage_provenance_spec,
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
    spec_path = args.spec or default_storage_provenance_spec_path(root)
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    spec = load_storage_provenance_spec(spec_path)
    output = (
        args.output
        or root / "data" / "processing" / "cses" / "storage_provenance_plan_v1.json"
    )
    if not output.is_absolute():
        output = root / output

    desired, diagnostics = build_desired_state(root, spec_path)
    arguments = connection_arguments(args.dbname or spec["database"], args.host, args.port, args.user)
    with connect_database(arguments) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            database_preflight = inspect_database(
                connection,
                desired,
                spec,
                diagnostics["source_dataset_outputs"],
            )

    checks = {**diagnostics["local_checks"], **database_preflight["checks"]}
    source_reference = {
        "mapping_version": spec["source_alignment_release"],
        "record_count": len(diagnostics["source_dataset_outputs"]),
        "canonical_sha256": canonical_sha256(diagnostics["source_dataset_outputs"]),
        "target_counts": diagnostics["source_output_counts"],
    }
    report = {
        "schema_version": 1,
        "provenance_release_id": spec["provenance_release_id"],
        "database_mutated": False,
        "explicit_write_approval_required": True,
        "approval_phrase": spec["approval_phrase"],
        "spec": diagnostics["spec"],
        "evidence": diagnostics["evidence"],
        "source_reference": source_reference,
        "target_relations": diagnostics["target_relations"],
        "external_dependencies": diagnostics["external_dependencies"],
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
    print(f"records={sum(diagnostics['record_counts'].values())} actions={database_preflight['action_counts']}")
    print(f"database_mutated=False preflight_ready={report['preflight_ready']}")
    if not report["preflight_ready"]:
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise SystemExit(f"Storage provenance preflight failed: {failed}")


if __name__ == "__main__":
    main()
