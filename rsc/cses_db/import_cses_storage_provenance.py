#!/usr/bin/env python3
"""Import the exact reviewed CSES storage-provenance plan in one transaction."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from cses_baseline_metadata import connection_arguments, normalize_json_value, sha256_file
from cses_storage_provenance import (
    apply_storage_provenance,
    build_desired_state,
    connect_database,
    default_storage_provenance_spec_path,
    load_storage_provenance_spec,
)

IMPLEMENTATION_PATHS = (
    "rsc/cses_db/cses_storage_provenance.py",
    "rsc/cses_db/import_cses_storage_provenance.py",
    "rsc/cses_db/plan_cses_storage_provenance.py",
    "rsc/specs/cses_storage_provenance_v1.json",
)


def validate_apply_gate(apply: bool, confirmation: str | None, spec: dict[str, Any]) -> None:
    if not apply:
        raise ValueError("Refusing database mutation without --apply")
    expected = spec["approval_phrase"]
    if confirmation != expected:
        raise ValueError(f"Refusing database mutation without --confirm {expected}")


def _without_code_revision(desired: dict[str, Any]) -> tuple[dict[str, Any], str]:
    copied = json.loads(json.dumps(normalize_json_value(desired)))
    revision = copied["load_runs"][0].pop("code_git_revision")
    return copied, revision


def validate_reviewed_plan(
    root: Path,
    plan_path: Path,
    spec: dict[str, Any],
    current_desired: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("provenance_release_id") != spec["provenance_release_id"]:
        raise ValueError("Reviewed plan release ID does not match the import specification")
    if plan.get("database_mutated") is not False or plan.get("preflight_ready") is not True:
        raise ValueError("Reviewed plan is not a successful non-mutating preflight")
    if plan.get("approval_phrase") != spec["approval_phrase"]:
        raise ValueError("Reviewed plan approval phrase does not match the import specification")
    if plan.get("desired_record_counts") != {
        "alignment_releases": 1,
        "dataset_outputs": 134,
        "load_runs": 1,
    }:
        raise ValueError("Reviewed plan does not contain the expected 136-record release")

    planned_desired = plan["desired_state"]
    comparable_plan, planned_revision = _without_code_revision(planned_desired)
    comparable_current, _ = _without_code_revision(current_desired)
    if comparable_plan != comparable_current:
        raise ValueError("Reviewed plan desired state differs from the current local evidence")

    subprocess.run(
        ["git", "merge-base", "--is-ancestor", planned_revision, "HEAD"],
        cwd=root,
        check=True,
    )
    for staged in (False, True):
        command = ["git", "diff", "--quiet"]
        if staged:
            command.append("--cached")
        command.extend([planned_revision, "--", *IMPLEMENTATION_PATHS])
        subprocess.run(command, cwd=root, check=True)
    return planned_desired, {
        "path": str(plan_path.relative_to(root)),
        "sha256": sha256_file(plan_path),
        "code_git_revision": planned_revision,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--plan", type=Path)
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
    spec_path = args.spec or default_storage_provenance_spec_path(root)
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    spec = load_storage_provenance_spec(spec_path)
    validate_apply_gate(args.apply, args.confirm, spec)
    current_desired, diagnostics = build_desired_state(root, spec_path)
    if not all(diagnostics["local_checks"].values()):
        failed = sorted(name for name, passed in diagnostics["local_checks"].items() if not passed)
        raise SystemExit(f"Local storage provenance checks failed: {failed}")
    plan_path = (
        args.plan
        or root / "data" / "processing" / "cses" / "storage_provenance_plan_v1.json"
    )
    if not plan_path.is_absolute():
        plan_path = root / plan_path
    desired, reviewed_plan = validate_reviewed_plan(root, plan_path, spec, current_desired)

    arguments = connection_arguments(args.dbname or spec["database"], args.host, args.port, args.user)
    with connect_database(arguments) as connection:
        with connection.transaction():
            result = apply_storage_provenance(
                connection,
                desired,
                spec,
                diagnostics["source_dataset_outputs"],
            )

    output = (
        args.output
        or root / "data" / "processing" / "cses" / "storage_provenance_import_v1.json"
    )
    if not output.is_absolute():
        output = root / output
    report = {
        "schema_version": 1,
        "provenance_release_id": spec["provenance_release_id"],
        "database": spec["database"],
        "spec": {"path": str(spec_path.relative_to(root)), "sha256": sha256_file(spec_path)},
        "reviewed_plan": reviewed_plan,
        **result,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"import_evidence={output.relative_to(root)}")
    print(f"database_mutated={result['database_mutated']} inserted={result['inserted_record_counts']}")


if __name__ == "__main__":
    main()
