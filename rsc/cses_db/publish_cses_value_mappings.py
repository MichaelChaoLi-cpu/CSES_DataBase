#!/usr/bin/env python3
"""Back up, prepare, publish and independently validate the approved value dictionary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from correct_cses_housing_lighting import compare_database_to_local, database_snapshot, write_json
from cses_baseline_metadata import canonical_sha256, connect_database, sha256_file
from plan_cses_value_mapping_release import (
    approved_rows,
    database_plan,
    load_context,
    verify_questionnaire_options,
)
from psycopg import sql
from psycopg.types.json import Jsonb
from record_cses_value_mapping_decisions import require

RELEASE = "cses-housing-value-mapping-v1"
PLAN = "data/processing/cses/value_mapping_release_v1/plan.json"
PLAN_SHA = "2f6fdca4705af007cdc982c71044adeada9fc54b97a40620d2871d3cc9577209"
DIRECTORY = f"data/releases/{RELEASE}"
SELF = "rsc/cses_db/publish_cses_value_mappings.py"
TABLES = (("cses_meta", "cses_alignment_release"), ("cses_alignment", "cses_variable_mapping"),
          ("cses_alignment", "cses_value_mapping"), ("cses_meta", "cses_load_run"))
COUNTS = {"alignment_releases": 1, "variable_mappings": 21, "value_mappings": 140, "load_runs": 1}


def frozen_plan(root: Path) -> dict:
    require(sha256_file(root / PLAN) == PLAN_SHA, "Reviewed plan hash differs")
    plan = json.loads((root / PLAN).read_text())
    require(plan["release_id"] == RELEASE and plan["semantic_status"] == "approved" and plan["preflight_passed"],
            "Wrong or unapproved plan")
    for path, digest in plan["provenance"]["implementation_sha256"].items():
        require(sha256_file(root / path) == digest, f"Planned implementation changed: {path}")
    return plan


def digest_excluding_release(connection, schema: str, table: str) -> dict:
    if table == "cses_alignment_release":
        predicate = sql.SQL("t.mapping_version <> %s")
    elif table == "cses_value_mapping":
        predicate = sql.SQL("t.variable_mapping_id NOT IN (SELECT m.variable_mapping_id FROM "
                            "cses_alignment.cses_variable_mapping m JOIN cses_meta.cses_alignment_release r "
                            "USING(alignment_release_id) WHERE r.mapping_version=%s)")
    else:
        predicate = sql.SQL("t.alignment_release_id IS NULL OR t.alignment_release_id NOT IN "
                            "(SELECT alignment_release_id FROM cses_meta.cses_alignment_release WHERE mapping_version=%s)")
    return connection.execute(sql.SQL("SELECT count(*) AS row_count, encode(sha256(convert_to("
        "coalesce(string_agg(h, '' ORDER BY h), ''), 'UTF8')), 'hex') AS sha256 FROM "
        "(SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')), 'hex') AS h FROM {} t WHERE {}) rows"
        ).format(sql.Identifier(schema, table), predicate), (RELEASE,)).fetchone()


def protected_snapshot(connection, correction: dict) -> tuple[dict, str]:
    snapshot = database_snapshot(connection, correction)
    original_hash = canonical_sha256(snapshot)
    require(len(snapshot["protected_relations"]) == 35, "Protected table set changed")
    for relation in snapshot["protected_relations"]:
        name = (relation["schema_name"], relation["table_name"])
        if name in TABLES:
            relation.update(digest_excluding_release(connection, *name))
    return snapshot, original_hash


def assert_protected(actual: dict, expected: dict) -> None:
    require(actual == expected, "Protected database content, structure or compatibility changed")


def read_only(connection) -> None:
    connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    connection.execute("SET LOCAL statement_timeout='55s'")
    require(connection.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on", "Read-only required")


def backup(root: Path, directory: Path, backup_dir: Path) -> None:
    frozen_plan(root)
    require(backup_dir.is_dir(), "Backup directory must already exist")
    require(not (directory / "backup.json").exists(), "Scoped backup already recorded")
    fd, name = tempfile.mkstemp(prefix=f"mda_{RELEASE}_", suffix=".dump", dir=backup_dir)
    os.close(fd)
    path = Path(name)
    path.chmod(0o600)
    args = ["pg_dump", "-d", "mda", "--format=custom", "--compress=6", f"--file={path}"]
    args += [f'--table={schema}."{table}"' for schema, table in TABLES]
    subprocess.run(args, check=True)
    toc = subprocess.run(["pg_restore", "--list", str(path)], check=True, capture_output=True, text=True).stdout
    for schema, table in TABLES:
        require(f"TABLE DATA {schema} {table} " in toc, f"Backup table data missing: {table}")
    subprocess.run(["pg_restore", "--file=/dev/null", str(path)], check=True)
    require(path.stat().st_size > 0, "Empty backup")
    write_json(directory / "backup.json", {"path": str(path), "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size, "tables": [list(t) for t in TABLES],
        "toc_verified": True, "full_decompression_verified": True, "database_mutated": False,
        "scope": "Four affected metadata tables only; not a full mda backup"})
    print(f"backup_verified=True path={path}", flush=True)


def checked_backup(directory: Path) -> dict:
    record = json.loads((directory / "backup.json").read_text())
    require(record["tables"] == [list(t) for t in TABLES], "Wrong backup scope")
    require(record["toc_verified"] and record["full_decompression_verified"], "Unverified backup")
    require(sha256_file(Path(record["path"])) == record["sha256"], "External backup hash differs")
    return record


def prepare(root: Path, directory: Path) -> None:
    plan = frozen_plan(root)
    spec, context, evidence = load_context(root)
    rows = approved_rows(spec, context)
    require(rows == plan["approved_rows"], "Approved decisions differ")
    verify_questionnaire_options(root, rows, evidence["audit_spec"])
    require(database_plan(root, spec, context, evidence, rows) == plan["database_plan"], "Fresh database preflight differs")
    print("fresh_preflight_passed=True; recording execution state", flush=True)
    record = checked_backup(directory)
    paths = sorted(set(plan["provenance"]["implementation_sha256"]) | {SELF})
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    hashes = {p: sha256_file(root / p) for p in paths}
    for path in paths:
        committed = subprocess.run(["git", "show", f"{revision}:{path}"], cwd=root, check=True, capture_output=True).stdout
        require(hashlib.sha256(committed).hexdigest() == hashes[path], f"Uncommitted execution code: {path}")
    with connect_database({"dbname": "mda"}) as connection:
        read_only(connection)
        snapshot, baseline_hash = protected_snapshot(connection, evidence["correction_spec"])
        require(baseline_hash == plan["database_plan"]["baseline_snapshot_sha256"], "Baseline changed during preparation")
    dvc_hash = re.search(r"md5: ([0-9a-f]{32}\.dir)", (root / "data.dvc").read_text()).group(1)
    write_json(directory / "execution.json", {"release_id": RELEASE, "execution_ready": True,
        "reviewed_plan_sha256": PLAN_SHA, "backup_evidence_sha256": sha256_file(directory / "backup.json"),
        "backup_sha256": record["sha256"], "code_git_revision": revision, "implementation_sha256": hashes,
        "source_data_dvc_revision": f"md5:{dvc_hash}", "protected_before": snapshot,
        "approved_record_counts": COUNTS, "database_mutated": False,
        "execution_approval": "User instructed execution of archive, backup, transaction, validation and lineage workflow."})
    print(f"execution_ready=True execution_sha256={sha256_file(directory / 'execution.json')}", flush=True)


def inputs(root: Path, directory: Path) -> tuple[dict, dict, str, dict]:
    plan = frozen_plan(root)
    manifest = json.loads((directory / "execution.json").read_text())
    require(manifest["release_id"] == RELEASE and manifest["reviewed_plan_sha256"] == PLAN_SHA
            and manifest["execution_ready"], "Wrong execution manifest")
    require(manifest["approved_record_counts"] == COUNTS, "Execution count scope differs")
    require(sha256_file(directory / "backup.json") == manifest["backup_evidence_sha256"], "Backup record changed")
    for path, digest in manifest["implementation_sha256"].items():
        require(sha256_file(root / path) == digest, f"Execution implementation changed: {path}")
    subprocess.run(["git", "merge-base", "--is-ancestor", manifest["code_git_revision"], "HEAD"], cwd=root, check=True)
    spec, context, evidence = load_context(root)
    require(approved_rows(spec, context) == plan["approved_rows"], "Approved source decisions changed")
    return plan, manifest, sha256_file(directory / "execution.json"), evidence["correction_spec"]


def expected_records(plan: dict, manifest: dict, manifest_hash: str) -> dict:
    mappings, values = [], []
    lineage = []
    for entry in plan["database_plan"]["planned_variable_mappings"]:
        m = entry["planned_mapping"]
        mappings.append({k: v for k, v in m.items() if k != "mapping_version"})
        for value in entry["value_mappings"]:
            values.append({"dataset_id": m["dataset_id"], "canonical_variable_id": m["canonical_variable_id"],
                           **{k: v for k, v in value.items() if k != "review_row_id"}})
        lineage.append({"dataset_id": m["dataset_id"], "canonical_variable_id": m["canonical_variable_id"],
                        "previous_variable_mapping_id": entry["previous_mapping"]["variable_mapping_id"],
                        "previous_mapping_version": entry["previous_mapping"]["mapping_version"]})
    return {"release": {"mapping_version": RELEASE, "status": "approved",
                        "description": "Approved housing source-code semantic dictionary: 140 values across 21 versioned source rules; physical data unchanged.",
                        "specification_sha256": plan["provenance"]["spec_sha256"]},
            "mappings": sorted(mappings, key=canonical_sha256), "values": sorted(values, key=canonical_sha256),
            "run": {"run_scope": RELEASE, "source_manifest_sha256": PLAN_SHA,
                    "code_git_revision": manifest["code_git_revision"], "dvc_revision": manifest["source_data_dvc_revision"],
                    "status": "loaded", "row_counts": COUNTS,
                    "validation_summary": {"execution_sha256": manifest_hash, "backup_sha256": manifest["backup_sha256"],
                        "reviewed_plan_sha256": PLAN_SHA, "protected_before_sha256": canonical_sha256(manifest["protected_before"]),
                        "physical_data_unchanged": True, "source_rule_provenance": lineage,
                        "interpretation_notes": plan["interpretation_notes"], "excluded_by_bucket": plan["excluded_by_bucket"]}}}


def existing_records(connection) -> dict | None:
    release = connection.execute("SELECT alignment_release_id,mapping_version,status,description,"
        "specification_sha256::text FROM cses_meta.cses_alignment_release WHERE mapping_version=%s", (RELEASE,)).fetchone()
    if release is None:
        return None
    identity = release.pop("alignment_release_id")
    mappings = connection.execute("SELECT dataset_id,canonical_variable_id,source_variable_names,source_kind,"
        "transformation_rule,alignment_status FROM cses_alignment.cses_variable_mapping WHERE alignment_release_id=%s",
        (identity,)).fetchall()
    values = connection.execute("SELECT m.dataset_id,m.canonical_variable_id,v.source_value,v.source_label,"
        "v.canonical_value,v.canonical_label,v.alignment_status FROM cses_alignment.cses_value_mapping v "
        "JOIN cses_alignment.cses_variable_mapping m USING(variable_mapping_id) WHERE m.alignment_release_id=%s",
        (identity,)).fetchall()
    runs = connection.execute("SELECT run_scope,source_manifest_sha256::text,code_git_revision,dvc_revision,status,"
        "row_counts,validation_summary FROM cses_meta.cses_load_run WHERE alignment_release_id=%s AND finished_at IS NOT NULL",
        (identity,)).fetchall()
    all_run_count = connection.execute("SELECT count(*) AS n FROM cses_meta.cses_load_run WHERE alignment_release_id=%s",
                                       (identity,)).fetchone()["n"]
    require(len(runs) == all_run_count == 1, "Unexpected or unfinished release load runs")
    require(connection.execute("SELECT approved_at IS NOT NULL AS ok FROM cses_meta.cses_alignment_release "
                               "WHERE alignment_release_id=%s", (identity,)).fetchone()["ok"], "Release not approved")
    return {"release": release, "mappings": sorted(mappings, key=canonical_sha256),
            "values": sorted(values, key=canonical_sha256), "run": runs[0]}


def insert_records(connection, desired: dict) -> None:
    r = desired["release"]
    identity = connection.execute("INSERT INTO cses_meta.cses_alignment_release "
        "(mapping_version,status,description,specification_sha256,approved_at) VALUES (%s,%s,%s,%s,now()) "
        "RETURNING alignment_release_id", tuple(r[k] for k in ("mapping_version","status","description","specification_sha256"))
    ).fetchone()["alignment_release_id"]
    ids = {}
    for m in desired["mappings"]:
        mid = connection.execute("INSERT INTO cses_alignment.cses_variable_mapping "
            "(dataset_id,canonical_variable_id,source_variable_names,source_kind,transformation_rule,alignment_status,"
            "alignment_release_id) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING variable_mapping_id",
            tuple(m[k] for k in ("dataset_id","canonical_variable_id","source_variable_names","source_kind",
                                "transformation_rule","alignment_status")) + (identity,)).fetchone()["variable_mapping_id"]
        ids[(m["dataset_id"], m["canonical_variable_id"])] = mid
    for v in desired["values"]:
        connection.execute("INSERT INTO cses_alignment.cses_value_mapping "
            "(variable_mapping_id,source_value,source_label,canonical_value,canonical_label,alignment_status) "
            "VALUES (%s,%s,%s,%s,%s,%s)", (ids[(v["dataset_id"],v["canonical_variable_id"])],) +
            tuple(v[k] for k in ("source_value","source_label","canonical_value","canonical_label","alignment_status")))
    run = desired["run"]
    connection.execute("INSERT INTO cses_meta.cses_load_run "
        "(alignment_release_id,run_scope,source_manifest_sha256,code_git_revision,dvc_revision,status,row_counts,"
        "validation_summary,finished_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now())", (identity,) +
        tuple(run[k] for k in ("run_scope","source_manifest_sha256","code_git_revision","dvc_revision","status")) +
        (Jsonb(run["row_counts"]), Jsonb(run["validation_summary"])))


def apply(root: Path, directory: Path, confirmation: str) -> None:
    plan, manifest, manifest_hash, correction = inputs(root, directory)
    require(confirmation == manifest_hash, "Exact execution hash required")
    require(checked_backup(directory)["sha256"] == manifest["backup_sha256"], "Backup binding differs")
    desired = expected_records(plan, manifest, manifest_hash)
    with connect_database({"dbname": "mda"}) as connection:
        with connection.transaction():
            connection.execute("SET LOCAL lock_timeout='15s'")
            connection.execute("SET LOCAL statement_timeout='55s'")
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (RELEASE,))
            for relation in manifest["protected_before"]["protected_relations"]:
                connection.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(
                    sql.Identifier(relation["schema_name"], relation["table_name"])))
            for schema, table in TABLES:
                require(not connection.execute("SELECT 1 FROM pg_trigger WHERE tgrelid=%s::regclass AND NOT tgisinternal",
                            (f'{schema}."{table}"',)).fetchone(), "Unexpected user trigger on metadata target")
            assert_protected(protected_snapshot(connection, correction)[0], manifest["protected_before"])
            existing = existing_records(connection)
            if existing is None:
                insert_records(connection, desired)
            else:
                require(existing == desired, "Existing release differs; refusing retry")
            require(existing_records(connection) == desired, "Published records differ from plan")
            after = protected_snapshot(connection, correction)[0]
            assert_protected(after, manifest["protected_before"])
            compare_database_to_local(connection, correction, root / "data/processing/cses/final_HO_CSES.parquet")
    write_json(directory / "import.json", {"release_id": RELEASE, "execution_sha256": manifest_hash,
        "reviewed_plan_sha256": PLAN_SHA, "published_record_counts": COUNTS, "database_mutated": True,
        "protected_after_sha256": canonical_sha256(after), "published_records_sha256": canonical_sha256(desired),
        "physical_data_unchanged": True, "note": "Publication evidence; exact retry validates and reconstructs the same record."})
    print(f"publication_validated=True new_records={163 if existing is None else 0}", flush=True)


def validate(root: Path, directory: Path) -> None:
    plan, manifest, manifest_hash, correction = inputs(root, directory)
    desired = expected_records(plan, manifest, manifest_hash)
    imported = json.loads((directory / "import.json").read_text())
    require(imported["execution_sha256"] == manifest_hash, "Import refers to a different execution")
    with connect_database({"dbname": "mda"}) as connection:
        read_only(connection)
        actual = existing_records(connection)
        require(actual == desired, "Independent validation: published records differ")
        protected = protected_snapshot(connection, correction)[0]
        assert_protected(protected, manifest["protected_before"])
        compare_database_to_local(connection, correction, root / "data/processing/cses/final_HO_CSES.parquet")
    require(canonical_sha256(protected) == imported["protected_after_sha256"] and
            canonical_sha256(actual) == imported["published_records_sha256"], "Import fingerprints differ")
    write_json(directory / "validation.json", {"release_id": RELEASE, "execution_sha256": manifest_hash,
        "import_sha256": sha256_file(directory / "import.json"), "validation_passed": True,
        "database_mutated": False, "transaction_read_only": True, "record_counts": COUNTS,
        "protected_table_count": 35, "physical_data_unchanged": True,
        "protected_sha256": canonical_sha256(protected), "published_records_sha256": canonical_sha256(actual)})
    print("validation_passed=True database_mutated=False", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("backup", "prepare", "apply", "validate"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--execution-sha256")
    args = parser.parse_args()
    root = args.root.resolve()
    directory = root / DIRECTORY
    if args.mode == "backup":
        require(args.backup_dir is not None, "Explicit external backup directory required")
        backup(root, directory, args.backup_dir)
    elif args.mode == "apply":
        require(args.apply and bool(args.execution_sha256), "Apply flag and exact execution hash required")
        apply(root, directory, args.execution_sha256)
    elif args.mode == "prepare":
        prepare(root, directory)
    else:
        validate(root, directory)


if __name__ == "__main__":
    main()
