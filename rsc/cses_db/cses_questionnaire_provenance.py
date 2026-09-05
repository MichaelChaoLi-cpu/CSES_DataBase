"""Build, inspect, and apply reviewed CSES questionnaire provenance."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import psycopg
from cses_baseline_metadata import (
    canonical_json,
    canonical_sha256,
    connect_database,
    normalize_json_value,
    sha256_file,
)
from cses_variable_catalog import ALIGNMENT_TABLE_COLUMNS
from inventory_cses_archives import DataSource
from psycopg.types.json import Jsonb

DATASET_KEY = ("archive_relative_path", "member_path", "nested_member_path")
INSTRUMENT_KEY = ("survey_wave", "instrument_type", "source_file")
QUESTION_KEY = (*INSTRUMENT_KEY, "question_code")
SOURCE_LINK_KEY = (*DATASET_KEY, "variable_name")
DESIRED_GROUPS = (
    "alignment_releases",
    "instruments",
    "questions",
    "source_variable_links",
    "load_runs",
)
RECORD_KEYS = {
    "alignment_releases": ("mapping_version",),
    "instruments": INSTRUMENT_KEY,
    "questions": QUESTION_KEY,
    "source_variable_links": SOURCE_LINK_KEY,
    "load_runs": ("questionnaire_provenance_import_id",),
}


def default_questionnaire_provenance_spec_path(root: Path) -> Path:
    return root / "rsc" / "specs" / "cses_questionnaire_provenance_v1.json"


def _record_key(record: dict[str, Any], fields: Iterable[str]) -> tuple[Any, ...]:
    return tuple(normalize_json_value(record.get(field)) for field in fields)


def _sorted_records(records: Iterable[dict[str, Any]], fields: Iterable[str]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda record: canonical_json(_record_key(record, fields)))


def _git_revision(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _source_file(instrument: dict[str, Any]) -> str:
    return f"{instrument['archive_relative_path']}::{instrument['member_path']}"


def load_questionnaire_provenance_spec(path: Path) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec.get("schema_version") != 1:
        raise ValueError("Unsupported questionnaire provenance schema version")
    if spec.get("database") != "mda":
        raise ValueError("The questionnaire provenance release is scoped to mda")
    release = spec.get("alignment_release", {})
    if release.get("status") != "approved" or not release.get("requires_explicit_approval"):
        raise ValueError("The questionnaire provenance release must be approved and gated")
    if spec.get("approval_phrase") != "ACCEPT-CSES-QUESTIONNAIRE-PROVENANCE-V1":
        raise ValueError("The exact questionnaire provenance approval phrase changed")
    if not re.fullmatch(r"md5:[0-9a-f]{32}\.dir", str(spec.get("source_data_dvc_revision", ""))):
        raise ValueError("A fixed source data.dvc directory revision is required")

    instruments = spec.get("instruments", [])
    identities = [(item["survey_wave"], item["instrument_type"], _source_file(item)) for item in instruments]
    if len(instruments) != 14 or len(identities) != len(set(identities)):
        raise ValueError("Questionnaire provenance v1 must define 14 unique instruments")
    allowed_statuses = {"discovered", "provisional", "documented", "verified"}
    if any(item["documentation_status"] not in allowed_statuses for item in instruments):
        raise ValueError("Invalid instrument documentation status")
    if len(spec.get("coverage_gaps", [])) != 7:
        raise ValueError("Questionnaire provenance v1 must retain seven explicit coverage gaps")
    return spec


def _read_verified_json(root: Path, descriptor: dict[str, str]) -> dict[str, Any]:
    path = root / descriptor["path"]
    if not path.is_file() or sha256_file(path) != descriptor["sha256"]:
        raise ValueError(f"Evidence fingerprint mismatch: {descriptor['path']}")
    return json.loads(path.read_text(encoding="utf-8"))


def _member_sha256(root: Path, instrument: dict[str, Any]) -> str:
    source = DataSource(
        root / instrument["archive_relative_path"],
        (instrument["member_path"],),
    )
    return hashlib.sha256(source.read_bytes()).hexdigest()


def _question_prefix_matches(variable_name: str, question_code: str) -> bool:
    variable = variable_name.lower()
    code = question_code.lower()
    if not variable.startswith(code):
        return False
    remainder = variable[len(code) :]
    return not remainder or not (code[-1].isdigit() and remainder[0].isdigit())


def match_question_code(variable_name: str, question_codes: Iterable[str]) -> str | None:
    matches = [code for code in question_codes if _question_prefix_matches(variable_name, code)]
    if not matches:
        return None
    matches.sort(key=lambda value: (len(value), value.lower()), reverse=True)
    if len(matches) > 1 and len(matches[0]) == len(matches[1]):
        raise ValueError(f"Ambiguous question-code match for {variable_name}: {matches[:2]}")
    return matches[0]


def build_desired_state(
    root: Path, spec_path: Path | None = None
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    spec_path = spec_path or default_questionnaire_provenance_spec_path(root)
    spec = load_questionnaire_provenance_spec(spec_path)
    evidence = {name: _read_verified_json(root, descriptor) for name, descriptor in sorted(spec["evidence"].items())}
    baseline = evidence["baseline_plan"]
    variable_plan = evidence["variable_catalog_plan"]
    question_catalog = evidence["question_catalog"]
    if baseline.get("baseline_id") != "cses-baseline-metadata-v1":
        raise ValueError("Unexpected baseline-plan evidence")
    if variable_plan.get("catalog_release_id") != "cses-variable-catalog-v1":
        raise ValueError("Unexpected variable-catalog evidence")
    if question_catalog.get("schema_version") != 1:
        raise ValueError("Unexpected question-catalog evidence")

    dataset_wave = {
        tuple(record.get(field) or "" for field in DATASET_KEY): record["survey_wave"]
        for record in baseline["desired_state"]["datasets"]
    }
    source_variables = variable_plan["desired_state"]["source_variables"]
    if len(dataset_wave) != 171 or len(source_variables) != 4092:
        raise ValueError("Questionnaire release requires the reviewed 171-dataset/4,092-variable catalog")
    if any(tuple(record.get(field) or "" for field in DATASET_KEY) not in dataset_wave for record in source_variables):
        raise ValueError("A source variable references an unregistered dataset")

    fingerprint_checks: dict[str, bool] = {}
    instruments: list[dict[str, Any]] = []
    instruments_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in spec["instruments"]:
        observed_sha256 = _member_sha256(root, item)
        label = f"{item['survey_wave']}_{item['instrument_type']}"
        fingerprint_checks[f"instrument_{label}_{len(instruments) + 1}_matches"] = (
            observed_sha256 == item["source_sha256"]
        )
        if observed_sha256 != item["source_sha256"]:
            raise ValueError(f"Instrument fingerprint mismatch: {_source_file(item)}")
        record = {
            "survey_wave": item["survey_wave"],
            "instrument_type": item["instrument_type"],
            "source_file": _source_file(item),
            "source_url": None,
            "source_sha256": item["source_sha256"],
            "document_title": item["document_title"],
            "publication_date": None,
            "language_code": item["language_code"],
            "documentation_status": item["documentation_status"],
        }
        instruments.append(record)
        key = (item["survey_wave"], item["instrument_type"])
        if item["question_catalog_included"]:
            if key in instruments_by_key:
                raise ValueError(f"Multiple catalog-bearing instruments for {key}")
            instruments_by_key[key] = record

    questions: list[dict[str, Any]] = []
    question_codes_by_wave: dict[str, list[str]] = defaultdict(list)
    question_lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for catalog in question_catalog["catalogs"]:
        key = (catalog["wave"], catalog["instrument_type"])
        instrument = instruments_by_key.get(key)
        if instrument is None:
            raise ValueError(f"Question catalog has no selected instrument: {key}")
        provisional = instrument["documentation_status"] == "provisional"
        for sequence, item in enumerate(catalog["questions"], start=1):
            code = item["question_code"].lower()
            record = {
                **{field: instrument[field] for field in INSTRUMENT_KEY},
                "question_code": code,
                "question_text": item["question_text"],
                "section_name": item["section_name"],
                "sequence_number": sequence,
                "source_page": None,
                "response_options": None,
                "skip_instruction": None,
                "question_grain": (
                    "village-wave" if catalog["instrument_type"] == "village_questionnaire" else "household-wave"
                ),
                "repeat_context": {
                    "source_sheet": item["source_sheet"],
                    "question_code_cell": item["question_code_cell"],
                    "question_text_cell": item["question_text_cell"],
                    "transcription": "whitespace-normalized spreadsheet cell text",
                },
                "is_exact_question_text": False,
                "documentation_status": "provisional" if provisional else "documented",
            }
            lookup_key = (catalog["wave"], code)
            if lookup_key in question_lookup:
                raise ValueError(f"Duplicate question code within wave: {lookup_key}")
            questions.append(record)
            question_lookup[lookup_key] = record
            question_codes_by_wave[catalog["wave"]].append(code)

    links: list[dict[str, Any]] = []
    for source_variable in source_variables:
        dataset_key = tuple(source_variable.get(field) or "" for field in DATASET_KEY)
        wave = dataset_wave[dataset_key]
        code = match_question_code(source_variable["variable_name"], question_codes_by_wave.get(wave, ()))
        if code is None:
            continue
        question = question_lookup[(wave, code)]
        links.append(
            {
                **{field: source_variable.get(field) or "" for field in DATASET_KEY},
                "variable_name": source_variable["variable_name"],
                "survey_wave": wave,
                "instrument_type": question["instrument_type"],
                "source_file": question["source_file"],
                "question_code": code,
                "question_link_status": (
                    spec["question_policy"]["provisional_link_status"]
                    if question["documentation_status"] == "provisional"
                    else spec["question_policy"]["documented_link_status"]
                ),
                "question_link_role": spec["question_policy"]["question_link_role"],
            }
        )

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
    scope_counts = {
        "instruments": len(instruments),
        "questions": len(questions),
        "source_variable_links": len(links),
        "exact_question_texts": sum(item["is_exact_question_text"] for item in questions),
        "coverage_gaps": len(spec["coverage_gaps"]),
    }
    source_manifest_sha256 = canonical_sha256(
        {
            "evidence": evidence_hashes,
            "instruments": instruments,
            "questions": questions,
            "source_variable_links": links,
            "coverage_gaps": spec["coverage_gaps"],
            "question_policy": spec["question_policy"],
        }
    )
    load_run = {
        "questionnaire_provenance_import_id": spec["catalog_release_id"],
        "survey_wave": None,
        "mapping_version": release["mapping_version"],
        "run_scope": spec["load_run"]["run_scope"],
        "source_manifest_sha256": source_manifest_sha256,
        "code_git_revision": _git_revision(root),
        "dvc_revision": spec["source_data_dvc_revision"],
        "status": spec["load_run"]["status"],
        "row_counts": scope_counts,
        "validation_summary": {
            "questionnaire_provenance_import_id": spec["catalog_release_id"],
            "source_alignment_release": spec["source_alignment_release"],
            "question_policy": spec["question_policy"],
            **scope_counts,
        },
        "error_message": None,
    }
    desired = {
        "alignment_releases": [release],
        "instruments": _sorted_records(instruments, INSTRUMENT_KEY),
        "questions": _sorted_records(questions, QUESTION_KEY),
        "source_variable_links": _sorted_records(links, SOURCE_LINK_KEY),
        "load_runs": [load_run],
    }
    linked_questions = {(link["survey_wave"], link["instrument_type"], link["question_code"]) for link in links}
    catalog_keys = {(catalog["wave"], catalog["instrument_type"]) for catalog in question_catalog["catalogs"]}
    local_checks = {
        **fingerprint_checks,
        "evidence_fingerprints_match": True,
        "instrument_identities_are_unique": len(instruments)
        == len({_record_key(item, INSTRUMENT_KEY) for item in instruments}),
        "question_identities_are_unique": len(questions)
        == len({_record_key(item, QUESTION_KEY) for item in questions}),
        "source_link_identities_are_unique": len(links) == len({_record_key(item, SOURCE_LINK_KEY) for item in links}),
        "reviewed_question_count_is_164": len(questions) == 164,
        "all_catalogs_have_selected_instruments": catalog_keys == set(instruments_by_key),
        "every_catalog_has_at_least_one_source_link": all(
            any((wave, instrument_type) == key[:2] for key in linked_questions)
            for wave, instrument_type in catalog_keys
        ),
        "2014_links_remain_proposed": all(
            link["question_link_status"] == "proposed" for link in links if link["survey_wave"] == "2014"
        ),
        "non_2014_links_are_reviewed": all(
            link["question_link_status"] == "reviewed" for link in links if link["survey_wave"] != "2014"
        ),
        "no_question_text_claimed_exact": not any(item["is_exact_question_text"] for item in questions),
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
        "scope_counts": scope_counts,
        "instrument_counts_by_wave": dict(sorted(Counter(item["survey_wave"] for item in instruments).items())),
        "question_counts_by_wave": dict(sorted(Counter(item["survey_wave"] for item in questions).items())),
        "source_link_counts_by_wave": dict(sorted(Counter(item["survey_wave"] for item in links).items())),
        "coverage_gaps": spec["coverage_gaps"],
        "local_checks": local_checks,
    }
    return desired, diagnostics


def reconcile_states(
    desired: dict[str, list[dict[str, Any]]],
    existing: dict[str, list[dict[str, Any]]],
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
            if group == "source_variable_links":
                blank = bool(candidates) and all(
                    candidates[0].get(field) is None
                    for field in (
                        "survey_wave",
                        "instrument_type",
                        "source_file",
                        "question_code",
                        "question_link_status",
                        "question_link_role",
                    )
                )
                if len(candidates) == 1 and blank:
                    action = "update"
                elif len(candidates) == 1 and normalize_json_value(candidates[0]) == normalize_json_value(record):
                    action = "noop"
                else:
                    action = "conflict"
            elif not candidates:
                action = "insert"
            elif len(candidates) == 1 and normalize_json_value(candidates[0]) == normalize_json_value(record):
                action = "noop"
            else:
                action = "conflict"
            if action == "conflict":
                conflicts.append(
                    {
                        "group": group,
                        "key": dict(zip(key_fields, key, strict=True)),
                        "desired": record,
                        "existing": candidates,
                    }
                )
            operations.append({"group": group, "key": dict(zip(key_fields, key, strict=True)), "action": action})
    operations.sort(key=lambda item: (item["group"], canonical_json(item["key"])))
    return operations, conflicts


def _fetch_existing_state(
    connection: psycopg.Connection[dict[str, Any]],
    desired: dict[str, list[dict[str, Any]]],
    catalog_release_id: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
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
    instruments = connection.execute(
        """
        SELECT s.survey_wave, i.instrument_type, i.source_file, i.source_url,
               i.source_sha256, i.document_title, i.publication_date,
               i.language_code, i.documentation_status
        FROM cses_alignment.cses_instrument AS i
        JOIN cses_meta.cses_survey AS s USING (survey_id)
        ORDER BY s.survey_wave, i.instrument_type, i.source_file
        """
    ).fetchall()
    questions = connection.execute(
        """
        SELECT s.survey_wave, i.instrument_type, i.source_file, q.question_code,
               q.question_text, q.section_name, q.sequence_number, q.source_page,
               q.response_options, q.skip_instruction, q.question_grain,
               q.repeat_context, q.is_exact_question_text, q.documentation_status
        FROM cses_alignment.cses_question AS q
        JOIN cses_alignment.cses_instrument AS i USING (instrument_id)
        JOIN cses_meta.cses_survey AS s USING (survey_id)
        ORDER BY s.survey_wave, i.instrument_type, i.source_file, q.question_code
        """
    ).fetchall()
    raw_links = connection.execute(
        """
        SELECT a.relative_path AS archive_relative_path, d.member_path,
               d.nested_member_path, sv.variable_name,
               qs.survey_wave, i.instrument_type, i.source_file, q.question_code,
               sv.question_link_status, sv.question_link_role
        FROM cses_alignment.cses_source_variable AS sv
        JOIN cses_meta.cses_dataset AS d USING (dataset_id)
        JOIN cses_meta.cses_source_archive AS a USING (source_archive_id)
        LEFT JOIN cses_alignment.cses_question AS q USING (question_id)
        LEFT JOIN cses_alignment.cses_instrument AS i USING (instrument_id)
        LEFT JOIN cses_meta.cses_survey AS qs ON qs.survey_id = i.survey_id
        ORDER BY a.relative_path, d.member_path, d.nested_member_path, sv.variable_name
        """
    ).fetchall()
    desired_link_keys = {_record_key(record, SOURCE_LINK_KEY) for record in desired["source_variable_links"]}
    links = [
        row
        for row in raw_links
        if _record_key(row, SOURCE_LINK_KEY) in desired_link_keys or row["question_code"] is not None
    ]
    load_runs = connection.execute(
        """
        SELECT validation_summary->>'questionnaire_provenance_import_id'
                   AS questionnaire_provenance_import_id,
               s.survey_wave, ar.mapping_version, lr.run_scope,
               lr.source_manifest_sha256, lr.code_git_revision, lr.dvc_revision,
               lr.status, lr.row_counts, lr.validation_summary, lr.error_message
        FROM cses_meta.cses_load_run AS lr
        LEFT JOIN cses_meta.cses_survey AS s USING (survey_id)
        LEFT JOIN cses_meta.cses_alignment_release AS ar USING (alignment_release_id)
        WHERE validation_summary->>'questionnaire_provenance_import_id' = %s
        ORDER BY lr.load_run_id
        """,
        (catalog_release_id,),
    ).fetchall()
    existing = {
        "alignment_releases": [normalize_json_value(dict(row)) for row in releases],
        "instruments": [normalize_json_value(dict(row)) for row in instruments],
        "questions": [normalize_json_value(dict(row)) for row in questions],
        "source_variable_links": [normalize_json_value(dict(row)) for row in links],
        "load_runs": [normalize_json_value(dict(row)) for row in load_runs],
    }
    unexpected: dict[str, list[dict[str, Any]]] = {}
    for group in ("instruments", "questions", "source_variable_links"):
        fields = RECORD_KEYS[group]
        desired_keys = {_record_key(record, fields) for record in desired[group]}
        unexpected[group] = [
            record
            for record in existing[group]
            if _record_key(record, fields) not in desired_keys
            and (group != "source_variable_links" or record.get("question_code") is not None)
        ]
    return existing, unexpected


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
    source_release = connection.execute(
        """
        SELECT status FROM cses_meta.cses_alignment_release WHERE mapping_version = %s
        """,
        (spec["source_alignment_release"],),
    ).fetchone()
    survey_waves = {
        row["survey_wave"]
        for row in connection.execute("SELECT survey_wave FROM cses_meta.cses_survey ORDER BY survey_wave").fetchall()
    }
    scope_counts = {
        "source_variables": connection.execute(
            "SELECT count(*) AS count FROM cses_alignment.cses_source_variable"
        ).fetchone()["count"],
        "canonical_variables": connection.execute(
            "SELECT count(*) AS count FROM cses_alignment.cses_canonical_variable"
        ).fetchone()["count"],
        "variable_mappings": connection.execute(
            "SELECT count(*) AS count FROM cses_alignment.cses_variable_mapping"
        ).fetchone()["count"],
        "value_mappings": connection.execute(
            "SELECT count(*) AS count FROM cses_alignment.cses_value_mapping"
        ).fetchone()["count"],
    }
    existing, unexpected = _fetch_existing_state(connection, desired, spec["catalog_release_id"])
    operations, conflicts = reconcile_states(desired, existing)
    action_counts = Counter(operation["action"] for operation in operations)
    desired_waves = {item["survey_wave"] for item in desired["instruments"]}
    checks = {
        "database_name_matches": database["database"] == spec["database"],
        "alignment_table_columns_match_v1_ddl": all(
            tuple(observed_columns[name]) == expected for name, expected in ALIGNMENT_TABLE_COLUMNS.items()
        ),
        "source_variable_catalog_is_present": scope_counts["source_variables"] == 4092,
        "canonical_variable_catalog_is_unchanged": scope_counts["canonical_variables"] == 280,
        "variable_mapping_catalog_is_unchanged": scope_counts["variable_mappings"] == 1714,
        "canonical_value_mappings_remain_empty": scope_counts["value_mappings"] == 0,
        "source_alignment_release_is_approved": source_release is not None and source_release["status"] == "approved",
        "all_instrument_waves_are_registered": desired_waves.issubset(survey_waves),
        "no_unexpected_questionnaire_provenance": not any(unexpected.values()),
        "no_existing_metadata_conflicts": not conflicts,
    }
    checks["transaction_is_read_only" if require_read_only else "transaction_is_read_write"] = database[
        "transaction_read_only"
    ] == ("on" if require_read_only else "off")
    return {
        "database": database,
        "alignment_columns": observed_columns,
        "scope_counts": scope_counts,
        "existing_record_counts": {name: len(existing[name]) for name in DESIRED_GROUPS},
        "unexpected_existing": unexpected,
        "operations": operations,
        "action_counts": {name: action_counts.get(name, 0) for name in ("insert", "update", "noop", "conflict")},
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
    return {tuple(row.get(field) or "" for field in DATASET_KEY): int(row["dataset_id"]) for row in rows}


def apply_questionnaire_provenance(
    connection: psycopg.Connection[dict[str, Any]],
    desired: dict[str, list[dict[str, Any]]],
    spec: dict[str, Any],
) -> dict[str, Any]:
    before = inspect_database(connection, desired, spec, require_read_only=False)
    failed = [name for name, passed in before["checks"].items() if not passed]
    if failed:
        raise RuntimeError(f"Questionnaire provenance write preflight failed: {failed}")
    connection.execute("SELECT pg_advisory_xact_lock(hashtext('cses-questionnaire-provenance-v1'))")
    inserted: Counter[str] = Counter()
    updated: Counter[str] = Counter()

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
    release_id = int(
        connection.execute(
            "SELECT alignment_release_id FROM cses_meta.cses_alignment_release WHERE mapping_version = %s",
            (release["mapping_version"],),
        ).fetchone()["alignment_release_id"]
    )
    survey_ids = {
        row["survey_wave"]: int(row["survey_id"])
        for row in connection.execute("SELECT survey_id, survey_wave FROM cses_meta.cses_survey").fetchall()
    }
    for record in desired["instruments"]:
        cursor = connection.execute(
            """
            INSERT INTO cses_alignment.cses_instrument
                (survey_id, instrument_type, source_file, source_url, source_sha256,
                 document_title, publication_date, language_code, documentation_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (survey_id, instrument_type, source_file) DO NOTHING
            """,
            (
                survey_ids[record["survey_wave"]],
                record["instrument_type"],
                record["source_file"],
                record["source_url"],
                record["source_sha256"],
                record["document_title"],
                record["publication_date"],
                record["language_code"],
                record["documentation_status"],
            ),
        )
        inserted["instruments"] += cursor.rowcount
    instrument_ids = {
        (row["survey_wave"], row["instrument_type"], row["source_file"]): int(row["instrument_id"])
        for row in connection.execute(
            """
            SELECT i.instrument_id, s.survey_wave, i.instrument_type, i.source_file
            FROM cses_alignment.cses_instrument AS i
            JOIN cses_meta.cses_survey AS s USING (survey_id)
            """
        ).fetchall()
    }
    for record in desired["questions"]:
        cursor = connection.execute(
            """
            INSERT INTO cses_alignment.cses_question
                (instrument_id, question_code, question_text, section_name,
                 sequence_number, source_page, response_options, skip_instruction,
                 question_grain, repeat_context, is_exact_question_text,
                 documentation_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (instrument_id, question_code) DO NOTHING
            """,
            (
                instrument_ids[_record_key(record, INSTRUMENT_KEY)],
                record["question_code"],
                record["question_text"],
                record["section_name"],
                record["sequence_number"],
                record["source_page"],
                Jsonb(record["response_options"]) if record["response_options"] is not None else None,
                record["skip_instruction"],
                record["question_grain"],
                Jsonb(record["repeat_context"]),
                record["is_exact_question_text"],
                record["documentation_status"],
            ),
        )
        inserted["questions"] += cursor.rowcount
    question_ids = {
        (row["survey_wave"], row["instrument_type"], row["source_file"], row["question_code"]): int(row["question_id"])
        for row in connection.execute(
            """
            SELECT q.question_id, s.survey_wave, i.instrument_type, i.source_file,
                   q.question_code
            FROM cses_alignment.cses_question AS q
            JOIN cses_alignment.cses_instrument AS i USING (instrument_id)
            JOIN cses_meta.cses_survey AS s USING (survey_id)
            """
        ).fetchall()
    }
    dataset_ids = _resolve_dataset_ids(connection)
    for record in desired["source_variable_links"]:
        question_key = (
            record["survey_wave"],
            record["instrument_type"],
            record["source_file"],
            record["question_code"],
        )
        cursor = connection.execute(
            """
            UPDATE cses_alignment.cses_source_variable
            SET question_id = %s, question_link_status = %s, question_link_role = %s
            WHERE dataset_id = %s AND variable_name = %s
              AND question_id IS NULL AND question_link_status IS NULL
              AND question_link_role IS NULL
            """,
            (
                question_ids[question_key],
                record["question_link_status"],
                record["question_link_role"],
                dataset_ids[_record_key(record, DATASET_KEY)],
                record["variable_name"],
            ),
        )
        updated["source_variable_links"] += cursor.rowcount

    load_run = desired["load_runs"][0]
    existing_load = connection.execute(
        """
        SELECT load_run_id FROM cses_meta.cses_load_run
        WHERE validation_summary->>'questionnaire_provenance_import_id' = %s
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
    after = inspect_database(connection, desired, spec, require_read_only=False)
    if (
        after["conflicts"]
        or any(after["action_counts"][name] for name in ("insert", "update", "conflict"))
        or not all(after["checks"].values())
    ):
        raise RuntimeError("Questionnaire provenance did not reconcile to the reviewed desired state")
    return {
        "inserted_record_counts": {
            name: inserted.get(name, 0) for name in ("alignment_releases", "instruments", "questions", "load_runs")
        },
        "updated_record_counts": {"source_variable_links": updated["source_variable_links"]},
        "post_write_action_counts": after["action_counts"],
        "database_mutated": bool(sum(inserted.values()) + sum(updated.values())),
    }


__all__ = [
    "apply_questionnaire_provenance",
    "build_desired_state",
    "connect_database",
    "default_questionnaire_provenance_spec_path",
    "inspect_database",
    "load_questionnaire_provenance_spec",
    "match_question_code",
    "reconcile_states",
]
