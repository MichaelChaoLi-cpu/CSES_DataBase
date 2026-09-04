"""Build and reconcile the reviewed CSES baseline metadata state."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import psycopg
from cses_schema_contract import SchemaContract, load_contract
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

RELATION_FINGERPRINT_ALGORITHM = "sha256:cses_relation_structure_v1"
METADATA_TABLE_COLUMNS = {
    "cses_survey": (
        "survey_id",
        "dataset_name",
        "survey_wave",
        "nominal_survey_year",
        "country_name",
        "country_code",
        "release_status",
        "created_at",
        "updated_at",
    ),
    "cses_source_archive": (
        "source_archive_id",
        "survey_id",
        "relative_path",
        "sha256",
        "size_bytes",
        "archive_member_count",
        "inventory_status",
        "created_at",
    ),
    "cses_dataset": (
        "dataset_id",
        "source_archive_id",
        "survey_id",
        "member_path",
        "nested_member_path",
        "module_code",
        "source_grain",
        "row_count",
        "column_count",
        "read_status",
    ),
    "cses_alignment_release": (
        "alignment_release_id",
        "mapping_version",
        "status",
        "description",
        "specification_sha256",
        "created_at",
        "approved_at",
    ),
    "cses_storage_table": (
        "storage_table_id",
        "table_schema",
        "table_name",
        "object_family",
        "module_code",
        "analytical_grain",
        "natural_key",
        "row_count",
        "column_count",
        "relation_fingerprint",
        "created_at",
        "updated_at",
    ),
    "cses_dataset_output": (
        "dataset_id",
        "storage_table_id",
        "alignment_release_id",
        "contribution_role",
        "output_row_count",
        "created_at",
    ),
    "cses_load_run": (
        "load_run_id",
        "survey_id",
        "alignment_release_id",
        "run_scope",
        "source_manifest_sha256",
        "code_git_revision",
        "dvc_revision",
        "status",
        "row_counts",
        "validation_summary",
        "error_message",
        "started_at",
        "finished_at",
    ),
}

RECORD_KEYS = {
    "surveys": ("survey_wave",),
    "source_archives": ("relative_path",),
    "datasets": ("archive_relative_path", "member_path", "nested_member_path"),
    "alignment_releases": ("mapping_version",),
    "storage_tables": ("table_schema", "table_name"),
    "dataset_outputs": (
        "archive_relative_path",
        "member_path",
        "nested_member_path",
        "table_schema",
        "table_name",
        "contribution_role",
    ),
    "load_runs": ("baseline_import_id",),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_json_value(item) for item in value]
    return value


def default_baseline_spec_path(root: Path) -> Path:
    return root / "rsc" / "specs" / "cses_baseline_metadata_v1.json"


def load_baseline_spec(path: Path) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec.get("schema_version") != 1:
        raise ValueError(f"Unsupported baseline metadata schema version: {spec.get('schema_version')}")
    if spec.get("database") != "mda":
        raise ValueError("The v1 baseline metadata contract is scoped to the mda database")
    if spec.get("alignment_release", {}).get("status") != "approved":
        raise ValueError("The reviewed import proposal must create an approved alignment release")
    if not spec["alignment_release"].get("requires_explicit_approval"):
        raise ValueError("The alignment release must retain its explicit approval gate")
    if not spec.get("approval_phrase"):
        raise ValueError("An exact write-approval phrase is required")
    if not re.fullmatch(r"md5:[0-9a-f]{32}\.dir", str(spec.get("source_data_dvc_revision", ""))):
        raise ValueError("A fixed source data.dvc directory revision is required")

    surveys = spec.get("surveys", [])
    waves = [item["survey_wave"] for item in surveys]
    datasets = [item["dataset_name"] for item in surveys]
    if len(surveys) != 10 or len(waves) != len(set(waves)) or len(datasets) != len(set(datasets)):
        raise ValueError("The baseline must define ten unique CSES survey waves")

    archives = spec.get("source_archives", [])
    paths = [item["path"] for item in archives]
    if len(archives) != 11 or len(paths) != len(set(paths)):
        raise ValueError("The baseline must define eleven unique source archives")
    if set(item["survey_wave"] for item in archives) - set(waves):
        raise ValueError("Every source archive must reference a declared survey wave")

    storage_names = [item["name"] for item in spec.get("storage_relations", [])]
    if len(storage_names) != 22 or len(storage_names) != len(set(storage_names)):
        raise ValueError("The baseline must describe the approved 22 physical CSES relations")
    direct_names = [item["relation"] for item in spec.get("direct_outputs", [])]
    if len(direct_names) != 7 or len(direct_names) != len(set(direct_names)):
        raise ValueError("The baseline must define seven local final-table provenance sources")
    if set(direct_names) - set(storage_names):
        raise ValueError("Every direct output must reference a declared storage relation")
    return spec


def split_source_dataset(value: str) -> tuple[str, str, str]:
    parts = value.split("::")
    if len(parts) < 2 or not parts[0].startswith("data/raw/"):
        raise ValueError(f"Invalid repository source dataset reference: {value}")
    return parts[0], parts[1], "::".join(parts[2:])


def _read_json(root: Path, relative_path: str) -> dict[str, Any]:
    return json.loads((root / relative_path).read_text(encoding="utf-8"))


def _git_revision(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _archive_records(root: Path, spec: dict[str, Any], release_manifest: dict[str, Any]) -> tuple[list[dict], dict]:
    expected = {item["path"]: item for item in spec["source_archives"]}
    recorded = {item["path"]: item for item in release_manifest["raw_archives"]}
    exact_manifest_set = set(expected) == set(recorded)
    manifest_matches = exact_manifest_set and all(
        recorded[path]["sha256"] == item["sha256"] and recorded[path]["size"] == item["size"]
        for path, item in expected.items()
    )
    files_match = all(
        (root / path).is_file()
        and (root / path).stat().st_size == item["size"]
        and sha256_file(root / path) == item["sha256"]
        for path, item in expected.items()
    )
    records = [
        {
            "relative_path": item["path"],
            "survey_wave": item["survey_wave"],
            "sha256": item["sha256"],
            "size_bytes": item["size"],
            "archive_member_count": None,
            "inventory_status": "validated",
        }
        for item in sorted(expected.values(), key=lambda row: row["path"])
    ]
    return records, {
        "archive_set_matches_release_manifest": exact_manifest_set,
        "archive_fingerprints_match_release_manifest": manifest_matches,
        "archive_files_match_declared_fingerprints": files_match,
    }


def _dataset_record(
    source_dataset: str,
    survey_wave: str,
    module_code: str | None,
    source_grain: str | None,
    row_count: int | None,
    column_count: int | None,
) -> dict[str, Any]:
    archive, member, nested = split_source_dataset(source_dataset)
    return {
        "archive_relative_path": archive,
        "survey_wave": survey_wave,
        "member_path": member,
        "nested_member_path": nested,
        "module_code": module_code,
        "source_grain": source_grain,
        "row_count": row_count,
        "column_count": column_count,
        "read_status": "readable",
    }


def _inventory_datasets(root: Path, spec: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    inventory = spec["dataset_inventory"]
    grains = inventory["source_grain_by_module"]
    records: dict[tuple[str, str, str], dict[str, Any]] = {}
    with (root / inventory["manifest_path"]).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            row_count = int(row["row_count"])
            if inventory["zero_row_count_means_unknown"] and row_count == 0:
                row_count = None
            record = _dataset_record(
                row["source_dataset"],
                row["survey_wave"],
                row["module"],
                grains.get(row["module"]),
                row_count,
                int(row["variable_count"]),
            )
            key = tuple(record[field] for field in RECORD_KEYS["datasets"])
            if key in records and records[key] != record:
                raise ValueError(f"Conflicting inventory rows for source dataset: {row['source_dataset']}")
            records[key] = record
    return records


def _direct_output_records(
    root: Path,
    spec: dict[str, Any],
    datasets: dict[tuple[str, str, str], dict[str, Any]],
    storage_by_name: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    output_records: dict[tuple[Any, ...], dict[str, Any]] = {}
    archive_waves = {item["path"]: item["survey_wave"] for item in spec["source_archives"]}
    mapping_version = spec["alignment_release"]["mapping_version"]
    for output in spec["direct_outputs"]:
        path = root / output["artifact_path"]
        frame = pd.read_parquet(
            path,
            columns=[
                output["survey_wave_column"],
                output["source_archive_column"],
                output["source_submodule_column"],
            ],
        ).dropna()
        rows = frame.drop_duplicates().sort_values(list(frame.columns)).itertuples(index=False, name=None)
        for survey_wave, archive, submodules in rows:
            if not str(archive).startswith("data/raw/"):
                continue
            for submodule in str(submodules).split(" | "):
                source_dataset = f"{archive}::{submodule}"
                archive_path, member, nested = split_source_dataset(source_dataset)
                if archive_path not in archive_waves:
                    raise ValueError(f"Output references an undeclared source archive: {archive_path}")
                if archive_waves[archive_path] != str(survey_wave):
                    raise ValueError(f"Output wave and archive wave disagree for {source_dataset}")
                dataset_key = (archive_path, member, nested)
                if dataset_key not in datasets:
                    datasets[dataset_key] = _dataset_record(
                        source_dataset,
                        str(survey_wave),
                        output["fallback_module_code"],
                        output["fallback_source_grain"],
                        None,
                        None,
                    )
                storage = storage_by_name[output["relation"]]
                record = {
                    "archive_relative_path": archive_path,
                    "member_path": member,
                    "nested_member_path": nested,
                    "table_schema": storage["table_schema"],
                    "table_name": storage["table_name"],
                    "mapping_version": mapping_version,
                    "contribution_role": "source",
                    "output_row_count": storage["row_count"],
                }
                key = tuple(record[field] for field in RECORD_KEYS["dataset_outputs"])
                output_records[key] = record
    return [output_records[key] for key in sorted(output_records)]


def _relation_fingerprint(relation: dict[str, Any], contract_relation: Any) -> str:
    physical = relation["physical"]
    descriptor = {
        "algorithm": RELATION_FINGERPRINT_ALGORITHM,
        "table_schema": contract_relation.target_schema,
        "table_name": contract_relation.name,
        "row_count": physical["row_count"],
        "columns": [
            {
                "position": column["position"],
                "name": column["name"],
                "data_type": column["data_type"],
                "not_null": column["not_null"],
            }
            for column in physical["columns"]
        ],
    }
    return canonical_sha256(descriptor)


def _storage_records(
    spec: dict[str, Any], schema_contract: SchemaContract, postflight: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, bool]]:
    metadata = {item["name"]: item for item in spec["storage_relations"]}
    evidence = {item["contract"]["name"]: item for item in postflight["objects"]}
    contract = {item.name: item for item in schema_contract.relations}
    sets_match = set(metadata) == set(evidence) == set(contract)
    records = []
    if sets_match:
        for name in sorted(contract):
            relation = contract[name]
            physical = evidence[name]["physical"]
            records.append(
                {
                    "table_schema": relation.target_schema,
                    "table_name": name,
                    "object_family": relation.family,
                    "module_code": metadata[name]["module_code"],
                    "analytical_grain": metadata[name]["analytical_grain"],
                    "natural_key": list(relation.natural_key),
                    "row_count": physical["row_count"],
                    "column_count": physical["column_count"],
                    "relation_fingerprint": _relation_fingerprint(evidence[name], relation),
                }
            )
    return records, {
        "storage_relation_sets_match": sets_match,
        "postflight_is_valid": bool(postflight.get("post_migration_valid")),
        "all_storage_relations_are_functional_physical": sets_match
        and all(item["layout_state"] == "functional_physical" for item in evidence.values()),
    }


def build_desired_state(root: Path, spec_path: Path | None = None) -> tuple[dict[str, list[dict]], dict[str, Any]]:
    spec_path = spec_path or default_baseline_spec_path(root)
    spec = load_baseline_spec(spec_path)
    evidence = spec["evidence"]
    release_manifest = _read_json(root, evidence["local_release_manifest"])
    postflight = _read_json(root, evidence["migration_postflight"])
    migration_validation = _read_json(root, evidence["migration_validation"])
    schema_contract = load_contract(root / evidence["schema_contract"])

    archives, archive_checks = _archive_records(root, spec, release_manifest)
    storage, storage_checks = _storage_records(spec, schema_contract, postflight)
    storage_by_name = {item["table_name"]: item for item in storage}
    datasets_by_key = _inventory_datasets(root, spec)
    outputs = _direct_output_records(root, spec, datasets_by_key, storage_by_name)
    datasets = [datasets_by_key[key] for key in sorted(datasets_by_key)]

    surveys = [
        {
            **item,
            "country_name": "Cambodia",
            "country_code": "KHM",
            "release_status": "baseline",
        }
        for item in sorted(spec["surveys"], key=lambda row: row["survey_wave"])
    ]
    alignment_release = {
        "mapping_version": spec["alignment_release"]["mapping_version"],
        "status": spec["alignment_release"]["status"],
        "description": spec["alignment_release"]["description"],
        "specification_sha256": sha256_file(spec_path),
    }
    evidence_hashes = {
        name: {"path": path, "sha256": sha256_file(root / path)}
        for name, path in sorted(evidence.items())
    }
    source_manifest_sha256 = canonical_sha256(
        [{field: item[field] for field in ("relative_path", "sha256", "size_bytes")} for item in archives]
    )
    dvc_revision = str(spec["source_data_dvc_revision"])
    validation_summary = {
        "baseline_import_id": spec["baseline_id"],
        "evidence": evidence_hashes,
        "lineage_gap_count": len(spec["lineage_gaps"]),
        "relation_fingerprint_algorithm": RELATION_FINGERPRINT_ALGORITHM,
        "schema_migration_validation_passed": bool(migration_validation.get("validation_passed")),
    }
    load_run = {
        "baseline_import_id": spec["baseline_id"],
        "survey_wave": None,
        "mapping_version": alignment_release["mapping_version"],
        "run_scope": spec["load_run"]["run_scope"],
        "source_manifest_sha256": source_manifest_sha256,
        "code_git_revision": _git_revision(root),
        "dvc_revision": dvc_revision,
        "status": spec["load_run"]["status"],
        "row_counts": {f"{item['table_schema']}.{item['table_name']}": item["row_count"] for item in storage},
        "validation_summary": validation_summary,
        "error_message": None,
    }
    desired = {
        "surveys": surveys,
        "source_archives": archives,
        "datasets": datasets,
        "alignment_releases": [alignment_release],
        "storage_tables": storage,
        "dataset_outputs": outputs,
        "load_runs": [load_run],
    }
    archive_paths = {item["relative_path"] for item in archives}
    survey_waves = {item["survey_wave"] for item in surveys}
    dataset_keys = {tuple(item[field] for field in RECORD_KEYS["datasets"]) for item in datasets}
    local_checks = {
        **archive_checks,
        **storage_checks,
        "migration_validation_passed": bool(migration_validation.get("validation_passed")),
        "all_datasets_reference_declared_archives": all(
            item["archive_relative_path"] in archive_paths for item in datasets
        ),
        "all_datasets_reference_declared_surveys": all(item["survey_wave"] in survey_waves for item in datasets),
        "all_output_datasets_are_registered": all(
            (item["archive_relative_path"], item["member_path"], item["nested_member_path"]) in dataset_keys
            for item in outputs
        ),
        "seven_direct_output_relations_have_edges": len({item["table_name"] for item in outputs}) == 7,
        "source_data_dvc_revision_is_declared": bool(re.fullmatch(r"md5:[0-9a-f]{32}\.dir", dvc_revision)),
    }
    diagnostics = {
        "spec": {
            "path": str(spec_path.relative_to(root)),
            "sha256": sha256_file(spec_path),
            "baseline_id": spec["baseline_id"],
            "approval_phrase": spec["approval_phrase"],
            "approval_required": True,
        },
        "evidence": evidence_hashes,
        "pipeline_dependencies": spec["pipeline_dependencies"],
        "lineage_gaps": spec["lineage_gaps"],
        "record_counts": {name: len(records) for name, records in desired.items()},
        "local_checks": local_checks,
    }
    return desired, diagnostics


def _fetch_existing_state(connection: psycopg.Connection[dict[str, Any]], baseline_id: str) -> dict[str, list[dict]]:
    queries = {
        "surveys": """
            SELECT dataset_name, survey_wave, nominal_survey_year, country_name,
                   country_code, release_status
            FROM cses_meta.cses_survey ORDER BY survey_wave
        """,
        "source_archives": """
            SELECT a.relative_path, s.survey_wave, a.sha256, a.size_bytes,
                   a.archive_member_count, a.inventory_status
            FROM cses_meta.cses_source_archive AS a
            LEFT JOIN cses_meta.cses_survey AS s USING (survey_id)
            ORDER BY a.relative_path
        """,
        "datasets": """
            SELECT a.relative_path AS archive_relative_path, s.survey_wave,
                   d.member_path, d.nested_member_path, d.module_code, d.source_grain,
                   d.row_count, d.column_count, d.read_status
            FROM cses_meta.cses_dataset AS d
            JOIN cses_meta.cses_source_archive AS a USING (source_archive_id)
            LEFT JOIN cses_meta.cses_survey AS s ON s.survey_id = d.survey_id
            ORDER BY a.relative_path, d.member_path, d.nested_member_path
        """,
        "alignment_releases": """
            SELECT mapping_version, status, description, specification_sha256
            FROM cses_meta.cses_alignment_release ORDER BY mapping_version
        """,
        "storage_tables": """
            SELECT table_schema, table_name, object_family, module_code,
                   analytical_grain, natural_key, row_count, column_count,
                   relation_fingerprint
            FROM cses_meta.cses_storage_table ORDER BY table_schema, table_name
        """,
        "dataset_outputs": """
            SELECT a.relative_path AS archive_relative_path, d.member_path,
                   d.nested_member_path, st.table_schema, st.table_name,
                   ar.mapping_version, o.contribution_role, o.output_row_count
            FROM cses_meta.cses_dataset_output AS o
            JOIN cses_meta.cses_dataset AS d USING (dataset_id)
            JOIN cses_meta.cses_source_archive AS a USING (source_archive_id)
            JOIN cses_meta.cses_storage_table AS st USING (storage_table_id)
            LEFT JOIN cses_meta.cses_alignment_release AS ar USING (alignment_release_id)
            ORDER BY a.relative_path, d.member_path, d.nested_member_path,
                     st.table_schema, st.table_name, o.contribution_role
        """,
        "load_runs": """
            SELECT validation_summary->>'baseline_import_id' AS baseline_import_id,
                   s.survey_wave, ar.mapping_version, lr.run_scope,
                   lr.source_manifest_sha256, lr.code_git_revision, lr.dvc_revision,
                   lr.status, lr.row_counts, lr.validation_summary, lr.error_message
            FROM cses_meta.cses_load_run AS lr
            LEFT JOIN cses_meta.cses_survey AS s USING (survey_id)
            LEFT JOIN cses_meta.cses_alignment_release AS ar USING (alignment_release_id)
            WHERE validation_summary->>'baseline_import_id' = %s
            ORDER BY lr.load_run_id
        """,
    }
    existing = {}
    for name, query in queries.items():
        params: tuple[object, ...] = (baseline_id,) if name == "load_runs" else ()
        existing[name] = [normalize_json_value(dict(row)) for row in connection.execute(query, params).fetchall()]
    return existing


def _record_key(record: dict[str, Any], fields: Iterable[str]) -> tuple[Any, ...]:
    return tuple(normalize_json_value(record.get(field)) for field in fields)


def reconcile_states(
    desired: dict[str, list[dict]], existing: dict[str, list[dict]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    operations = []
    conflicts = []
    for group, desired_records in desired.items():
        key_fields = RECORD_KEYS[group]
        existing_by_key: dict[tuple[Any, ...], list[dict]] = {}
        for record in existing[group]:
            existing_by_key.setdefault(_record_key(record, key_fields), []).append(record)
        for record in desired_records:
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
                {
                    "group": group,
                    "key": dict(zip(key_fields, key, strict=True)),
                    "action": action,
                }
            )
    operations.sort(key=lambda item: (item["group"], canonical_json(item["key"])))
    return operations, conflicts


def inspect_database(
    connection: psycopg.Connection[dict[str, Any]],
    desired: dict[str, list[dict]],
    baseline_id: str,
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

    physical_checks = []
    for record in desired["storage_tables"]:
        row = connection.execute(
            sql.SQL("SELECT count(*) AS row_count FROM {}.{}").format(
                sql.Identifier(record["table_schema"]), sql.Identifier(record["table_name"])
            )
        ).fetchone()
        column_count = connection.execute(
            """
            SELECT count(*) AS column_count
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            """,
            (record["table_schema"], record["table_name"]),
        ).fetchone()["column_count"]
        physical_checks.append(
            {
                "table_schema": record["table_schema"],
                "table_name": record["table_name"],
                "expected_row_count": record["row_count"],
                "observed_row_count": row["row_count"],
                "expected_column_count": record["column_count"],
                "observed_column_count": column_count,
                "matches": row["row_count"] == record["row_count"]
                and column_count == record["column_count"],
            }
        )

    existing = _fetch_existing_state(connection, baseline_id)
    operations, conflicts = reconcile_states(desired, existing)
    action_counts = Counter(item["action"] for item in operations)
    checks = {
        "database_name_matches": database["database"] == "mda",
        "metadata_table_columns_match_v1_ddl": all(
            tuple(observed_columns[name]) == expected for name, expected in METADATA_TABLE_COLUMNS.items()
        ),
        "physical_relations_match_baseline_evidence": all(item["matches"] for item in physical_checks),
        "no_existing_metadata_conflicts": not conflicts,
    }
    checks["transaction_is_read_only" if require_read_only else "transaction_is_read_write"] = (
        database["transaction_read_only"] == ("on" if require_read_only else "off")
    )
    return {
        "database": database,
        "metadata_columns": observed_columns,
        "existing_record_counts": {name: len(records) for name, records in existing.items()},
        "physical_relation_checks": physical_checks,
        "operations": operations,
        "action_counts": {name: action_counts.get(name, 0) for name in ("insert", "noop", "conflict")},
        "conflicts": conflicts,
        "checks": checks,
    }


def connection_arguments(
    database: str, host: str | None = None, port: int = 5432, user: str | None = None
) -> dict[str, object]:
    arguments: dict[str, object] = {"dbname": database}
    if host:
        arguments.update(host=host, port=port)
    if user:
        arguments["user"] = user
    return arguments


def connect_database(arguments: dict[str, object]) -> psycopg.Connection[dict[str, Any]]:
    return psycopg.connect(**arguments, row_factory=dict_row)


def _selected_id(
    connection: psycopg.Connection[dict[str, Any]],
    table: str,
    id_column: str,
    key_column: str,
    key_value: object,
) -> int:
    row = connection.execute(
        sql.SQL("SELECT {} AS id FROM cses_meta.{} WHERE {} = %s").format(
            sql.Identifier(id_column), sql.Identifier(table), sql.Identifier(key_column)
        ),
        (key_value,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Unable to resolve {table}.{id_column} for {key_column}={key_value}")
    return int(row["id"])


def apply_baseline_metadata(
    connection: psycopg.Connection[dict[str, Any]],
    desired: dict[str, list[dict]],
    baseline_id: str,
) -> dict[str, Any]:
    """Insert a conflict-free baseline inside the caller's database transaction."""
    before = inspect_database(connection, desired, baseline_id, require_read_only=False)
    failed = [name for name, passed in before["checks"].items() if not passed]
    if failed:
        raise RuntimeError(f"Baseline metadata write preflight failed: {failed}")
    if before["conflicts"]:
        raise RuntimeError("Baseline metadata write preflight found existing conflicts")

    connection.execute("SELECT pg_advisory_xact_lock(hashtext('cses-baseline-metadata-v1'))")
    inserted: Counter[str] = Counter()
    survey_ids: dict[str, int] = {}
    for record in desired["surveys"]:
        cursor = connection.execute(
            """
            INSERT INTO cses_meta.cses_survey
                (dataset_name, survey_wave, nominal_survey_year, country_name,
                 country_code, release_status)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            tuple(record[field] for field in (
                "dataset_name",
                "survey_wave",
                "nominal_survey_year",
                "country_name",
                "country_code",
                "release_status",
            )),
        )
        inserted["surveys"] += cursor.rowcount
        survey_ids[record["survey_wave"]] = _selected_id(
            connection, "cses_survey", "survey_id", "survey_wave", record["survey_wave"]
        )

    archive_ids: dict[str, int] = {}
    for record in desired["source_archives"]:
        cursor = connection.execute(
            """
            INSERT INTO cses_meta.cses_source_archive
                (survey_id, relative_path, sha256, size_bytes,
                 archive_member_count, inventory_status)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (relative_path) DO NOTHING
            """,
            (
                survey_ids[record["survey_wave"]],
                record["relative_path"],
                record["sha256"],
                record["size_bytes"],
                record["archive_member_count"],
                record["inventory_status"],
            ),
        )
        inserted["source_archives"] += cursor.rowcount
        archive_ids[record["relative_path"]] = _selected_id(
            connection,
            "cses_source_archive",
            "source_archive_id",
            "relative_path",
            record["relative_path"],
        )

    dataset_ids: dict[tuple[str, str, str], int] = {}
    for record in desired["datasets"]:
        archive_id = archive_ids[record["archive_relative_path"]]
        cursor = connection.execute(
            """
            INSERT INTO cses_meta.cses_dataset
                (source_archive_id, survey_id, member_path, nested_member_path,
                 module_code, source_grain, row_count, column_count, read_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_archive_id, member_path, nested_member_path) DO NOTHING
            """,
            (
                archive_id,
                survey_ids[record["survey_wave"]],
                record["member_path"],
                record["nested_member_path"],
                record["module_code"],
                record["source_grain"],
                record["row_count"],
                record["column_count"],
                record["read_status"],
            ),
        )
        inserted["datasets"] += cursor.rowcount
        row = connection.execute(
            """
            SELECT dataset_id
            FROM cses_meta.cses_dataset
            WHERE source_archive_id = %s AND member_path = %s AND nested_member_path = %s
            """,
            (archive_id, record["member_path"], record["nested_member_path"]),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Unable to resolve dataset ID for {record}")
        key = tuple(record[field] for field in RECORD_KEYS["datasets"])
        dataset_ids[key] = int(row["dataset_id"])

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
    release_id = _selected_id(
        connection,
        "cses_alignment_release",
        "alignment_release_id",
        "mapping_version",
        release["mapping_version"],
    )

    storage_ids: dict[tuple[str, str], int] = {}
    for record in desired["storage_tables"]:
        cursor = connection.execute(
            """
            INSERT INTO cses_meta.cses_storage_table
                (table_schema, table_name, object_family, module_code,
                 analytical_grain, natural_key, row_count, column_count,
                 relation_fingerprint)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (table_schema, table_name) DO NOTHING
            """,
            (
                record["table_schema"],
                record["table_name"],
                record["object_family"],
                record["module_code"],
                record["analytical_grain"],
                record["natural_key"],
                record["row_count"],
                record["column_count"],
                record["relation_fingerprint"],
            ),
        )
        inserted["storage_tables"] += cursor.rowcount
        row = connection.execute(
            """
            SELECT storage_table_id FROM cses_meta.cses_storage_table
            WHERE table_schema = %s AND table_name = %s
            """,
            (record["table_schema"], record["table_name"]),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Unable to resolve storage-table ID for {record}")
        storage_ids[(record["table_schema"], record["table_name"])] = int(row["storage_table_id"])

    for record in desired["dataset_outputs"]:
        dataset_key = tuple(record[field] for field in RECORD_KEYS["datasets"])
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
                storage_ids[(record["table_schema"], record["table_name"])],
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
        WHERE validation_summary->>'baseline_import_id' = %s
        """,
        (baseline_id,),
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

    after = inspect_database(connection, desired, baseline_id, require_read_only=False)
    if after["conflicts"] or after["action_counts"]["insert"]:
        raise RuntimeError("Baseline metadata did not reconcile to the reviewed desired state")
    return {
        "inserted_record_counts": {
            name: inserted.get(name, 0)
            for name in (
                "surveys",
                "source_archives",
                "datasets",
                "alignment_releases",
                "storage_tables",
                "dataset_outputs",
                "load_runs",
            )
        },
        "post_write_action_counts": after["action_counts"],
        "database_mutated": bool(sum(inserted.values())),
    }
