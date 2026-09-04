#!/usr/bin/env python3
"""Validate the imported CSES baseline metadata against its reviewed plan."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from cses_baseline_metadata import connect_database, connection_arguments, inspect_database, sha256_file


def build_validation_checks(
    plan: dict[str, Any],
    plan_sha256: str,
    import_evidence: dict[str, Any],
    database_preflight: dict[str, Any],
) -> dict[str, bool]:
    desired_counts = plan["desired_record_counts"]
    desired_total = sum(desired_counts.values())
    actions = database_preflight["action_counts"]
    return {
        "reviewed_plan_was_ready": plan.get("preflight_ready") is True,
        "reviewed_plan_was_non_mutating": plan.get("database_mutated") is False,
        "import_used_reviewed_plan_sha256": import_evidence["reviewed_plan"]["sha256"] == plan_sha256,
        "import_used_reviewed_plan_revision": import_evidence["reviewed_plan"]["code_git_revision"]
        == plan["desired_state"]["load_runs"][0]["code_git_revision"],
        "import_record_counts_match_plan": import_evidence["inserted_record_counts"] == desired_counts,
        "import_reported_database_mutation": import_evidence.get("database_mutated") is True,
        "import_transaction_reconciled_to_noops": import_evidence["post_write_action_counts"]
        == {"conflict": 0, "insert": 0, "noop": desired_total},
        "validation_transaction_is_read_only": database_preflight["checks"]["transaction_is_read_only"],
        "database_preflight_checks_pass": all(database_preflight["checks"].values()),
        "all_reviewed_records_are_noops": actions == {"conflict": 0, "insert": 0, "noop": desired_total},
        "database_record_counts_match_plan": database_preflight["existing_record_counts"] == desired_counts,
    }


def git_revision(root: Path) -> str:
    result = subprocess.run(
        [
            "git",
            "log",
            "-1",
            "--format=%H",
            "--",
            "rsc/cses_db/validate_cses_baseline_metadata.py",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    revision = result.stdout.strip()
    if not revision:
        raise RuntimeError("Validator code is not committed in Git")
    return revision


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--import-evidence", type=Path)
    parser.add_argument("--dbname", default="mda")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    plan_path = args.plan or root / "data" / "processing" / "cses" / "baseline_metadata_plan_v1.json"
    import_path = (
        args.import_evidence
        or root / "data" / "processing" / "cses" / "baseline_metadata_import_v1.json"
    )
    output = args.output or root / "data" / "processing" / "cses" / "baseline_metadata_validation_v1.json"
    plan_path = plan_path if plan_path.is_absolute() else root / plan_path
    import_path = import_path if import_path.is_absolute() else root / import_path
    output = output if output.is_absolute() else root / output

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    import_evidence = json.loads(import_path.read_text(encoding="utf-8"))
    desired = plan["desired_state"]
    arguments = connection_arguments(args.dbname, args.host, args.port, args.user)
    with connect_database(arguments) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            database_preflight = inspect_database(connection, desired, plan["baseline_id"])

    plan_sha256 = sha256_file(plan_path)
    checks = build_validation_checks(plan, plan_sha256, import_evidence, database_preflight)
    report = {
        "schema_version": 1,
        "baseline_id": plan["baseline_id"],
        "database_mutated": False,
        "validation_passed": all(checks.values()),
        "validation_code_git_revision": git_revision(root),
        "checks": checks,
        "reviewed_plan": {
            "path": str(plan_path.relative_to(root)),
            "sha256": plan_sha256,
            "code_git_revision": desired["load_runs"][0]["code_git_revision"],
        },
        "import_evidence": {
            "path": str(import_path.relative_to(root)),
            "sha256": sha256_file(import_path),
        },
        "database_preflight": database_preflight,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"validation={output.relative_to(root)}")
    print(f"actions={database_preflight['action_counts']} database_mutated=False")
    print(f"validation_passed={report['validation_passed']}")
    if not report["validation_passed"]:
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise SystemExit(f"Baseline metadata validation failed: {failed}")


if __name__ == "__main__":
    main()
