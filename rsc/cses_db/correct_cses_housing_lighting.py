#!/usr/bin/env python3
"""Prepare, apply, and independently validate the exact approved 2004 lighting correction."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
from cses_baseline_metadata import canonical_sha256, connect_database, sha256_file
from cses_hh_hl_common import snake_case
from inventory_cses_archives import DataSource
from psycopg import sql
from psycopg.types.json import Jsonb

SPEC = "rsc/specs/cses_housing_lighting_missing_v1.json"
HO_FILES = ("final_HO_CSES.parquet", "cses_ho_alignment_audit.csv", "cses_ho_data_issues.csv",
            "ind_que_HO_CSES.csv", "align_summary_HO_CSES.csv")
IMPLEMENTATION = (SPEC, "rsc/cses_db/correct_cses_housing_lighting.py",
                  "rsc/cses_db/cses_housing.py", "rsc/cses_db/validate_cses_ho.py",
                  "rsc/cses_db/cses_baseline_metadata.py", "rsc/cses_db/inventory_cses_archives.py",
                  "rsc/cses_db/cses_hh_hl_common.py", "pyproject.toml", "uv.lock")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    # Evidence from an earlier execution is not replaced by a different result.
    if path.exists():
        require(path.read_text() == text, f"Immutable evidence already differs: {path}")
    else:
        path.write_text(text)


def target_mask(frame: pd.DataFrame, spec: dict) -> pd.Series:
    return frame["Survey Wave"].eq(spec["survey_wave"]) & frame["Household ID"].eq(spec["household_id"])


def compare_local(before: pd.DataFrame, after: pd.DataFrame, spec: dict) -> dict:
    require(list(before.columns) == list(after.columns), "Local columns changed")
    require(before.dtypes.equals(after.dtypes), "Local column dtypes changed")
    require(before.index.equals(after.index), "Local row count or order changed")
    mask = target_mask(before, spec)
    require(int(mask.sum()) == 1, "Correction target is not unique")
    require(before.loc[mask, "Source Row ID"].item() == spec["source_row_id"], "Target source row changed")
    require(before.loc[mask, spec["local_column"]].item() == spec["old_value"], "Unexpected old value")
    expected = before.copy()
    expected.loc[mask, spec["local_column"]] = pd.NA
    pd.testing.assert_frame_equal(expected, after, check_exact=True)
    differences = ~(before.eq(after) | (before.isna() & after.isna())).fillna(False)
    require(int(differences.sum().sum()) == 1, "Expected exactly one changed cell")
    return {"rows": len(after), "columns": len(after.columns), "changed_cells": 1,
            "changed_rows": 1, "target_key": {"survey_wave": spec["survey_wave"], "household_id": spec["household_id"]},
            "source_row_id": spec["source_row_id"], "column": spec["column"],
            "old_value": spec["old_value"], "new_value": None,
            "all_other_cells_keys_and_types_unchanged": True}


def relation_digest(connection, schema: str, table: str, spec: dict, *, mask_target: bool = False) -> dict:
    relation = sql.Identifier(schema, table)
    expression = sql.SQL("to_jsonb(t)")
    condition = sql.SQL("TRUE")
    parameters = []
    if mask_target:
        expression = sql.SQL("CASE WHEN survey_wave=%s AND household_id=%s "
                             "THEN to_jsonb(t) - %s ELSE to_jsonb(t) END")
        parameters.extend([spec["survey_wave"], spec["household_id"], spec["column"]])
    if (schema, table) == ("cses_meta", "cses_alignment_release"):
        condition = sql.SQL("mapping_version <> %s")
        parameters.append(spec["release_id"])
    elif (schema, table) in {("cses_meta", "cses_load_run"), ("cses_alignment", "cses_variable_mapping")}:
        condition = sql.SQL("alignment_release_id IS NULL OR alignment_release_id NOT IN "
                            "(SELECT alignment_release_id FROM cses_meta.cses_alignment_release WHERE mapping_version=%s)")
        parameters.append(spec["release_id"])
    query = sql.SQL("SELECT count(*) AS row_count, encode(sha256(convert_to("
                    "coalesce(string_agg(h, '' ORDER BY h), ''), 'UTF8')), 'hex') AS sha256 "
                    "FROM (SELECT encode(sha256(convert_to(({expression})::text, 'UTF8')), 'hex') AS h "
                    "FROM {relation} AS t WHERE {condition}) AS rows").format(
                        expression=expression, relation=relation, condition=condition)
    return connection.execute(query, parameters).fetchone()


def database_snapshot(connection, spec: dict) -> dict:
    relations = connection.execute("""
        SELECT n.nspname AS schema_name, c.relname AS table_name, c.oid::bigint AS oid,
               c.relowner::bigint AS owner, c.relacl::text AS acl
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname IN ('cses_meta','cses_alignment','cses_data','cses_analysis')
          AND c.relkind='r' ORDER BY n.nspname,c.relname
    """).fetchall()
    fingerprints = []
    for relation in relations:
        name = (relation["schema_name"], relation["table_name"])
        fingerprints.append({**relation, **relation_digest(connection, *name, spec,
                            mask_target=name == (spec["table_schema"], spec["table"]))})
    structural = connection.execute("""
        SELECT n.nspname, c.relname, c.relkind, c.oid::bigint, c.relowner::bigint, c.relacl::text,
               a.attnum, a.attname, format_type(a.atttypid,a.atttypmod) AS type,
               a.attnotnull, col_description(c.oid,a.attnum) AS comment,
               CASE WHEN c.relkind='v' THEN pg_get_viewdef(c.oid,true) END AS view_definition
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
        WHERE (n.nspname IN ('cses_meta','cses_alignment','cses_data','cses_analysis')
          OR (n.nspname='public' AND c.relname IN (SELECT table_name FROM cses_meta.cses_storage_table)))
          AND c.relkind IN ('r','v') ORDER BY n.nspname,c.relname,a.attnum
    """).fetchall()
    require(not connection.execute("SELECT 1 FROM pg_trigger WHERE tgrelid=%s::regclass AND NOT tgisinternal",
                                   (f'{spec["table_schema"]}."{spec["table"]}"',)).fetchall(),
            "Unexpected user trigger on correction target")
    target = connection.execute(sql.SQL("SELECT to_jsonb(t) AS row FROM {} t WHERE survey_wave=%s AND household_id=%s")
                                .format(sql.Identifier(spec["table_schema"], spec["table"])),
                                (spec["survey_wave"], spec["household_id"])).fetchall()
    require(len(target) == 1, "Database target key is not unique")
    return {"protected_relations": fingerprints, "structure_sha256": canonical_sha256(structural),
            "target_row": target[0]["row"],
            "housing_full": relation_digest(connection, spec["table_schema"], spec["table"], spec),
            "compatibility_full": relation_digest(connection, "public", spec["table"], spec)}


def source_check(root: Path, spec: dict) -> dict:
    require(sha256_file(root / spec["source_archive"]) == spec["archive_sha256"], "Raw archive changed")
    payload = DataSource(root / spec["source_archive"], (spec["source_member"],)).read_bytes()
    with pd.io.stata.StataReader(io.BytesIO(payload), convert_categoricals=False) as reader:
        label_sets = reader.value_labels()
        assigned = dict(zip(reader._varlist, reader._lbllist, strict=True))
        label = label_sets[assigned[spec["source_variable"]]][spec["old_value"]]
        raw = reader.read(columns=[spec["source_variable"]])
    row_number = int(spec["source_row_id"].rsplit(":", 1)[1])
    # Source Row ID is 1-based in the inherited builder.
    require(raw.iloc[row_number - 1][spec["source_variable"]] == spec["old_value"], "Raw source row mismatch")
    require(label == spec["source_label"], "Raw source label does not document missingness")
    require(int(raw[spec["source_variable"]].eq(spec["old_value"]).sum()) == 1, "Raw correction scope changed")
    return {"archive_sha256": spec["archive_sha256"], "member_sha256": hashlib.sha256(payload).hexdigest(),
            "variable": spec["source_variable"], "label": label, "raw_matches": 1}


def prepare(root: Path, spec: dict, directory: Path) -> None:
    current = root / "data/processing/cses"
    require(sha256_file(current / HO_FILES[0]) == spec["before_housing_sha256"], "Current local table is not baseline")
    require(sha256_file(root / spec["audit_evidence"]["path"]) == spec["audit_evidence"]["sha256"], "Audit changed")
    source = source_check(root, spec)
    for filename in HO_FILES:
        destination = directory / "before" / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            require(sha256_file(destination) == sha256_file(current / filename), "Before artifact differs")
        else:
            shutil.copy2(current / filename, destination)
    with connect_database({"dbname": spec["database"]}) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL statement_timeout='55s'")
        snapshot = database_snapshot(connection, spec)
        require(snapshot["target_row"][spec["column"]] == spec["old_value"], "Database is not at expected old value")
        require(snapshot["target_row"]["source_row_id"] == spec["source_row_id"], "Database source row mismatch")
        require(snapshot["housing_full"] == snapshot["compatibility_full"], "Compatibility view differs")
    protected_files = {str(p.relative_to(root)): sha256_file(p) for p in current.iterdir()
                       if p.is_file() and p.name not in HO_FILES}
    write_json(directory / "before.json", {"schema_version": 1, "database_mutated": False,
               "release_id": spec["release_id"], "source": source, "database": snapshot,
               "protected_local_files": protected_files,
               "before_files": {name: sha256_file(directory / "before" / name) for name in HO_FILES}})
    print("prepare_complete=True database_mutated=False", flush=True)


def verify_protected_local(root: Path, before: dict) -> None:
    for path, digest in before["protected_local_files"].items():
        require(sha256_file(root / path) == digest, f"Unrelated local artifact changed: {path}")


def compare_database_to_local(connection, spec: dict, path: Path) -> None:
    """Compare every cell, preserving local declared numeric and string types."""
    local = pd.read_parquet(path).rename(columns=snake_case)
    cursor = connection.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(spec["table_schema"], spec["table"])))
    columns = [column.name for column in cursor.description]
    require(columns == list(local.columns), "Published columns differ from local columns")
    observed = pd.DataFrame.from_records(cursor.fetchall(), columns=columns)
    for column in columns:
        observed[column] = observed[column].astype(local[column].dtype)
    keys = ["survey_wave", "household_id"]
    pd.testing.assert_frame_equal(local.sort_values(keys).reset_index(drop=True),
                                  observed.sort_values(keys).reset_index(drop=True), check_exact=True)


def prior_mapping(connection, spec: dict) -> dict:
    records = connection.execute("""
        SELECT m.variable_mapping_id,m.dataset_id,m.canonical_variable_id,d.survey_id
        FROM cses_alignment.cses_variable_mapping m
        JOIN cses_meta.cses_alignment_release r USING(alignment_release_id)
        JOIN cses_alignment.cses_canonical_variable c USING(canonical_variable_id)
        JOIN cses_meta.cses_dataset d USING(dataset_id)
        JOIN cses_meta.cses_source_archive a USING(source_archive_id)
        WHERE r.mapping_version=%s AND c.target_table=%s AND c.canonical_name=%s
          AND a.relative_path=%s AND d.member_path=%s
    """, (spec["baseline_mapping_version"], spec["table"], spec["column"],
            spec["source_archive"], spec["source_member"])).fetchall()
    require(len(records) == 1, "Prior mapping identity is ambiguous")
    return records[0]


def check_database_state(observed: dict, before: dict, spec: dict, after: bool) -> None:
    require(observed["protected_relations"] == before["protected_relations"], "Protected database content changed")
    require(observed["structure_sha256"] == before["structure_sha256"], "Database structure or permissions changed")
    expected = dict(before["target_row"])
    if after:
        expected[spec["column"]] = None
    require(observed["target_row"] == expected, "Target differs beyond the approved cell")
    require(observed["housing_full"] == observed["compatibility_full"], "Compatibility interface differs")
    if not after:
        require(observed["housing_full"] == before["housing_full"], "Housing table changed since preparation")


def build_plan(root: Path, spec: dict, directory: Path) -> None:
    before = json.loads((directory / "before.json").read_text())
    verify_protected_local(root, before)
    current = root / "data/processing/cses"
    diff = compare_local(pd.read_parquet(directory / "before" / HO_FILES[0]),
                         pd.read_parquet(current / HO_FILES[0]), spec)
    for name in (HO_FILES[1], HO_FILES[3], HO_FILES[4]):
        require(sha256_file(current / name) == before["before_files"][name], f"Unexpected metadata change: {name}")
    prior_issues = pd.read_csv(directory / "before" / HO_FILES[2]).fillna("")
    next_issues = pd.read_csv(current / HO_FILES[2]).fillna("")
    added = next_issues.merge(prior_issues, how="outer", indicator=True).query('_merge != "both"')
    require(len(added) == 1 and added.iloc[0]["_merge"] == "left_only", "Unexpected issue-report change")
    require(str(added.iloc[0]["survey_wave"]) == "2004" and added.iloc[0]["variable"] == "Main Lighting Source Code"
            and int(added.iloc[0]["affected_rows"]) == 1, "Issue report is not scoped to the corrected cell")
    with connect_database({"dbname": spec["database"]}) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL statement_timeout='55s'")
        check_database_state(database_snapshot(connection, spec), before["database"], spec, False)
        compare_database_to_local(connection, spec, directory / "before" / HO_FILES[0])
        prior = prior_mapping(connection, spec)
    after_files = {}
    for name in HO_FILES:
        after_files[name] = sha256_file(current / name)
        destination = directory / "after" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            require(sha256_file(destination) == after_files[name], "After artifact differs")
        else:
            shutil.copy2(current / name, destination)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    write_json(directory / "plan.json", {"schema_version": 1, "release_id": spec["release_id"],
               "database_mutated": False, "preflight_ready": True, "spec_sha256": sha256_file(root / SPEC),
               "before_sha256": sha256_file(directory / "before.json"), "source": source_check(root, spec),
               "local_difference": diff, "after_files": after_files,
               "prior_mapping": prior, "baseline_database_and_local_match_all_cells": True,
               "implementation_sha256": {path: sha256_file(root / path) for path in IMPLEMENTATION},
               "code_git_revision": revision, "metadata_insert_counts": spec["metadata_changes"]})
    print("preflight_ready=True changed_cells=1 database_mutated=False", flush=True)


def backup(spec: dict, directory: Path, backup_dir: Path) -> None:
    require(backup_dir.is_dir(), "External backup directory does not exist")
    fd, name = tempfile.mkstemp(prefix=f"mda_{spec['release_id']}_", suffix=".dump", dir=backup_dir)
    os.close(fd)
    path = Path(name)
    path.chmod(0o600)
    print(f"backup={path}", flush=True)
    subprocess.run(["pg_dump", "-d", spec["database"], "--format=custom", "--compress=6",
                    "--table=cses_data.\"final_HO_CSES\"", "--table=cses_meta.cses_alignment_release",
                    "--table=cses_meta.cses_load_run", "--table=cses_alignment.cses_variable_mapping",
                    f"--file={path}"], check=True)
    require(path.stat().st_size > 0, "Backup is empty")
    toc = subprocess.run(["pg_restore", "--list", str(path)], check=True, capture_output=True, text=True).stdout
    for table in ("final_HO_CSES", "cses_alignment_release", "cses_load_run", "cses_variable_mapping"):
        require(table in toc, f"Backup is missing {table}")
    subprocess.run(["pg_restore", "--file=/dev/null", str(path)], check=True)
    write_json(directory / "backup.json", {"database_mutated": False, "path": str(path),
               "sha256": sha256_file(path), "size_bytes": path.stat().st_size,
               "scope": "Housing table and three metadata tables affected by this correction; not a full database backup",
               "pg_restore_list_passed": True, "pg_restore_full_decompression_passed": True})
    print("backup_verified=True", flush=True)


def release_records(connection, spec: dict) -> dict:
    release = connection.execute("SELECT alignment_release_id,mapping_version,status,description,"
                                 "specification_sha256::text FROM cses_meta.cses_alignment_release WHERE mapping_version=%s",
                                 (spec["release_id"],)).fetchone()
    if not release:
        return {"release": None, "mappings": [], "runs": []}
    identity = release["alignment_release_id"]
    mappings = connection.execute("SELECT dataset_id,canonical_variable_id,source_variable_names,source_kind,"
                                  "transformation_rule,alignment_status FROM cses_alignment.cses_variable_mapping "
                                  "WHERE alignment_release_id=%s", (identity,)).fetchall()
    runs = connection.execute("SELECT run_scope,status,source_manifest_sha256::text,code_git_revision,dvc_revision,"
                              "row_counts,validation_summary FROM cses_meta.cses_load_run WHERE alignment_release_id=%s",
                              (identity,)).fetchall()
    return {"release": release, "mappings": mappings, "runs": runs}


def verify_release_records(records: dict, spec: dict, plan: dict, plan_hash: str) -> None:
    require(records["release"] is not None and records["release"]["status"] == "approved", "Correction release absent")
    require(records["release"]["specification_sha256"] == plan["spec_sha256"], "Release specification differs")
    require(records["release"]["description"] == spec["transformation_rule"], "Release description differs")
    require(len(records["mappings"]) == len(records["runs"]) == 1, "Incorrect correction metadata count")
    mapping, run = records["mappings"][0], records["runs"][0]
    require(mapping["transformation_rule"] == spec["transformation_rule"] and
            mapping["source_variable_names"] == [spec["source_variable"]] and mapping["alignment_status"] == "loaded",
            "Correction mapping does not match plan")
    require(mapping["dataset_id"] == plan["prior_mapping"]["dataset_id"] and
            mapping["canonical_variable_id"] == plan["prior_mapping"]["canonical_variable_id"] and
            mapping["source_kind"] == "explicit", "Correction mapping target differs")
    require(run["status"] == "loaded" and run["validation_summary"]["plan_sha256"] == plan_hash
            and run["row_counts"] == {"updated_cells": 1, "updated_rows": 1}, "Correction load run differs")
    require(run["source_manifest_sha256"] == plan_hash and run["run_scope"] == spec["release_id"] and
            run["code_git_revision"] == plan["code_git_revision"] and
            run["dvc_revision"] == spec["baseline_data_dvc_revision"], "Correction run provenance differs")


def write_import_evidence(directory: Path, spec: dict, plan_hash: str, after: dict, records: dict) -> None:
    write_json(directory / "import.json", {"database_mutated": True, "release_id": spec["release_id"],
               "plan_sha256": plan_hash, "updated_rows": 1, "updated_cells": 1,
               "inserted_metadata_counts": spec["metadata_changes"], "after_database": after, "records": records})


def apply(root: Path, spec: dict, directory: Path, plan_hash: str) -> None:
    require(sha256_file(directory / "plan.json") == plan_hash, "Explicit plan hash differs")
    plan = json.loads((directory / "plan.json").read_text())
    require(plan["preflight_ready"] and not plan["database_mutated"], "Plan is not read-only and ready")
    require(sha256_file(root / SPEC) == plan["spec_sha256"], "Specification changed")
    require(sha256_file(directory / "before.json") == plan["before_sha256"], "Before evidence changed")
    for path, digest in plan["implementation_sha256"].items():
        require(sha256_file(root / path) == digest, f"Implementation changed: {path}")
    for name, digest in plan["after_files"].items():
        require(sha256_file(root / "data/processing/cses" / name) == digest, f"Local result changed: {name}")
    before = json.loads((directory / "before.json").read_text())
    verify_protected_local(root, before)
    backup_record = json.loads((directory / "backup.json").read_text())
    require(backup_record["pg_restore_full_decompression_passed"] and
            sha256_file(Path(backup_record["path"])) == backup_record["sha256"], "Verified backup differs")
    source_check(root, spec)
    with connect_database({"dbname": spec["database"]}) as connection:
        with connection.transaction():
            connection.execute("SET LOCAL lock_timeout='10s'")
            connection.execute("SET LOCAL statement_timeout='55s'")
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (spec["release_id"],))
            # Keep the target and metadata stable for exact before/after comparison.
            tables = connection.execute("SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                                        "WHERE n.nspname IN ('cses_meta','cses_alignment','cses_data','cses_analysis') "
                                        "AND c.relkind='r' ORDER BY n.nspname,c.relname").fetchall()
            for table in tables:
                connection.execute(sql.SQL("LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE").format(
                    sql.Identifier(table["nspname"], table["relname"])))
            existing = release_records(connection, spec)
            if existing["release"]:
                verify_release_records(existing, spec, plan, plan_hash)
                after = database_snapshot(connection, spec)
                check_database_state(after, before["database"], spec, True)
                compare_database_to_local(connection, spec, root / "data/processing/cses" / HO_FILES[0])
                write_import_evidence(directory, spec, plan_hash, after, existing)
                print("already_applied=True database_mutated=False")
                return
            check_database_state(database_snapshot(connection, spec), before["database"], spec, False)
            prior = prior_mapping(connection, spec)
            require(prior == plan["prior_mapping"], "Prior mapping identity differs from plan")
            changed = connection.execute(sql.SQL("UPDATE {} SET {}=NULL WHERE survey_wave=%s AND household_id=%s "
                                                 "AND source_row_id=%s AND {}=%s RETURNING household_id").format(
                sql.Identifier(spec["table_schema"], spec["table"]), sql.Identifier(spec["column"]),
                sql.Identifier(spec["column"])),
                (spec["survey_wave"], spec["household_id"], spec["source_row_id"], spec["old_value"])).fetchall()
            require(len(changed) == 1, "Correction did not update exactly one row")
            release_id = connection.execute("INSERT INTO cses_meta.cses_alignment_release "
                "(mapping_version,status,description,specification_sha256,approved_at) VALUES (%s,'approved',%s,%s,now()) "
                "RETURNING alignment_release_id", (spec["release_id"], spec["transformation_rule"], plan["spec_sha256"])
            ).fetchone()["alignment_release_id"]
            connection.execute("INSERT INTO cses_alignment.cses_variable_mapping "
                "(dataset_id,canonical_variable_id,alignment_release_id,source_variable_names,source_kind,transformation_rule,"
                "alignment_status) VALUES (%s,%s,%s,%s,'explicit',%s,'loaded')",
                (prior["dataset_id"], prior["canonical_variable_id"], release_id,
                 [spec["source_variable"]], spec["transformation_rule"]))
            validation = {"correction_id": spec["release_id"], "plan_sha256": plan_hash,
                          "before_evidence_sha256": plan["before_sha256"],
                          "backup_sha256": backup_record["sha256"], "local_difference": plan["local_difference"],
                          "supersedes_variable_mapping_id": prior["variable_mapping_id"],
                          "protected_database_sha256": canonical_sha256(before["database"]["protected_relations"])}
            connection.execute("INSERT INTO cses_meta.cses_load_run "
                "(survey_id,alignment_release_id,run_scope,source_manifest_sha256,code_git_revision,dvc_revision,status,"
                "row_counts,validation_summary,finished_at) VALUES (%s,%s,%s,%s,%s,%s,'loaded',%s,%s,now())",
                (prior["survey_id"], release_id, spec["release_id"], plan_hash, plan["code_git_revision"],
                 spec["baseline_data_dvc_revision"], Jsonb({"updated_cells": 1, "updated_rows": 1}), Jsonb(validation)))
            after = database_snapshot(connection, spec)
            check_database_state(after, before["database"], spec, True)
            compare_database_to_local(connection, spec, root / "data/processing/cses" / HO_FILES[0])
            records = release_records(connection, spec)
            verify_release_records(records, spec, plan, plan_hash)
    write_import_evidence(directory, spec, plan_hash, after, records)
    print("database_mutated=True updated_cells=1 updated_rows=1", flush=True)


def validate(root: Path, spec: dict, directory: Path) -> None:
    before = json.loads((directory / "before.json").read_text())
    plan = json.loads((directory / "plan.json").read_text())
    imported = json.loads((directory / "import.json").read_text())
    plan_hash = sha256_file(directory / "plan.json")
    require(imported["plan_sha256"] == plan_hash, "Import evidence refers to a different plan")
    verify_protected_local(root, before)
    difference = compare_local(pd.read_parquet(directory / "before" / HO_FILES[0]),
                               pd.read_parquet(root / "data/processing/cses" / HO_FILES[0]), spec)
    with connect_database({"dbname": spec["database"]}) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL statement_timeout='55s'")
        observed = database_snapshot(connection, spec)
        check_database_state(observed, before["database"], spec, True)
        require(observed == imported["after_database"], "Live state differs from committed import evidence")
        verify_release_records(release_records(connection, spec), spec, plan, plan_hash)
        compare_database_to_local(connection, spec, root / "data/processing/cses" / HO_FILES[0])
    write_json(directory / "validation.json", {"database_mutated": False, "validation_passed": True,
               "release_id": spec["release_id"], "plan_sha256": plan_hash,
               "import_sha256": sha256_file(directory / "import.json"), "local_difference": difference,
               "after_database_sha256": canonical_sha256(observed), "transaction_read_only": True,
               "database_and_local_match_all_cells": True})
    print("validation_passed=True database_mutated=False", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "plan", "backup", "apply", "validate"])
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--plan-sha256")
    args = parser.parse_args()
    root = args.root.resolve()
    spec = json.loads((root / SPEC).read_text())
    require(spec["release_id"] == "cses-housing-lighting-missing-v1" and spec["database"] == "mda", "Wrong scope")
    directory = root / spec["release_directory"]
    directory.mkdir(parents=True, exist_ok=True)
    if args.mode == "apply":
        require(args.apply and bool(args.plan_sha256), "Apply requires --apply and the exact --plan-sha256")
        apply(root, spec, directory, args.plan_sha256)
    elif args.mode == "backup":
        require(args.backup_dir is not None, "Backup requires an explicitly selected external directory")
        backup(spec, directory, args.backup_dir)
    else:
        {"prepare": prepare, "plan": build_plan, "validate": validate}[args.mode](root, spec, directory)


if __name__ == "__main__":
    main()
