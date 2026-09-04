"""Build, inspect, and apply reviewed CSES storage-level provenance."""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import psycopg
from cses_baseline_metadata import (
    METADATA_TABLE_COLUMNS,
    canonical_json,
    canonical_sha256,
    connect_database,
    normalize_json_value,
    sha256_file,
)
from psycopg import sql
from psycopg.types.json import Jsonb

OUTPUT_KEY_FIELDS = (
    "archive_relative_path",
    "member_path",
    "nested_member_path",
    "table_schema",
    "table_name",
    "contribution_role",
)
RECORD_KEYS = {
    "alignment_releases": ("mapping_version",),
    "dataset_outputs": OUTPUT_KEY_FIELDS,
    "load_runs": ("storage_provenance_import_id",),
}
DESIRED_GROUPS = ("alignment_releases", "dataset_outputs", "load_runs")


def default_storage_provenance_spec_path(root: Path) -> Path:
    return root / "rsc" / "specs" / "cses_storage_provenance_v1.json"


def load_storage_provenance_spec(path: Path) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec.get("schema_version") != 1:
        raise ValueError(f"Unsupported storage provenance schema version: {spec.get('schema_version')}")
    if spec.get("database") != "mda":
        raise ValueError("The storage provenance release is scoped to the mda database")
    if spec.get("alignment_release", {}).get("status") != "approved":
        raise ValueError("The storage provenance release must be approved")
    if not spec["alignment_release"].get("requires_explicit_approval"):
        raise ValueError("The storage provenance release must retain its explicit approval gate")
    if not spec.get("approval_phrase"):
        raise ValueError("An exact database-write approval phrase is required")
    if not re.fullmatch(r"md5:[0-9a-f]{32}\.dir", str(spec.get("source_data_dvc_revision", ""))):
        raise ValueError("A fixed source data.dvc directory revision is required")

    rules = spec.get("module_rules", [])
    modules = [rule["module_code"] for rule in rules]
    finals = [rule["final_relation"] for rule in rules]
    dictionaries = [rule["dictionary_relation"] for rule in rules]
    summaries = [rule["summary_relation"] for rule in rules]
    if len(rules) != 7 or len(set(modules)) != 7:
        raise ValueError("Storage provenance v1 must define seven unique module rules")
    if any(len(set(names)) != 7 for names in (finals, dictionaries, summaries)):
        raise ValueError("Final, dictionary, and summary relation names must be unique")
    geography = spec.get("geography_rule", {})
    if geography.get("cses_source_relation") not in finals:
        raise ValueError("The geography rule must inherit a declared final-relation source set")
    if geography.get("contribution_role") != "source":
        raise ValueError("The geography relation must use the source contribution role")
    targets = [*dictionaries, *summaries, geography.get("target_relation")]
    if len(targets) != 15 or len(set(targets)) != 15:
        raise ValueError("Storage provenance v1 must close exactly fifteen unique relation gaps")
    if len(geography.get("external_dependencies", [])) != 2:
        raise ValueError("Both external Cambodia boundary dependencies must remain explicit")
    return spec


def _git_revision(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _read_verified_json(root: Path, descriptor: dict[str, str]) -> tuple[dict[str, Any], bool]:
    path = root / descriptor["path"]
    matches = path.is_file() and sha256_file(path) == descriptor["sha256"]
    if not matches:
        raise ValueError(f"Evidence fingerprint mismatch: {descriptor['path']}")
    return json.loads(path.read_text(encoding="utf-8")), matches


def _artifact_path(relation: str) -> str:
    suffix = ".parquet" if relation.startswith("final_") else ".csv"
    return f"data/processing/cses/{relation}{suffix}"


def _record_key(record: dict[str, Any], fields: Iterable[str]) -> tuple[Any, ...]:
    return tuple(normalize_json_value(record.get(field)) for field in fields)


def _sorted_records(records: Iterable[dict[str, Any]], fields: Iterable[str]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda record: canonical_json(_record_key(record, fields)))


def _retarget_output(
    source: dict[str, Any],
    storage: dict[str, Any],
    mapping_version: str,
    role: str,
) -> dict[str, Any]:
    return {
        "archive_relative_path": source["archive_relative_path"],
        "member_path": source["member_path"],
        "nested_member_path": source["nested_member_path"],
        "table_schema": storage["table_schema"],
        "table_name": storage["table_name"],
        "mapping_version": mapping_version,
        "contribution_role": role,
        "output_row_count": storage["row_count"],
    }


def build_desired_state(
    root: Path, spec_path: Path | None = None
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    spec_path = spec_path or default_storage_provenance_spec_path(root)
    spec = load_storage_provenance_spec(spec_path)
    evidence_documents: dict[str, dict[str, Any]] = {}
    evidence_checks: dict[str, bool] = {}
    for name, descriptor in sorted(spec["evidence"].items()):
        document, matched = _read_verified_json(root, descriptor)
        evidence_documents[name] = document
        evidence_checks[f"{name}_fingerprint_matches"] = matched

    baseline = evidence_documents["baseline_plan"]
    manifest = evidence_documents["local_release_manifest"]
    graph = evidence_documents["lineage_graph"]
    if baseline.get("baseline_id") != "cses-baseline-metadata-v1":
        raise ValueError("The reviewed baseline plan has an unexpected baseline ID")
    if baseline.get("preflight_ready") is not True or baseline.get("database_mutated") is not False:
        raise ValueError("The baseline evidence is not a successful non-mutating plan")

    baseline_outputs = baseline["desired_state"]["dataset_outputs"]
    storage_by_name = {
        record["table_name"]: record for record in baseline["desired_state"]["storage_tables"]
    }
    release_versions = {
        record["mapping_version"] for record in baseline["desired_state"]["alignment_releases"]
    }
    if spec["source_alignment_release"] not in release_versions:
        raise ValueError("The source alignment release is absent from the reviewed baseline plan")

    artifact_manifest = {record["path"]: record for record in manifest["artifacts"]}
    artifact_paths: set[str] = set()
    builder_checks: dict[str, bool] = {}
    output_records: dict[tuple[Any, ...], dict[str, Any]] = {}
    mapping_version = spec["alignment_release"]["mapping_version"]
    for rule in spec["module_rules"]:
        builder_path = root / rule["builder_path"]
        builder_matches = builder_path.is_file() and sha256_file(builder_path) == rule["builder_sha256"]
        builder_checks[f"builder_{rule['module_code']}_matches"] = builder_matches
        if not builder_matches:
            raise ValueError(f"Builder fingerprint mismatch: {rule['builder_path']}")

        relations = (rule["final_relation"], rule["dictionary_relation"], rule["summary_relation"])
        for relation in relations:
            artifact_path = _artifact_path(relation)
            artifact_paths.add(artifact_path)
            recorded = artifact_manifest.get(artifact_path)
            if recorded is None or sha256_file(root / artifact_path) != recorded["sha256"]:
                raise ValueError(f"Artifact is absent from or differs from the release manifest: {artifact_path}")

        final_sources = [
            record for record in baseline_outputs if record["table_name"] == rule["final_relation"]
        ]
        if not final_sources:
            raise ValueError(f"No reviewed source edges for {rule['final_relation']}")
        for target_name, role in (
            (rule["dictionary_relation"], "source"),
            (rule["summary_relation"], "validation"),
        ):
            storage = storage_by_name[target_name]
            for source in final_sources:
                record = _retarget_output(source, storage, mapping_version, role)
                output_records[_record_key(record, OUTPUT_KEY_FIELDS)] = record

    geography = spec["geography_rule"]
    geography_source = root / geography["legacy_source_path"]
    geography_source_matches = (
        geography_source.is_file() and sha256_file(geography_source) == geography["legacy_source_sha256"]
    )
    if not geography_source_matches:
        raise ValueError(f"Legacy geography source fingerprint mismatch: {geography['legacy_source_path']}")
    geography_storage = storage_by_name[geography["target_relation"]]
    for source in baseline_outputs:
        if source["table_name"] == geography["cses_source_relation"]:
            record = _retarget_output(
                source,
                geography_storage,
                mapping_version,
                geography["contribution_role"],
            )
            output_records[_record_key(record, OUTPUT_KEY_FIELDS)] = record

    outputs = _sorted_records(output_records.values(), OUTPUT_KEY_FIELDS)
    target_names = sorted({record["table_name"] for record in outputs})
    target_identities = sorted(
        f"{storage_by_name[name]['table_schema']}.{name}" for name in target_names
    )
    expected_graph_gaps = set(target_identities)
    observed_graph_gaps = set(graph["summary"]["storage_without_dataset_outputs"])
    artifact_checks = {
        "all_release_artifacts_are_manifested_and_current": all(
            path in artifact_manifest
            and (root / path).is_file()
            and sha256_file(root / path) == artifact_manifest[path]["sha256"]
            for path in artifact_paths
        )
    }

    release = {
        "mapping_version": mapping_version,
        "status": spec["alignment_release"]["status"],
        "description": spec["alignment_release"]["description"],
        "specification_sha256": sha256_file(spec_path),
    }
    evidence_hashes = {
        name: {"path": descriptor["path"], "sha256": descriptor["sha256"]}
        for name, descriptor in sorted(spec["evidence"].items())
    }
    source_manifest_sha256 = canonical_sha256(
        {
            "evidence": evidence_hashes,
            "module_rules": spec["module_rules"],
            "geography_rule": spec["geography_rule"],
            "dataset_outputs": outputs,
        }
    )
    validation_summary = {
        "storage_provenance_import_id": spec["provenance_release_id"],
        "source_alignment_release": spec["source_alignment_release"],
        "evidence": evidence_hashes,
        "closed_storage_relation_count": len(target_names),
        "dataset_output_count": len(outputs),
        "dictionary_role": "source",
        "alignment_summary_role": "validation",
        "target_relations": target_identities,
        "external_geography_dependencies": geography["external_dependencies"],
        "variable_level_mapping_created": False,
    }
    load_run = {
        "storage_provenance_import_id": spec["provenance_release_id"],
        "survey_wave": None,
        "mapping_version": mapping_version,
        "run_scope": spec["load_run"]["run_scope"],
        "source_manifest_sha256": source_manifest_sha256,
        "code_git_revision": _git_revision(root),
        "dvc_revision": spec["source_data_dvc_revision"],
        "status": spec["load_run"]["status"],
        "row_counts": {
            f"{storage_by_name[name]['table_schema']}.{name}": storage_by_name[name]["row_count"]
            for name in target_names
        },
        "validation_summary": validation_summary,
        "error_message": None,
    }
    desired = {
        "alignment_releases": [release],
        "dataset_outputs": outputs,
        "load_runs": [load_run],
    }

    source_output_counts = Counter(record["table_name"] for record in baseline_outputs)
    local_checks = {
        **evidence_checks,
        **builder_checks,
        **artifact_checks,
        "baseline_has_62_reviewed_final_edges": len(baseline_outputs) == 62,
        "baseline_has_seven_reviewed_final_targets": len(source_output_counts) == 7,
        "lineage_graph_declares_exact_15_target_gaps": observed_graph_gaps == expected_graph_gaps,
        "desired_output_count_is_134": len(outputs) == 134,
        "desired_target_relation_count_is_15": len(target_names) == 15,
        "all_output_datasets_come_from_reviewed_baseline": {
            (record["archive_relative_path"], record["member_path"], record["nested_member_path"])
            for record in outputs
        }.issubset(
            {
                (record["archive_relative_path"], record["member_path"], record["nested_member_path"])
                for record in baseline_outputs
            }
        ),
        "source_data_dvc_revision_is_declared": bool(
            re.fullmatch(r"md5:[0-9a-f]{32}\.dir", spec["source_data_dvc_revision"])
        ),
        "external_geography_dependencies_are_explicit": all(
            item["status"] == "documented_not_registered_as_cses_dataset"
            for item in geography["external_dependencies"]
        ),
        "legacy_geography_source_matches": geography_source_matches,
    }
    diagnostics = {
        "spec": {
            "path": str(spec_path.relative_to(root)),
            "sha256": sha256_file(spec_path),
            "provenance_release_id": spec["provenance_release_id"],
            "approval_phrase": spec["approval_phrase"],
            "approval_required": True,
        },
        "evidence": evidence_hashes,
        "record_counts": {name: len(desired[name]) for name in DESIRED_GROUPS},
        "source_output_counts": dict(sorted(source_output_counts.items())),
        "target_relations": target_identities,
        "external_dependencies": geography["external_dependencies"],
        "local_checks": local_checks,
        "source_dataset_outputs": _sorted_records(baseline_outputs, OUTPUT_KEY_FIELDS),
    }
    return desired, diagnostics


def reconcile_states(
    desired: dict[str, list[dict[str, Any]]], existing: dict[str, list[dict[str, Any]]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    operations: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for group in DESIRED_GROUPS:
        key_fields = RECORD_KEYS[group]
        existing_by_key: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for record in existing[group]:
            existing_by_key.setdefault(_record_key(record, key_fields), []).append(record)
        for record in desired[group]:
            key = _record_key(record, key_fields)
            candidates = existing_by_key.get(key, [])
            if not candidates:
                action = "insert"
            elif len(candidates) == 1 and normalize_json_value(candidates[0]) == normalize_json_value(record):
                action = "noop"
            else:
                action = "conflict"
                conflicts.append(
                    {
                        "group": group,
                        "key": dict(zip(key_fields, key, strict=True)),
                        "desired": record,
                        "existing": candidates,
                    }
                )
            operations.append(
                {"group": group, "key": dict(zip(key_fields, key, strict=True)), "action": action}
            )
    operations.sort(key=lambda item: (item["group"], canonical_json(item["key"])))
    return operations, conflicts


def _fetch_output_records(
    connection: psycopg.Connection[dict[str, Any]],
    *,
    table_names: list[str],
    mapping_version: str | None = None,
) -> list[dict[str, Any]]:
    mapping_filter = "AND ar.mapping_version = %s" if mapping_version else ""
    parameters: tuple[object, ...] = (table_names, mapping_version) if mapping_version else (table_names,)
    query = f"""
        SELECT a.relative_path AS archive_relative_path, d.member_path,
               d.nested_member_path, st.table_schema, st.table_name,
               ar.mapping_version, o.contribution_role, o.output_row_count
        FROM cses_meta.cses_dataset_output AS o
        JOIN cses_meta.cses_dataset AS d USING (dataset_id)
        JOIN cses_meta.cses_source_archive AS a USING (source_archive_id)
        JOIN cses_meta.cses_storage_table AS st USING (storage_table_id)
        JOIN cses_meta.cses_alignment_release AS ar USING (alignment_release_id)
        WHERE st.table_name = ANY(%s) {mapping_filter}
        ORDER BY a.relative_path, d.member_path, d.nested_member_path,
                 st.table_schema, st.table_name, o.contribution_role
    """
    return [normalize_json_value(dict(row)) for row in connection.execute(query, parameters).fetchall()]


def _fetch_existing_state(
    connection: psycopg.Connection[dict[str, Any]],
    desired: dict[str, list[dict[str, Any]]],
    provenance_release_id: str,
) -> dict[str, list[dict[str, Any]]]:
    mapping_version = desired["alignment_releases"][0]["mapping_version"]
    releases = connection.execute(
        """
        SELECT mapping_version, status, description, specification_sha256
        FROM cses_meta.cses_alignment_release
        WHERE mapping_version = %s
        ORDER BY alignment_release_id
        """,
        (mapping_version,),
    ).fetchall()
    target_names = sorted({record["table_name"] for record in desired["dataset_outputs"]})
    outputs = _fetch_output_records(connection, table_names=target_names)
    load_runs = connection.execute(
        """
        SELECT validation_summary->>'storage_provenance_import_id' AS storage_provenance_import_id,
               s.survey_wave, ar.mapping_version, lr.run_scope,
               lr.source_manifest_sha256, lr.code_git_revision, lr.dvc_revision,
               lr.status, lr.row_counts, lr.validation_summary, lr.error_message
        FROM cses_meta.cses_load_run AS lr
        LEFT JOIN cses_meta.cses_survey AS s USING (survey_id)
        LEFT JOIN cses_meta.cses_alignment_release AS ar USING (alignment_release_id)
        WHERE validation_summary->>'storage_provenance_import_id' = %s
        ORDER BY lr.load_run_id
        """,
        (provenance_release_id,),
    ).fetchall()
    return {
        "alignment_releases": [normalize_json_value(dict(row)) for row in releases],
        "dataset_outputs": outputs,
        "load_runs": [normalize_json_value(dict(row)) for row in load_runs],
    }


def inspect_database(
    connection: psycopg.Connection[dict[str, Any]],
    desired: dict[str, list[dict[str, Any]]],
    spec: dict[str, Any],
    source_dataset_outputs: list[dict[str, Any]],
    *,
    require_read_only: bool = True,
) -> dict[str, Any]:
    database = connection.execute(
        """
        SELECT current_database() AS database, current_user AS current_user,
               current_setting('transaction_read_only') AS transaction_read_only
        """
    ).fetchone()
    columns = connection.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'cses_meta' AND table_name = ANY(%s)
        ORDER BY table_name, ordinal_position
        """,
        (sorted(METADATA_TABLE_COLUMNS),),
    ).fetchall()
    observed_columns: dict[str, list[str]] = {name: [] for name in METADATA_TABLE_COLUMNS}
    for row in columns:
        observed_columns[row["table_name"]].append(row["column_name"])

    target_names = sorted({record["table_name"] for record in desired["dataset_outputs"]})
    target_rows = connection.execute(
        """
        SELECT table_schema, table_name, row_count
        FROM cses_meta.cses_storage_table
        WHERE table_name = ANY(%s)
        ORDER BY table_schema, table_name
        """,
        (target_names,),
    ).fetchall()
    registered_target_counts = {
        (row["table_schema"], row["table_name"]): row["row_count"] for row in target_rows
    }
    expected_target_counts = {
        (record["table_schema"], record["table_name"]): record["output_row_count"]
        for record in desired["dataset_outputs"]
    }
    physical_checks = []
    for (table_schema, table_name), expected_count in sorted(expected_target_counts.items()):
        physical_count = connection.execute(
            sql.SQL("SELECT count(*) AS row_count FROM {}.{}").format(
                sql.Identifier(table_schema), sql.Identifier(table_name)
            )
        ).fetchone()["row_count"]
        physical_checks.append(
            {
                "table_schema": table_schema,
                "table_name": table_name,
                "expected_row_count": expected_count,
                "registered_row_count": registered_target_counts.get((table_schema, table_name)),
                "observed_row_count": physical_count,
                "matches": registered_target_counts.get((table_schema, table_name))
                == physical_count
                == expected_count,
            }
        )

    dataset_rows = connection.execute(
        """
        SELECT a.relative_path AS archive_relative_path, d.member_path, d.nested_member_path
        FROM cses_meta.cses_dataset AS d
        JOIN cses_meta.cses_source_archive AS a USING (source_archive_id)
        ORDER BY a.relative_path, d.member_path, d.nested_member_path
        """
    ).fetchall()
    registered_dataset_keys = {
        (row["archive_relative_path"], row["member_path"], row["nested_member_path"])
        for row in dataset_rows
    }
    desired_dataset_keys = {
        (record["archive_relative_path"], record["member_path"], record["nested_member_path"])
        for record in desired["dataset_outputs"]
    }

    source_names = sorted({record["table_name"] for record in source_dataset_outputs})
    observed_source_outputs = _fetch_output_records(
        connection,
        table_names=source_names,
        mapping_version=spec["source_alignment_release"],
    )
    expected_source_outputs = _sorted_records(source_dataset_outputs, OUTPUT_KEY_FIELDS)
    observed_source_outputs = _sorted_records(observed_source_outputs, OUTPUT_KEY_FIELDS)

    existing = _fetch_existing_state(connection, desired, spec["provenance_release_id"])
    operations, conflicts = reconcile_states(desired, existing)
    desired_output_by_key = {
        _record_key(record, OUTPUT_KEY_FIELDS): normalize_json_value(record)
        for record in desired["dataset_outputs"]
    }
    unreviewed_existing_outputs = [
        record
        for record in existing["dataset_outputs"]
        if desired_output_by_key.get(_record_key(record, OUTPUT_KEY_FIELDS))
        != normalize_json_value(record)
    ]
    action_counts = Counter(item["action"] for item in operations)
    checks = {
        "database_name_matches": database["database"] == spec["database"],
        "metadata_table_columns_match_v1_ddl": all(
            tuple(observed_columns[name]) == expected for name, expected in METADATA_TABLE_COLUMNS.items()
        ),
        "all_target_storage_relations_are_registered": set(registered_target_counts)
        == set(expected_target_counts),
        "physical_target_relations_match_registered_counts": all(
            record["matches"] for record in physical_checks
        ),
        "all_referenced_datasets_are_registered": desired_dataset_keys.issubset(registered_dataset_keys),
        "source_final_edges_match_reviewed_baseline": observed_source_outputs == expected_source_outputs,
        "no_unreviewed_output_edges_on_target_relations": not unreviewed_existing_outputs,
        "no_existing_metadata_conflicts": not conflicts,
    }
    checks["transaction_is_read_only" if require_read_only else "transaction_is_read_write"] = (
        database["transaction_read_only"] == ("on" if require_read_only else "off")
    )
    return {
        "database": database,
        "metadata_columns": observed_columns,
        "existing_record_counts": {name: len(existing[name]) for name in DESIRED_GROUPS},
        "source_output_edge_count": len(observed_source_outputs),
        "target_physical_checks": physical_checks,
        "unreviewed_existing_outputs": unreviewed_existing_outputs,
        "operations": operations,
        "action_counts": {name: action_counts.get(name, 0) for name in ("insert", "noop", "conflict")},
        "conflicts": conflicts,
        "checks": checks,
    }


def _resolve_dataset_ids(
    connection: psycopg.Connection[dict[str, Any]],
) -> dict[tuple[str, str, str], int]:
    rows = connection.execute(
        """
        SELECT d.dataset_id, a.relative_path AS archive_relative_path,
               d.member_path, d.nested_member_path
        FROM cses_meta.cses_dataset AS d
        JOIN cses_meta.cses_source_archive AS a USING (source_archive_id)
        """
    ).fetchall()
    return {
        (row["archive_relative_path"], row["member_path"], row["nested_member_path"]): int(
            row["dataset_id"]
        )
        for row in rows
    }


def _resolve_storage_ids(
    connection: psycopg.Connection[dict[str, Any]],
) -> dict[tuple[str, str], int]:
    rows = connection.execute(
        "SELECT storage_table_id, table_schema, table_name FROM cses_meta.cses_storage_table"
    ).fetchall()
    return {
        (row["table_schema"], row["table_name"]): int(row["storage_table_id"]) for row in rows
    }


def apply_storage_provenance(
    connection: psycopg.Connection[dict[str, Any]],
    desired: dict[str, list[dict[str, Any]]],
    spec: dict[str, Any],
    source_dataset_outputs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Insert the reviewed storage provenance inside the caller's transaction."""
    before = inspect_database(
        connection,
        desired,
        spec,
        source_dataset_outputs,
        require_read_only=False,
    )
    failed = [name for name, passed in before["checks"].items() if not passed]
    if failed:
        raise RuntimeError(f"Storage provenance write preflight failed: {failed}")
    if before["conflicts"]:
        raise RuntimeError("Storage provenance write preflight found existing conflicts")

    connection.execute("SELECT pg_advisory_xact_lock(hashtext('cses-storage-provenance-v1'))")
    inserted: Counter[str] = Counter()
    release = desired["alignment_releases"][0]
    cursor = connection.execute(
        """
        INSERT INTO cses_meta.cses_alignment_release
            (mapping_version, status, description, specification_sha256, approved_at)
        VALUES (%s, %s, %s, %s, transaction_timestamp())
        ON CONFLICT (mapping_version) DO NOTHING
        """,
        (
            release["mapping_version"],
            release["status"],
            release["description"],
            release["specification_sha256"],
        ),
    )
    inserted["alignment_releases"] += cursor.rowcount
    release_row = connection.execute(
        """
        SELECT alignment_release_id FROM cses_meta.cses_alignment_release
        WHERE mapping_version = %s
        """,
        (release["mapping_version"],),
    ).fetchone()
    if release_row is None:
        raise RuntimeError("Unable to resolve the storage provenance alignment release")
    release_id = int(release_row["alignment_release_id"])

    dataset_ids = _resolve_dataset_ids(connection)
    storage_ids = _resolve_storage_ids(connection)
    for record in desired["dataset_outputs"]:
        dataset_key = (
            record["archive_relative_path"],
            record["member_path"],
            record["nested_member_path"],
        )
        storage_key = (record["table_schema"], record["table_name"])
        cursor = connection.execute(
            """
            INSERT INTO cses_meta.cses_dataset_output
                (dataset_id, storage_table_id, alignment_release_id,
                 contribution_role, output_row_count)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (dataset_id, storage_table_id, contribution_role) DO NOTHING
            """,
            (
                dataset_ids[dataset_key],
                storage_ids[storage_key],
                release_id,
                record["contribution_role"],
                record["output_row_count"],
            ),
        )
        inserted["dataset_outputs"] += cursor.rowcount

    load_run = desired["load_runs"][0]
    existing_load = connection.execute(
        """
        SELECT load_run_id FROM cses_meta.cses_load_run
        WHERE validation_summary->>'storage_provenance_import_id' = %s
        """,
        (spec["provenance_release_id"],),
    ).fetchone()
    if existing_load is None:
        cursor = connection.execute(
            """
            INSERT INTO cses_meta.cses_load_run
                (survey_id, alignment_release_id, run_scope, source_manifest_sha256,
                 code_git_revision, dvc_revision, status, row_counts,
                 validation_summary, error_message, started_at, finished_at)
            VALUES (NULL, %s, %s, %s, %s, %s, %s, %s, %s, NULL,
                    transaction_timestamp(), transaction_timestamp())
            """,
            (
                release_id,
                load_run["run_scope"],
                load_run["source_manifest_sha256"],
                load_run["code_git_revision"],
                load_run["dvc_revision"],
                load_run["status"],
                Jsonb(load_run["row_counts"]),
                Jsonb(load_run["validation_summary"]),
            ),
        )
        inserted["load_runs"] += cursor.rowcount

    after = inspect_database(
        connection,
        desired,
        spec,
        source_dataset_outputs,
        require_read_only=False,
    )
    if after["conflicts"] or after["action_counts"]["insert"]:
        raise RuntimeError("Storage provenance did not reconcile to the reviewed desired state")
    return {
        "inserted_record_counts": {
            name: inserted.get(name, 0) for name in DESIRED_GROUPS
        },
        "post_write_action_counts": after["action_counts"],
        "database_mutated": bool(sum(inserted.values())),
    }


__all__ = [
    "apply_storage_provenance",
    "build_desired_state",
    "connect_database",
    "default_storage_provenance_spec_path",
    "inspect_database",
    "load_storage_provenance_spec",
    "reconcile_states",
]
