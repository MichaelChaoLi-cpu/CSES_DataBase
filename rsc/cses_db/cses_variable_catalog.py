"""Build, inspect, and apply the reviewed CSES variable catalog."""

from __future__ import annotations

import csv
import io
import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import psycopg
from cses_baseline_metadata import (
    canonical_json,
    canonical_sha256,
    connect_database,
    normalize_json_value,
    sha256_file,
)
from cses_survey_date_contract import hh_summary_extension
from inventory_cses_archives import DataSource
from psycopg.types.json import Jsonb

DATASET_KEY = ("archive_relative_path", "member_path", "nested_member_path")
SOURCE_VARIABLE_KEY = (*DATASET_KEY, "variable_name")
CANONICAL_VARIABLE_KEY = ("target_table", "canonical_name")
VARIABLE_MAPPING_KEY = (*DATASET_KEY, "target_table", "canonical_name", "mapping_version")
DESIRED_GROUPS = (
    "alignment_releases",
    "source_variables",
    "canonical_variables",
    "variable_mappings",
    "load_runs",
)
RECORD_KEYS = {
    "alignment_releases": ("mapping_version",),
    "source_variables": SOURCE_VARIABLE_KEY,
    "canonical_variables": CANONICAL_VARIABLE_KEY,
    "variable_mappings": VARIABLE_MAPPING_KEY,
    "load_runs": ("variable_catalog_import_id",),
}

ALIGNMENT_TABLE_COLUMNS = {
    "cses_instrument": (
        "instrument_id", "survey_id", "instrument_type", "source_file", "source_url",
        "source_sha256", "document_title", "publication_date", "language_code",
        "documentation_status", "imported_at",
    ),
    "cses_question": (
        "question_id", "instrument_id", "question_code", "question_text", "section_name",
        "sequence_number", "source_page", "response_options", "skip_instruction",
        "question_grain", "repeat_context", "is_exact_question_text", "documentation_status",
    ),
    "cses_source_variable": (
        "source_variable_id", "dataset_id", "question_id", "variable_name",
        "variable_position", "storage_type", "variable_label", "value_labels",
        "question_link_status", "question_link_role", "alignment_status",
    ),
    "cses_canonical_variable": (
        "canonical_variable_id", "target_table", "canonical_name", "database_type",
        "measure_type", "canonical_definition", "analytical_grain", "status",
    ),
    "cses_variable_mapping": (
        "variable_mapping_id", "dataset_id", "canonical_variable_id",
        "alignment_release_id", "source_variable_names", "source_kind",
        "transformation_rule", "alignment_status", "observed_row_count",
        "observed_nonnull_count", "observed_distinct_count", "observation_status",
        "profiled_at", "created_at",
    ),
    "cses_value_mapping": (
        "variable_mapping_id", "source_value", "source_label", "canonical_value",
        "canonical_label", "alignment_status",
    ),
}


def default_variable_catalog_spec_path(root: Path) -> Path:
    return root / "rsc" / "specs" / "cses_variable_catalog_v1.json"


def _record_key(record: dict[str, Any], fields: Iterable[str]) -> tuple[Any, ...]:
    return tuple(normalize_json_value(record.get(field)) for field in fields)


def _sorted_records(records: Iterable[dict[str, Any]], fields: Iterable[str]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda record: canonical_json(_record_key(record, fields)))


def _git_revision(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _snake_case(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _dataset_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return tuple(str(record.get(field) or "") for field in DATASET_KEY)  # type: ignore[return-value]


def load_variable_catalog_spec(path: Path) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec.get("schema_version") != 1:
        raise ValueError(f"Unsupported variable catalog schema version: {spec.get('schema_version')}")
    if spec.get("database") != "mda":
        raise ValueError("The variable catalog release is scoped to the mda database")
    release = spec.get("alignment_release", {})
    if release.get("status") != "approved" or not release.get("requires_explicit_approval"):
        raise ValueError("The variable catalog release must be approved and explicitly gated")
    if spec.get("approval_phrase") != "ACCEPT-CSES-VARIABLE-CATALOG-V1":
        raise ValueError("The variable catalog release must retain its exact approval phrase")
    if not re.fullmatch(r"md5:[0-9a-f]{32}\.dir", str(spec.get("source_data_dvc_revision", ""))):
        raise ValueError("A fixed source data.dvc directory revision is required")
    rules = spec.get("module_rules", [])
    modules = [rule["module_code"] for rule in rules]
    targets = [rule["target_table"] for rule in rules]
    if len(rules) != 7 or len(set(modules)) != 7 or len(set(targets)) != 7:
        raise ValueError("Variable catalog v1 must define seven unique module/target rules")
    if spec.get("questionnaire_policy", {}).get("instrument_count") != 0:
        raise ValueError("Variable catalog v1 must not synthesize instruments")
    if spec.get("questionnaire_policy", {}).get("question_count") != 0:
        raise ValueError("Variable catalog v1 must not synthesize questions")
    if spec.get("value_mapping_policy", {}).get("count") != 0:
        raise ValueError("Variable catalog v1 must not infer canonical value mappings")
    if len(spec.get("survey_date_sources", [])) != 3:
        raise ValueError("Variable catalog v1 requires three exact-date sources")
    return spec


def _read_verified_json(root: Path, descriptor: dict[str, str]) -> dict[str, Any]:
    path = root / descriptor["path"]
    if not path.is_file() or sha256_file(path) != descriptor["sha256"]:
        raise ValueError(f"Evidence fingerprint mismatch: {descriptor['path']}")
    return json.loads(path.read_text(encoding="utf-8"))


def _stata_storage_type(value: Any) -> str:
    numeric = {251: "stata_byte", 252: "stata_int16", 253: "stata_int32", 254: "stata_float32", 255: "stata_float64"}
    letter = {"b": "stata_byte", "h": "stata_int16", "l": "stata_int32", "f": "stata_float32", "d": "stata_float64"}
    if isinstance(value, int):
        if value in numeric:
            return numeric[value]
        if 1 <= value <= 2045:
            return f"stata_str{value}"
    text = str(value)
    if text in letter:
        return letter[text]
    if text.isdigit():
        width = int(text)
        return _stata_storage_type(width)
    return f"stata_{text.lower()}"


def _label_value(value: Any) -> str:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if value.is_integer():
            return str(int(value))
    return str(value)


def _read_stata_catalog(root: Path, dataset: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    members = tuple(value for value in (dataset["member_path"], dataset["nested_member_path"]) if value)
    source = DataSource(root / dataset["archive_relative_path"], members)
    input_obj: Path | io.BytesIO = io.BytesIO(source.read_bytes()) if members else source.root_file
    reader = pd.io.stata.StataReader(input_obj, convert_categoricals=False)
    try:
        labels = reader.variable_labels()
        value_label_sets = reader.value_labels()
        names = list(reader._varlist)
        storage_types = list(reader._typlist)
        label_sets = list(reader._lbllist)
        row_count = int(reader._nobs)
        column_count = int(reader._nvar)
    finally:
        close = getattr(reader, "close", None)
        if close is not None:
            close()
    if not (len(names) == len(storage_types) == len(label_sets) == column_count):
        raise ValueError(f"Incomplete Stata metadata for dataset: {_dataset_key(dataset)}")
    rows: list[dict[str, Any]] = []
    for position, (name, storage_type, label_set) in enumerate(
        zip(names, storage_types, label_sets, strict=True), start=1
    ):
        raw_value_labels = value_label_sets.get(label_set, {}) if label_set else {}
        value_labels = (
            {
                key: str(value)
                for key, value in sorted(
                    ((_label_value(key), value) for key, value in raw_value_labels.items()),
                    key=lambda item: item[0],
                )
            }
            if raw_value_labels
            else None
        )
        rows.append(
            {
                **{field: dataset[field] for field in DATASET_KEY},
                "question_id": None,
                "variable_name": str(name),
                "variable_position": position,
                "storage_type": _stata_storage_type(storage_type),
                "variable_label": labels.get(name) or None,
                "value_labels": value_labels,
                "question_link_status": None,
                "question_link_role": None,
                "alignment_status": "documented",
            }
        )
    return rows, {"row_count": row_count, "column_count": column_count}


def _load_dictionary(path: Path, module_code: str) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if module_code == "SURVEY_DATE":
        return [
            {
                "canonical_name": _snake_case(row["varname"]),
                "survey_wave": "",
                "raw_name": row["column_in_raw_sav"].strip(),
                "source_kind": row["source_kind"].strip(),
                "measure_type": row["measure_type"].strip(),
                "canonical_definition": row["canonical_text"].strip(),
            }
            for row in rows
        ]
    return [
        {
            "canonical_name": row["canonical_varname"].strip(),
            "survey_wave": row["dataset_name"].removeprefix("CSES ").strip(),
            "raw_name": row["column_in_raw_sav"].strip(),
            "source_kind": row["source_kind"].strip(),
            "measure_type": row["measure_type"].strip(),
            "canonical_definition": row["canonical_text"].strip(),
        }
        for row in rows
    ]


def _canonical_lookup(
    rules: list[dict[str, Any]], dictionaries: dict[str, list[dict[str, str]]]
) -> dict[tuple[str, str], tuple[str, str]]:
    lookup: dict[tuple[str, str], tuple[str, str]] = {}
    for rule in rules:
        target = rule["target_table"]
        for row in dictionaries[rule["module_code"]]:
            key = (target, row["canonical_name"])
            value = (row["measure_type"], row["canonical_definition"])
            if key in lookup and lookup[key] != value:
                raise ValueError(f"Conflicting canonical metadata: {target}.{row['canonical_name']}")
            lookup[key] = value
    for row in hh_summary_extension().to_dict("records"):
        key = ("final_HH_CSES", str(row["varname"]))
        value = (str(row["measure_type"]), str(row["canonical_text"]))
        if key in lookup and lookup[key] != value:
            raise ValueError(f"Conflicting household date metadata: {key}")
        lookup[key] = value
    return lookup


def _build_standard_mappings(
    spec: dict[str, Any],
    datasets: list[dict[str, Any]],
    source_variables: list[dict[str, Any]],
    dictionaries: dict[str, list[dict[str, str]]],
    canonical_definitions: dict[tuple[str, str], tuple[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    variables_by_dataset: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for record in source_variables:
        variables_by_dataset[_dataset_key(record)].add(record["variable_name"])
    datasets_by_wave_module: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for dataset in datasets:
        datasets_by_wave_module[(dataset["survey_wave"], dataset["module_code"])].append(dataset)

    mappings: dict[tuple[Any, ...], dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []
    mapping_version = spec["alignment_release"]["mapping_version"]
    for rule in spec["module_rules"]:
        module = rule["module_code"]
        if module == "SURVEY_DATE":
            continue
        target = rule["target_table"]
        candidates_by_wave: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for source_module in rule["source_modules"]:
            for (wave, observed_module), candidates in datasets_by_wave_module.items():
                if observed_module == source_module:
                    candidates_by_wave[wave].extend(candidates)
        for row in dictionaries[module]:
            if not row["raw_name"]:
                continue
            matched = []
            for dataset in candidates_by_wave[row["survey_wave"]]:
                if row["raw_name"] in variables_by_dataset[_dataset_key(dataset)]:
                    matched.append(dataset)
            if not matched:
                unresolved.append(
                    {
                        "module_code": module,
                        "target_table": target,
                        "survey_wave": row["survey_wave"],
                        "canonical_name": row["canonical_name"],
                        "raw_name": row["raw_name"],
                    }
                )
                continue
            for dataset in matched:
                key = (*_dataset_key(dataset), target, row["canonical_name"], mapping_version)
                existing = mappings.setdefault(
                    key,
                    {
                        **{field: dataset[field] for field in DATASET_KEY},
                        "target_table": target,
                        "canonical_name": row["canonical_name"],
                        "mapping_version": mapping_version,
                        "source_variable_names": [],
                        "source_kind": "explicit",
                        "transformation_rule": "",
                        "alignment_status": "tested",
                        "observed_row_count": None,
                        "observed_nonnull_count": None,
                        "observed_distinct_count": None,
                        "observation_status": None,
                        "profiled_at": None,
                    },
                )
                existing["source_variable_names"].append(row["raw_name"])
                if row["source_kind"] == "derived":
                    existing["source_kind"] = "derived"
    for record in mappings.values():
        record["source_variable_names"] = sorted(set(record["source_variable_names"]))
        definition = canonical_definitions[(record["target_table"], record["canonical_name"])][1]
        names = ", ".join(record["source_variable_names"])
        record["transformation_rule"] = (
            f"Reviewed builder dictionary maps source field(s) [{names}] to "
            f"{record['target_table']}.{record['canonical_name']}. Canonical semantics: {definition}"
        )
    return list(mappings.values()), unresolved


def _build_survey_date_mappings(
    spec: dict[str, Any],
    datasets_by_key: dict[tuple[str, str, str], dict[str, Any]],
    source_variables: list[dict[str, Any]],
    canonical_definitions: dict[tuple[str, str], tuple[str, str]],
) -> list[dict[str, Any]]:
    variables_by_dataset: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for record in source_variables:
        variables_by_dataset[_dataset_key(record)].add(record["variable_name"])
    mappings: list[dict[str, Any]] = []
    mapping_version = spec["alignment_release"]["mapping_version"]
    for source in spec["survey_date_sources"]:
        key = _dataset_key(source)
        dataset = datasets_by_key.get(key)
        if dataset is None:
            raise ValueError(f"Exact-date source is not registered: {key}")
        wave = source["survey_wave"]
        for canonical_name, source_names in spec["survey_date_variable_rules"][wave].items():
            missing = sorted(set(source_names) - variables_by_dataset[key])
            if missing:
                raise ValueError(f"Exact-date mapping source variables are absent from {key}: {missing}")
            definition = canonical_definitions[("final_SURVEY_DATE_CSES", canonical_name)][1]
            mappings.append(
                {
                    **{field: dataset[field] for field in DATASET_KEY},
                    "target_table": "final_SURVEY_DATE_CSES",
                    "canonical_name": canonical_name,
                    "mapping_version": mapping_version,
                    "source_variable_names": sorted(set(source_names)),
                    "source_kind": "derived",
                    "transformation_rule": (
                        f"Reviewed survey-date builder derives final_SURVEY_DATE_CSES.{canonical_name} "
                        f"from explicit raw field(s) [{', '.join(sorted(set(source_names)))}] for wave {wave}. "
                        f"Canonical semantics: {definition}"
                    ),
                    "alignment_status": "tested",
                    "observed_row_count": None,
                    "observed_nonnull_count": None,
                    "observed_distinct_count": None,
                    "observation_status": None,
                    "profiled_at": None,
                }
            )
    return mappings


def build_desired_state(
    root: Path, spec_path: Path | None = None
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    spec_path = spec_path or default_variable_catalog_spec_path(root)
    spec = load_variable_catalog_spec(spec_path)
    evidence = {
        name: _read_verified_json(root, descriptor)
        for name, descriptor in sorted(spec["evidence"].items())
    }
    baseline = evidence["baseline_plan"]
    manifest = evidence["local_release_manifest"]
    postflight = evidence["migration_postflight"]
    validation = evidence["migration_validation"]
    if baseline.get("baseline_id") != "cses-baseline-metadata-v1" or not baseline.get("preflight_ready"):
        raise ValueError("The pinned baseline plan is not an accepted preflight")
    if not postflight.get("post_migration_valid") or not validation.get("validation_passed"):
        raise ValueError("The pinned functional schema evidence is not valid")

    manifest_paths = {item["path"]: item["sha256"] for item in manifest["artifacts"]}
    dictionaries: dict[str, list[dict[str, str]]] = {}
    fingerprint_checks: dict[str, bool] = {}
    for rule in spec["module_rules"]:
        for kind in ("builder", "dictionary"):
            path = root / rule[f"{kind}_path"]
            expected = rule[f"{kind}_sha256"]
            matched = path.is_file() and sha256_file(path) == expected
            fingerprint_checks[f"{kind}_{rule['module_code']}_matches"] = matched
            if not matched:
                raise ValueError(f"{kind.title()} fingerprint mismatch: {path.relative_to(root)}")
        dictionary_path = rule["dictionary_path"]
        if manifest_paths.get(dictionary_path) != rule["dictionary_sha256"]:
            raise ValueError(f"Dictionary is not pinned by the release manifest: {dictionary_path}")
        dictionaries[rule["module_code"]] = _load_dictionary(root / dictionary_path, rule["module_code"])
    contract_path = root / spec["survey_date_contract"]["path"]
    contract_matches = sha256_file(contract_path) == spec["survey_date_contract"]["sha256"]
    if not contract_matches:
        raise ValueError("Survey-date contract fingerprint mismatch")

    datasets = [normalize_json_value(record) for record in baseline["desired_state"]["datasets"]]
    datasets_by_key = {_dataset_key(record): record for record in datasets}
    if len(datasets) != 171 or len(datasets_by_key) != 171:
        raise ValueError("The reviewed baseline must contain exactly 171 unique datasets")
    source_variables: list[dict[str, Any]] = []
    header_observations: dict[tuple[str, str, str], dict[str, Any]] = {}
    for dataset in sorted(datasets, key=_dataset_key):
        rows, observation = _read_stata_catalog(root, dataset)
        source_variables.extend(rows)
        header_observations[_dataset_key(dataset)] = observation
    if len(source_variables) != len({_record_key(row, SOURCE_VARIABLE_KEY) for row in source_variables}):
        raise ValueError("The Stata catalog contains duplicate dataset-variable identities")

    canonical_definitions = _canonical_lookup(spec["module_rules"], dictionaries)
    grains = {
        record["table_name"]: record["analytical_grain"]
        for record in baseline["desired_state"]["storage_tables"]
        if record["table_name"].startswith("final_")
    }
    physical_tables = {
        item["contract"]["name"]: item["physical"]
        for item in postflight["objects"]
        if item["contract"]["family"] == "final"
    }
    expected_targets = {rule["target_table"] for rule in spec["module_rules"]}
    if set(physical_tables) != expected_targets or set(grains) != expected_targets:
        raise ValueError("Pinned physical final-table set differs from the seven module rules")
    canonical_variables: list[dict[str, Any]] = []
    for target in sorted(physical_tables):
        for column in physical_tables[target]["columns"]:
            key = (target, column["name"])
            if key not in canonical_definitions:
                raise ValueError(f"No reviewed canonical definition for {target}.{column['name']}")
            measure_type, definition = canonical_definitions[key]
            canonical_variables.append(
                {
                    "target_table": target,
                    "canonical_name": column["name"],
                    "database_type": column["data_type"],
                    "measure_type": measure_type,
                    "canonical_definition": definition,
                    "analytical_grain": grains[target],
                    "status": "approved",
                }
            )
    observed_canonical_keys = {_record_key(row, CANONICAL_VARIABLE_KEY) for row in canonical_variables}
    extra_definitions = sorted(set(canonical_definitions) - observed_canonical_keys)
    if len(canonical_variables) != 280 or extra_definitions:
        raise ValueError(
            f"Canonical contract mismatch: count={len(canonical_variables)} extra={extra_definitions}"
        )

    standard_mappings, unresolved = _build_standard_mappings(
        spec, datasets, source_variables, dictionaries, canonical_definitions
    )
    if unresolved:
        raise ValueError(f"Reviewed dictionary source fields did not resolve: {unresolved[:10]}")
    date_mappings = _build_survey_date_mappings(
        spec, datasets_by_key, source_variables, canonical_definitions
    )
    variable_mappings = _sorted_records(
        [*standard_mappings, *date_mappings], VARIABLE_MAPPING_KEY
    )
    if len(variable_mappings) != len({_record_key(row, VARIABLE_MAPPING_KEY) for row in variable_mappings}):
        raise ValueError("Variable mapping identities are not unique")

    release = {
        "mapping_version": spec["alignment_release"]["mapping_version"],
        "status": spec["alignment_release"]["status"],
        "description": spec["alignment_release"]["description"],
        "specification_sha256": sha256_file(spec_path),
    }
    evidence_hashes = {
        name: {"path": descriptor["path"], "sha256": descriptor["sha256"]}
        for name, descriptor in sorted(spec["evidence"].items())
    }
    record_counts = {
        "source_variables": len(source_variables),
        "canonical_variables": len(canonical_variables),
        "variable_mappings": len(variable_mappings),
        "instruments": 0,
        "questions": 0,
        "value_mappings": 0,
    }
    source_manifest_sha256 = canonical_sha256(
        {
            "evidence": evidence_hashes,
            "module_rules": spec["module_rules"],
            "source_variable_catalog": source_variables,
            "canonical_variables": canonical_variables,
            "variable_mappings": variable_mappings,
        }
    )
    load_run = {
        "variable_catalog_import_id": spec["catalog_release_id"],
        "survey_wave": None,
        "mapping_version": release["mapping_version"],
        "run_scope": spec["load_run"]["run_scope"],
        "source_manifest_sha256": source_manifest_sha256,
        "code_git_revision": _git_revision(root),
        "dvc_revision": spec["source_data_dvc_revision"],
        "status": spec["load_run"]["status"],
        "row_counts": record_counts,
        "validation_summary": {
            "variable_catalog_import_id": spec["catalog_release_id"],
            "source_alignment_release": spec["source_alignment_release"],
            "source_dataset_count": len(datasets),
            **record_counts,
            "questionnaire_policy": spec["questionnaire_policy"],
            "value_mapping_policy": spec["value_mapping_policy"],
        },
        "error_message": None,
    }
    desired = {
        "alignment_releases": [release],
        "source_variables": _sorted_records(source_variables, SOURCE_VARIABLE_KEY),
        "canonical_variables": _sorted_records(canonical_variables, CANONICAL_VARIABLE_KEY),
        "variable_mappings": variable_mappings,
        "load_runs": [load_run],
    }
    baseline_counts_match = all(
        (dataset["column_count"] is None or observation["column_count"] == dataset["column_count"])
        and (dataset["row_count"] is None or observation["row_count"] == dataset["row_count"])
        for key, observation in header_observations.items()
        for dataset in [datasets_by_key[key]]
    )
    local_checks = {
        **fingerprint_checks,
        "survey_date_contract_matches": contract_matches,
        "baseline_has_171_registered_datasets": len(datasets) == 171,
        "all_registered_dataset_headers_read": len(header_observations) == 171,
        "known_baseline_dimensions_match_stata_headers": baseline_counts_match,
        "source_variable_identities_are_unique": len(source_variables)
        == len({_record_key(row, SOURCE_VARIABLE_KEY) for row in source_variables}),
        "canonical_contract_matches_280_physical_columns": len(canonical_variables) == 280,
        "all_dictionary_source_fields_resolved": not unresolved,
        "all_mapping_sources_are_cataloged": all(
            set(mapping["source_variable_names"]).issubset(
                {
                    row["variable_name"]
                    for row in source_variables
                    if _dataset_key(row) == _dataset_key(mapping)
                }
            )
            for mapping in variable_mappings
        ),
        "no_instruments_or_questions_synthesized": True,
        "no_value_mappings_inferred": True,
    }
    diagnostics = {
        "spec": {
            "path": str(spec_path.relative_to(root)),
            "sha256": sha256_file(spec_path),
            "approval_phrase": spec["approval_phrase"],
            "approval_required": True,
        },
        "evidence": evidence_hashes,
        "record_counts": {name: len(desired[name]) for name in DESIRED_GROUPS},
        "scope_counts": record_counts,
        "mapping_counts_by_target": dict(
            sorted(Counter(row["target_table"] for row in variable_mappings).items())
        ),
        "source_variable_counts_by_wave": dict(
            sorted(
                Counter(
                    dataset["survey_wave"]
                    for record in source_variables
                    for dataset in [datasets_by_key[_dataset_key(record)]]
                ).items()
            )
        ),
        "local_checks": local_checks,
    }
    return desired, diagnostics


def reconcile_states(
    desired: dict[str, list[dict[str, Any]]], existing: dict[str, list[dict[str, Any]]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    operations: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for group in DESIRED_GROUPS:
        key_fields = RECORD_KEYS[group]
        existing_by_key: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for record in existing[group]:
            existing_by_key[_record_key(record, key_fields)].append(record)
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


def _fetch_existing_state(
    connection: psycopg.Connection[dict[str, Any]],
    desired: dict[str, list[dict[str, Any]]],
    catalog_release_id: str,
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
    source_variables = connection.execute(
        """
        SELECT a.relative_path AS archive_relative_path, d.member_path,
               d.nested_member_path, sv.question_id, sv.variable_name,
               sv.variable_position, sv.storage_type, sv.variable_label,
               sv.value_labels, sv.question_link_status, sv.question_link_role,
               sv.alignment_status
        FROM cses_alignment.cses_source_variable AS sv
        JOIN cses_meta.cses_dataset AS d USING (dataset_id)
        JOIN cses_meta.cses_source_archive AS a USING (source_archive_id)
        ORDER BY a.relative_path, d.member_path, d.nested_member_path,
                 sv.variable_name
        """
    ).fetchall()
    canonicals = connection.execute(
        """
        SELECT target_table, canonical_name, database_type, measure_type,
               canonical_definition, analytical_grain, status
        FROM cses_alignment.cses_canonical_variable
        ORDER BY target_table, canonical_name
        """
    ).fetchall()
    mappings = connection.execute(
        """
        SELECT a.relative_path AS archive_relative_path, d.member_path,
               d.nested_member_path, cv.target_table, cv.canonical_name,
               ar.mapping_version, vm.source_variable_names, vm.source_kind,
               vm.transformation_rule, vm.alignment_status,
               vm.observed_row_count, vm.observed_nonnull_count,
               vm.observed_distinct_count, vm.observation_status, vm.profiled_at
        FROM cses_alignment.cses_variable_mapping AS vm
        JOIN cses_meta.cses_dataset AS d USING (dataset_id)
        JOIN cses_meta.cses_source_archive AS a USING (source_archive_id)
        JOIN cses_alignment.cses_canonical_variable AS cv USING (canonical_variable_id)
        JOIN cses_meta.cses_alignment_release AS ar USING (alignment_release_id)
        ORDER BY a.relative_path, d.member_path, d.nested_member_path,
                 cv.target_table, cv.canonical_name, ar.mapping_version
        """
    ).fetchall()
    load_runs = connection.execute(
        """
        SELECT validation_summary->>'variable_catalog_import_id' AS variable_catalog_import_id,
               s.survey_wave, ar.mapping_version, lr.run_scope,
               lr.source_manifest_sha256, lr.code_git_revision, lr.dvc_revision,
               lr.status, lr.row_counts, lr.validation_summary, lr.error_message
        FROM cses_meta.cses_load_run AS lr
        LEFT JOIN cses_meta.cses_survey AS s USING (survey_id)
        LEFT JOIN cses_meta.cses_alignment_release AS ar USING (alignment_release_id)
        WHERE validation_summary->>'variable_catalog_import_id' = %s
        ORDER BY lr.load_run_id
        """,
        (catalog_release_id,),
    ).fetchall()
    return {
        "alignment_releases": [normalize_json_value(dict(row)) for row in releases],
        "source_variables": [normalize_json_value(dict(row)) for row in source_variables],
        "canonical_variables": [normalize_json_value(dict(row)) for row in canonicals],
        "variable_mappings": [normalize_json_value(dict(row)) for row in mappings],
        "load_runs": [normalize_json_value(dict(row)) for row in load_runs],
    }


def inspect_database(
    connection: psycopg.Connection[dict[str, Any]],
    desired: dict[str, list[dict[str, Any]]],
    spec: dict[str, Any],
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
        WHERE table_schema = 'cses_alignment' AND table_name = ANY(%s)
        ORDER BY table_name, ordinal_position
        """,
        (sorted(ALIGNMENT_TABLE_COLUMNS),),
    ).fetchall()
    observed_columns: dict[str, list[str]] = {name: [] for name in ALIGNMENT_TABLE_COLUMNS}
    for row in columns:
        observed_columns[row["table_name"]].append(row["column_name"])

    registered_datasets = connection.execute(
        """
        SELECT a.relative_path AS archive_relative_path, d.member_path,
               d.nested_member_path
        FROM cses_meta.cses_dataset AS d
        JOIN cses_meta.cses_source_archive AS a USING (source_archive_id)
        ORDER BY a.relative_path, d.member_path, d.nested_member_path
        """
    ).fetchall()
    registered_dataset_keys = {_dataset_key(dict(row)) for row in registered_datasets}
    desired_dataset_keys = {_dataset_key(row) for row in desired["source_variables"]}

    expected_physical = {
        (record["target_table"], record["canonical_name"]): record["database_type"]
        for record in desired["canonical_variables"]
    }
    physical_rows = connection.execute(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'cses_data' AND table_name = ANY(%s)
        ORDER BY table_name, ordinal_position
        """,
        (sorted({record["target_table"] for record in desired["canonical_variables"]}),),
    ).fetchall()
    observed_physical = {
        (row["table_name"], row["column_name"]): row["data_type"] for row in physical_rows
    }
    release_rows = connection.execute(
        """
        SELECT mapping_version, status
        FROM cses_meta.cses_alignment_release
        WHERE mapping_version = ANY(%s)
        """,
        ([spec["source_alignment_release"], spec["alignment_release"]["mapping_version"]],),
    ).fetchall()
    releases = {row["mapping_version"]: row["status"] for row in release_rows}
    protected_counts = {
        table: connection.execute(
            f"SELECT count(*) AS count FROM cses_alignment.{table}"
        ).fetchone()["count"]
        for table in ("cses_instrument", "cses_question", "cses_value_mapping")
    }

    existing = _fetch_existing_state(connection, desired, spec["catalog_release_id"])
    operations, conflicts = reconcile_states(desired, existing)
    unexpected_existing: dict[str, list[dict[str, Any]]] = {}
    for group in ("source_variables", "canonical_variables", "variable_mappings"):
        fields = RECORD_KEYS[group]
        desired_keys = {_record_key(record, fields) for record in desired[group]}
        unexpected_existing[group] = [
            record for record in existing[group] if _record_key(record, fields) not in desired_keys
        ]
    action_counts = Counter(item["action"] for item in operations)
    checks = {
        "database_name_matches": database["database"] == spec["database"],
        "alignment_table_columns_match_v1_ddl": all(
            tuple(observed_columns[name]) == expected
            for name, expected in ALIGNMENT_TABLE_COLUMNS.items()
        ),
        "registered_dataset_set_matches_catalog_scope": registered_dataset_keys == desired_dataset_keys,
        "physical_final_columns_match_canonical_contract": observed_physical == expected_physical,
        "source_storage_release_is_approved": releases.get(spec["source_alignment_release"])
        == "approved",
        "no_instruments_or_questions_present": protected_counts["cses_instrument"] == 0
        and protected_counts["cses_question"] == 0,
        "no_canonical_value_mappings_present": protected_counts["cses_value_mapping"] == 0,
        "no_unreviewed_variable_state": not any(unexpected_existing.values()),
        "no_existing_metadata_conflicts": not conflicts,
    }
    checks["transaction_is_read_only" if require_read_only else "transaction_is_read_write"] = (
        database["transaction_read_only"] == ("on" if require_read_only else "off")
    )
    return {
        "database": database,
        "alignment_columns": observed_columns,
        "registered_dataset_count": len(registered_dataset_keys),
        "physical_canonical_column_count": len(observed_physical),
        "protected_zero_scope_counts": protected_counts,
        "existing_record_counts": {name: len(existing[name]) for name in DESIRED_GROUPS},
        "unexpected_existing": unexpected_existing,
        "operations": operations,
        "action_counts": {
            name: action_counts.get(name, 0) for name in ("insert", "noop", "conflict")
        },
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
    return {_dataset_key(dict(row)): int(row["dataset_id"]) for row in rows}


def apply_variable_catalog(
    connection: psycopg.Connection[dict[str, Any]],
    desired: dict[str, list[dict[str, Any]]],
    spec: dict[str, Any],
) -> dict[str, Any]:
    before = inspect_database(connection, desired, spec, require_read_only=False)
    failed = [name for name, passed in before["checks"].items() if not passed]
    if failed:
        raise RuntimeError(f"Variable catalog write preflight failed: {failed}")
    connection.execute("SELECT pg_advisory_xact_lock(hashtext('cses-variable-catalog-v1'))")
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
            release["mapping_version"], release["status"], release["description"],
            release["specification_sha256"],
        ),
    )
    inserted["alignment_releases"] += cursor.rowcount
    release_id = int(
        connection.execute(
            "SELECT alignment_release_id FROM cses_meta.cses_alignment_release WHERE mapping_version = %s",
            (release["mapping_version"],),
        ).fetchone()["alignment_release_id"]
    )
    dataset_ids = _resolve_dataset_ids(connection)
    for record in desired["source_variables"]:
        cursor = connection.execute(
            """
            INSERT INTO cses_alignment.cses_source_variable
                (dataset_id, question_id, variable_name, variable_position,
                 storage_type, variable_label, value_labels, question_link_status,
                 question_link_role, alignment_status)
            VALUES (%s, NULL, %s, %s, %s, %s, %s, NULL, NULL, %s)
            ON CONFLICT (dataset_id, variable_name) DO NOTHING
            """,
            (
                dataset_ids[_dataset_key(record)], record["variable_name"],
                record["variable_position"], record["storage_type"], record["variable_label"],
                Jsonb(record["value_labels"]) if record["value_labels"] is not None else None,
                record["alignment_status"],
            ),
        )
        inserted["source_variables"] += cursor.rowcount

    for record in desired["canonical_variables"]:
        cursor = connection.execute(
            """
            INSERT INTO cses_alignment.cses_canonical_variable
                (target_table, canonical_name, database_type, measure_type,
                 canonical_definition, analytical_grain, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (target_table, canonical_name) DO NOTHING
            """,
            (
                record["target_table"], record["canonical_name"], record["database_type"],
                record["measure_type"], record["canonical_definition"],
                record["analytical_grain"], record["status"],
            ),
        )
        inserted["canonical_variables"] += cursor.rowcount
    canonical_ids = {
        (row["target_table"], row["canonical_name"]): int(row["canonical_variable_id"])
        for row in connection.execute(
            "SELECT canonical_variable_id, target_table, canonical_name FROM cses_alignment.cses_canonical_variable"
        ).fetchall()
    }
    for record in desired["variable_mappings"]:
        cursor = connection.execute(
            """
            INSERT INTO cses_alignment.cses_variable_mapping
                (dataset_id, canonical_variable_id, alignment_release_id,
                 source_variable_names, source_kind, transformation_rule,
                 alignment_status, observed_row_count, observed_nonnull_count,
                 observed_distinct_count, observation_status, profiled_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NULL, NULL, NULL, NULL)
            ON CONFLICT (dataset_id, canonical_variable_id, alignment_release_id) DO NOTHING
            """,
            (
                dataset_ids[_dataset_key(record)],
                canonical_ids[(record["target_table"], record["canonical_name"])],
                release_id, record["source_variable_names"], record["source_kind"],
                record["transformation_rule"], record["alignment_status"],
            ),
        )
        inserted["variable_mappings"] += cursor.rowcount

    load_run = desired["load_runs"][0]
    existing_load = connection.execute(
        """
        SELECT load_run_id FROM cses_meta.cses_load_run
        WHERE validation_summary->>'variable_catalog_import_id' = %s
        """,
        (spec["catalog_release_id"],),
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
                release_id, load_run["run_scope"], load_run["source_manifest_sha256"],
                load_run["code_git_revision"], load_run["dvc_revision"], load_run["status"],
                Jsonb(load_run["row_counts"]), Jsonb(load_run["validation_summary"]),
            ),
        )
        inserted["load_runs"] += cursor.rowcount

    after = inspect_database(connection, desired, spec, require_read_only=False)
    if after["conflicts"] or after["action_counts"]["insert"] or not all(after["checks"].values()):
        raise RuntimeError("Variable catalog did not reconcile to the reviewed desired state")
    return {
        "inserted_record_counts": {name: inserted.get(name, 0) for name in DESIRED_GROUPS},
        "post_write_action_counts": after["action_counts"],
        "database_mutated": bool(sum(inserted.values())),
    }


__all__ = [
    "ALIGNMENT_TABLE_COLUMNS",
    "apply_variable_catalog",
    "build_desired_state",
    "connect_database",
    "default_variable_catalog_spec_path",
    "inspect_database",
    "load_variable_catalog_spec",
    "reconcile_states",
]
