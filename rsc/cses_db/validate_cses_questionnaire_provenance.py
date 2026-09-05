#!/usr/bin/env python3
"""Validate an imported CSES questionnaire provenance release read-only."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from cses_baseline_metadata import connection_arguments, sha256_file
from cses_questionnaire_provenance import (
    build_desired_state,
    connect_database,
    default_questionnaire_provenance_spec_path,
    inspect_database,
    load_questionnaire_provenance_spec,
)


def build_validation_checks(
    plan: dict[str, Any],
    plan_sha256: str,
    import_evidence: dict[str, Any],
    database_preflight: dict[str, Any],
) -> dict[str, bool]:
    expected_noops = sum(plan["desired_record_counts"].values())
    expected_inserts = {
        "alignment_releases": 1,
        "instruments": plan["desired_record_counts"]["instruments"],
        "questions": plan["desired_record_counts"]["questions"],
        "load_runs": 1,
    }
    return {
        "reviewed_plan_was_ready": plan.get("preflight_ready") is True,
        "reviewed_plan_was_non_mutating": plan.get("database_mutated") is False,
        "import_used_exact_reviewed_plan": import_evidence.get("reviewed_plan", {}).get("sha256") == plan_sha256,
        "import_code_revision_matches_plan": import_evidence.get("reviewed_plan", {}).get("code_git_revision")
        == plan["desired_state"]["load_runs"][0]["code_git_revision"],
        "all_reviewed_records_are_noops": database_preflight["action_counts"]
        == {"insert": 0, "update": 0, "noop": expected_noops, "conflict": 0},
        "all_database_checks_pass": all(database_preflight["checks"].values()),
        "import_inserted_expected_records": import_evidence["inserted_record_counts"] == expected_inserts,
        "import_updated_expected_source_links": import_evidence["updated_record_counts"]
        == {"source_variable_links": plan["desired_record_counts"]["source_variable_links"]},
        "import_reported_database_mutation": import_evidence.get("database_mutated") is True,
        "post_write_reconciled": import_evidence.get("post_write_action_counts")
        == {"insert": 0, "update": 0, "noop": expected_noops, "conflict": 0},
    }


def git_revision(root: Path) -> str:
    result = subprocess.run(
        [
            "git",
            "log",
            "-1",
            "--format=%H",
            "--",
            "rsc/cses_db/validate_cses_questionnaire_provenance.py",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    revision = result.stdout.strip()
    if not revision:
        raise RuntimeError("Questionnaire provenance validator is not committed in Git")
    return revision


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--import-evidence", type=Path)
    parser.add_argument("--dbname")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    spec_path = args.spec or default_questionnaire_provenance_spec_path(root)
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    spec = load_questionnaire_provenance_spec(spec_path)
    plan_path = args.plan or root / "data" / "processing" / "cses" / "questionnaire_provenance_plan_v1.json"
    import_path = (
        args.import_evidence or root / "data" / "processing" / "cses" / "questionnaire_provenance_import_v1.json"
    )
    if not plan_path.is_absolute():
        plan_path = root / plan_path
    if not import_path.is_absolute():
        import_path = root / import_path
    for name, path in (("plan", plan_path), ("import evidence", import_path)):
        if not path.is_file():
            raise SystemExit(f"Missing {name}: {path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    import_evidence = json.loads(import_path.read_text(encoding="utf-8"))
    desired, diagnostics = build_desired_state(root, spec_path)
    desired["load_runs"][0]["code_git_revision"] = plan["desired_state"]["load_runs"][0]["code_git_revision"]
    if desired != plan["desired_state"]:
        raise SystemExit("Current desired state differs from the reviewed questionnaire plan")
    arguments = connection_arguments(args.dbname or spec["database"], args.host, args.port, args.user)
    with connect_database(arguments) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            database_preflight = inspect_database(connection, desired, spec)
    checks = {
        **diagnostics["local_checks"],
        **build_validation_checks(plan, sha256_file(plan_path), import_evidence, database_preflight),
    }
    report = {
        "schema_version": 1,
        "catalog_release_id": spec["catalog_release_id"],
        "database_mutated": False,
        "validation_code_git_revision": git_revision(root),
        "plan": {"path": str(plan_path.relative_to(root)), "sha256": sha256_file(plan_path)},
        "import_evidence": {"path": str(import_path.relative_to(root)), "sha256": sha256_file(import_path)},
        "database_validation": database_preflight,
        "checks": checks,
        "validation_passed": all(checks.values()),
    }
    output = args.output or root / "data" / "processing" / "cses" / "questionnaire_provenance_validation_v1.json"
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"validation={output.relative_to(root)} passed={report['validation_passed']}")
    if not report["validation_passed"]:
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise SystemExit(f"Questionnaire provenance validation failed: {failed}")


if __name__ == "__main__":
    main()
