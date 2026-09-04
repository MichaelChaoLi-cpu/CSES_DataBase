#!/usr/bin/env python3
"""Compare CSES preflight and postflight evidence after a schema migration."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--postflight", type=Path, required=True)
    parser.add_argument("--backup-verification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def normalized_indexes(item: dict[str, Any]) -> list[dict[str, str]]:
    physical = item["physical"]
    schema = physical["schema"]
    return [
        {
            "name": index["name"],
            "definition": index["definition"].replace(f" ON {schema}.", " ON <physical>.", 1),
        }
        for index in physical["indexes"]
    ]


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    preflight_path = args.preflight if args.preflight.is_absolute() else root / args.preflight
    postflight_path = args.postflight if args.postflight.is_absolute() else root / args.postflight
    backup_path = (
        args.backup_verification if args.backup_verification.is_absolute() else root / args.backup_verification
    )
    output = args.output if args.output.is_absolute() else root / args.output
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    postflight = json.loads(postflight_path.read_text(encoding="utf-8"))
    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    pre_objects = {item["contract"]["name"]: item for item in preflight["objects"]}
    post_objects = {item["contract"]["name"]: item for item in postflight["objects"]}

    object_results = []
    for name in sorted(pre_objects):
        before = pre_objects[name]
        after = post_objects.get(name)
        physical_fields = (
            "oid",
            "relkind",
            "relpersistence",
            "owner",
            "total_bytes",
            "row_count",
            "column_count",
            "columns",
            "constraints",
            "grants",
        )
        comparisons = {
            field: after is not None and before["physical"][field] == after["physical"][field]
            for field in physical_fields
        }
        comparisons.update(
            {
                "contract": after is not None and before["contract"] == after["contract"],
                "indexes": after is not None and normalized_indexes(before) == normalized_indexes(after),
                "natural_key_audit": after is not None and before["natural_key_audit"] == after["natural_key_audit"],
                "compatibility_interface": after is not None
                and after["compatibility_interface"] is not None
                and after["compatibility_interface"]["columns_match_physical"],
            }
        )
        object_results.append(
            {
                "name": name,
                "target_schema": before["contract"]["target_schema"],
                "comparisons": comparisons,
                "passed": all(comparisons.values()),
            }
        )

    checks = {
        "backup_full_decompression_passed": backup["verification"]["pg_restore_full_decompression_passed"],
        "backup_mode_is_0600": backup["backup"]["mode"] == "0o600",
        "preflight_was_ready": preflight["layout"] == "public" and preflight["migration_ready"],
        "postflight_is_valid": postflight["layout"] == "functional" and postflight["post_migration_valid"],
        "contract_unchanged": preflight["contract"] == postflight["contract"],
        "protected_public_relations_unchanged": preflight["protected_public_relations"]
        == postflight["protected_public_relations"],
        "all_objects_preserved": all(result["passed"] for result in object_results),
    }
    report = {
        "schema_version": 1,
        "migration_name": preflight["migration_name"],
        "validation_passed": all(checks.values()),
        "checks": checks,
        "object_count": len(object_results),
        "objects": object_results,
        "evidence": {
            "preflight": {
                "path": str(preflight_path.relative_to(root)),
                "sha256": sha256_file(preflight_path),
            },
            "postflight": {
                "path": str(postflight_path.relative_to(root)),
                "sha256": sha256_file(postflight_path),
            },
            "backup_verification": {
                "path": str(backup_path.relative_to(root)),
                "sha256": sha256_file(backup_path),
                "backup_sha256": backup["backup"]["sha256"],
            },
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"validation={output.relative_to(root)}")
    print(f"objects={len(object_results)} validation_passed={report['validation_passed']}")
    if not report["validation_passed"]:
        failed = [name for name, passed in checks.items() if not passed]
        raise SystemExit(f"Schema migration validation failed: {failed}")


if __name__ == "__main__":
    main()
