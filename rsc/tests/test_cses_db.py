from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "rsc" / "cses_db"
sys.path.insert(0, str(MODULE_ROOT))

from audit_mda_baseline import TABLE_FILES  # noqa: E402
from build_local_release import BUILD_OUTPUTS, BUILD_SCRIPTS, VALIDATION_SCRIPTS  # noqa: E402
from cses_baseline_metadata import (  # noqa: E402
    build_desired_state,
    default_baseline_spec_path,
    load_baseline_spec,
    reconcile_states,
    split_source_dataset,
)
from cses_lineage_graph import build_lineage_graph, render_lineage_overview  # noqa: E402
from cses_schema_contract import EXPECTED_FAMILY_COUNTS, default_contract_path, load_contract  # noqa: E402
from cses_storage_provenance import (  # noqa: E402
    build_desired_state as build_storage_provenance_state,
)
from cses_storage_provenance import (  # noqa: E402
    default_storage_provenance_spec_path,
    load_storage_provenance_spec,
)
from cses_storage_provenance import (  # noqa: E402
    reconcile_states as reconcile_storage_provenance,
)
from cses_variable_catalog import (  # noqa: E402
    build_desired_state as build_variable_catalog_state,
)
from cses_variable_catalog import (  # noqa: E402
    default_variable_catalog_spec_path,
    load_variable_catalog_spec,
)
from cses_variable_catalog import (  # noqa: E402
    reconcile_states as reconcile_variable_catalog,
)
from import_cses_baseline_metadata import validate_apply_gate, validate_reviewed_plan  # noqa: E402
from import_cses_storage_provenance import (  # noqa: E402
    validate_apply_gate as validate_storage_provenance_apply_gate,
)
from import_cses_storage_provenance import (  # noqa: E402
    validate_reviewed_plan as validate_storage_provenance_plan,
)
from import_cses_variable_catalog import (  # noqa: E402
    validate_apply_gate as validate_variable_catalog_apply_gate,
)
from inventory_cses_archives import normalize_wave  # noqa: E402
from render_cses_migration_sql import render_migration_sql  # noqa: E402
from validate_cses_baseline_metadata import build_validation_checks  # noqa: E402

EXPECTED_ARCHIVES = {
    "CSES 2004.zip",
    "CSES 2007.zip",
    "CSES 2009.zip",
    "CSES 2011-12.zip",
    "CSES2013.zip",
    "CSES 2014.zip",
    "CSES2016.zip",
    "CSES2017.zip",
    "CSES2019.zip",
    "CSES2021-Village_data.zip",
    "Data of CSES2021.zip",
}


def test_wave_normalization() -> None:
    assert normalize_wave("CSES 2004.zip") == "2004"
    assert normalize_wave("CSES 2011-12.zip") == "2011-12"
    assert normalize_wave("CSES2013.zip::CSES 2013.zip") == "2013"
    assert normalize_wave("Data of CSES2021.zip") == "2021"


def test_expected_raw_archives_are_present() -> None:
    observed = {path.name for path in (ROOT / "data" / "raw").glob("*.zip")}
    assert observed == EXPECTED_ARCHIVES


def test_orchestrator_references_existing_scripts() -> None:
    for name in (*BUILD_SCRIPTS, *VALIDATION_SCRIPTS):
        assert (MODULE_ROOT / name).is_file()
    assert set(BUILD_OUTPUTS) == set(BUILD_SCRIPTS)
    assert set(TABLE_FILES.values()) == set(BUILD_OUTPUTS.values())


def test_no_legacy_raw_root_in_ported_code() -> None:
    for path in MODULE_ROOT.glob("*.py"):
        if path.name == "compare_reference_release.py":
            continue
        assert "data/raw/CSE/" not in path.read_text(encoding="utf-8")


def test_schema_contract_owns_only_the_approved_22_relations() -> None:
    contract = load_contract(default_contract_path(ROOT))
    assert len(contract.relations) == 22
    assert {
        family: sum(relation.family == family for relation in contract.relations) for family in EXPECTED_FAMILY_COUNTS
    } == EXPECTED_FAMILY_COUNTS
    assert {relation.target_schema for relation in contract.relations} == {
        "cses_alignment",
        "cses_analysis",
        "cses_data",
    }
    assert "final_HEAT_LABOR_CSES" not in {relation.name for relation in contract.relations}


def test_generated_migration_sql_is_current_and_non_destructive() -> None:
    contract = load_contract(default_contract_path(ROOT))
    schema_ddl = (ROOT / "rsc" / "sql" / "cses_schema_v1.sql").read_text(encoding="utf-8")
    rendered = render_migration_sql(contract, schema_ddl)
    stored = (ROOT / "rsc" / "sql" / "cses_public_to_functional_v1.sql").read_text(encoding="utf-8")
    assert rendered == stored
    assert "ALTER TABLE %I.%I SET SCHEMA %I" in rendered
    assert "'CREATE OR REPLACE VIEW %I.%I AS SELECT * FROM %I.%I'" in rendered
    assert re.search(r"\bDROP\s+(TABLE|VIEW|SCHEMA|MATERIALIZED)\b", rendered, re.IGNORECASE) is None
    assert "TRUNCATE " not in rendered.upper()
    assert re.search(r"\bDELETE\s+FROM\b", rendered, re.IGNORECASE) is None


def test_schema_ddl_defines_functional_model_without_public_tables() -> None:
    ddl = (ROOT / "rsc" / "sql" / "cses_schema_v1.sql").read_text(encoding="utf-8")
    for schema in ("cses_meta", "cses_alignment", "cses_data", "cses_analysis"):
        assert f"CREATE SCHEMA IF NOT EXISTS {schema};" in ddl
    assert ddl.count("CREATE TABLE IF NOT EXISTS cses_meta.") == 7
    assert ddl.count("CREATE TABLE IF NOT EXISTS cses_alignment.") == 6
    assert "CREATE TABLE IF NOT EXISTS public." not in ddl


def test_baseline_metadata_contract_has_reviewed_scope_and_write_gate() -> None:
    spec = load_baseline_spec(default_baseline_spec_path(ROOT))
    assert len(spec["surveys"]) == 10
    assert len(spec["source_archives"]) == 11
    assert len(spec["storage_relations"]) == 22
    assert len(spec["direct_outputs"]) == 7
    assert spec["alignment_release"]["requires_explicit_approval"] is True
    with pytest.raises(ValueError, match="without --apply"):
        validate_apply_gate(False, None, spec)
    with pytest.raises(ValueError, match="without --confirm"):
        validate_apply_gate(True, "wrong", spec)
    validate_apply_gate(True, spec["approval_phrase"], spec)


def test_nested_source_dataset_identity_is_stable() -> None:
    source = "data/raw/CSES2013.zip::CSES2013/CSES2013/CSES 2013.zip::HHMembers.dta"
    assert split_source_dataset(source) == (
        "data/raw/CSES2013.zip",
        "CSES2013/CSES2013/CSES 2013.zip",
        "HHMembers.dta",
    )


def test_baseline_metadata_desired_state_is_complete_and_locally_valid() -> None:
    desired, diagnostics = build_desired_state(ROOT)
    assert diagnostics["record_counts"] == {
        "surveys": 10,
        "source_archives": 11,
        "datasets": 171,
        "alignment_releases": 1,
        "storage_tables": 22,
        "dataset_outputs": 62,
        "load_runs": 1,
    }
    assert all(diagnostics["local_checks"].values())
    assert {item["table_name"] for item in desired["dataset_outputs"]} == {
        "final_EC_CSES",
        "final_ED_CSES",
        "final_HH_CSES",
        "final_HL_CSES",
        "final_HO_CSES",
        "final_SURVEY_DATE_CSES",
        "final_VL_CSES",
    }
    assert not any(item["table_name"] == "dim_geo_CSES" for item in desired["dataset_outputs"])


def test_baseline_reconciliation_distinguishes_noop_insert_and_conflict() -> None:
    desired = {
        "surveys": [
            {
                "survey_wave": "2004",
                "dataset_name": "CSES 2004",
            },
            {
                "survey_wave": "2007",
                "dataset_name": "CSES 2007",
            },
        ]
    }
    existing = {
        "surveys": [
            {
                "survey_wave": "2004",
                "dataset_name": "CSES 2004",
            }
        ]
    }
    operations, conflicts = reconcile_states(desired, existing)
    assert [item["action"] for item in operations] == ["noop", "insert"]
    assert conflicts == []

    existing["surveys"][0]["dataset_name"] = "conflicting name"
    operations, conflicts = reconcile_states(desired, existing)
    assert [item["action"] for item in operations] == ["conflict", "insert"]
    assert len(conflicts) == 1


def test_importer_consumes_exact_reviewed_plan_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    planned = {
        "load_runs": [
            {
                "baseline_import_id": "baseline-v1",
                "code_git_revision": "reviewed-commit",
                "dvc_revision": "md5:input.dir",
            }
        ]
    }
    current = json.loads(json.dumps(planned))
    current["load_runs"][0]["code_git_revision"] = "later-data-pointer-commit"
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "baseline_id": "baseline-v1",
                "database_mutated": False,
                "preflight_ready": True,
                "approval_phrase": "APPROVE",
                "desired_state": planned,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("import_cses_baseline_metadata.subprocess.run", lambda *args, **kwargs: None)
    selected, evidence = validate_reviewed_plan(
        tmp_path,
        plan_path,
        {"baseline_id": "baseline-v1", "approval_phrase": "APPROVE"},
        current,
    )
    assert selected == planned
    assert evidence["code_git_revision"] == "reviewed-commit"

    current["load_runs"][0]["dvc_revision"] = "md5:different.dir"
    with pytest.raises(ValueError, match="differs from the current local evidence"):
        validate_reviewed_plan(
            tmp_path,
            plan_path,
            {"baseline_id": "baseline-v1", "approval_phrase": "APPROVE"},
            current,
        )


def test_post_import_validation_requires_exact_noop_state() -> None:
    plan = {
        "preflight_ready": True,
        "database_mutated": False,
        "desired_record_counts": {"surveys": 1},
        "desired_state": {"load_runs": [{"code_git_revision": "reviewed-commit"}]},
    }
    import_evidence = {
        "reviewed_plan": {
            "sha256": "plan-sha",
            "code_git_revision": "reviewed-commit",
        },
        "inserted_record_counts": {"surveys": 1},
        "database_mutated": True,
        "post_write_action_counts": {"conflict": 0, "insert": 0, "noop": 1},
    }
    database_preflight = {
        "checks": {"transaction_is_read_only": True, "no_existing_metadata_conflicts": True},
        "action_counts": {"conflict": 0, "insert": 0, "noop": 1},
        "existing_record_counts": {"surveys": 1},
    }
    assert all(build_validation_checks(plan, "plan-sha", import_evidence, database_preflight).values())
    database_preflight["action_counts"]["conflict"] = 1
    checks = build_validation_checks(plan, "plan-sha", import_evidence, database_preflight)
    assert checks["all_reviewed_records_are_noops"] is False


def test_storage_provenance_contract_has_exact_scope_and_write_gate() -> None:
    spec = load_storage_provenance_spec(default_storage_provenance_spec_path(ROOT))
    assert len(spec["module_rules"]) == 7
    assert spec["source_alignment_release"] == "cses-baseline-v1"
    assert spec["alignment_release"]["mapping_version"] == "cses-storage-provenance-v1"
    assert spec["alignment_release"]["requires_explicit_approval"] is True
    assert {item["relation"] for item in spec["geography_rule"]["external_dependencies"]} == {
        "public.dim_admin2_cambodia",
        "public.dim_admin3_cambodia",
    }
    with pytest.raises(ValueError, match="without --apply"):
        validate_storage_provenance_apply_gate(False, None, spec)
    with pytest.raises(ValueError, match="without --confirm"):
        validate_storage_provenance_apply_gate(True, "wrong", spec)
    validate_storage_provenance_apply_gate(True, spec["approval_phrase"], spec)


def test_storage_provenance_closes_exact_15_storage_gaps() -> None:
    desired, diagnostics = build_storage_provenance_state(ROOT)
    assert diagnostics["record_counts"] == {
        "alignment_releases": 1,
        "dataset_outputs": 134,
        "load_runs": 1,
    }
    assert all(diagnostics["local_checks"].values())
    assert len(diagnostics["target_relations"]) == 15
    outputs = desired["dataset_outputs"]
    assert sum(record["table_name"].startswith("ind_que_") for record in outputs) == 62
    assert sum(record["table_name"].startswith("align_summary_") for record in outputs) == 62
    assert sum(record["table_name"] == "dim_geo_CSES" for record in outputs) == 10
    assert {
        record["contribution_role"]
        for record in outputs
        if record["table_name"].startswith("ind_que_")
    } == {"source"}
    assert {
        record["contribution_role"]
        for record in outputs
        if record["table_name"].startswith("align_summary_")
    } == {"validation"}
    assert desired["load_runs"][0]["validation_summary"]["variable_level_mapping_created"] is False


def test_variable_catalog_contract_is_conservative_and_write_gated() -> None:
    spec = load_variable_catalog_spec(default_variable_catalog_spec_path(ROOT))
    assert len(spec["module_rules"]) == 7
    assert spec["source_alignment_release"] == "cses-storage-provenance-v1"
    assert spec["alignment_release"]["mapping_version"] == "cses-variable-catalog-v1"
    assert spec["questionnaire_policy"]["instrument_count"] == 0
    assert spec["questionnaire_policy"]["question_count"] == 0
    assert spec["value_mapping_policy"]["count"] == 0
    with pytest.raises(ValueError, match="without --apply"):
        validate_variable_catalog_apply_gate(False, None, spec)
    with pytest.raises(ValueError, match="without --confirm"):
        validate_variable_catalog_apply_gate(True, "wrong", spec)
    validate_variable_catalog_apply_gate(True, spec["approval_phrase"], spec)


def test_variable_catalog_covers_all_sources_and_physical_canonicals() -> None:
    desired, diagnostics = build_variable_catalog_state(ROOT)
    assert diagnostics["record_counts"] == {
        "alignment_releases": 1,
        "source_variables": 4092,
        "canonical_variables": 280,
        "variable_mappings": 1714,
        "load_runs": 1,
    }
    assert diagnostics["scope_counts"]["instruments"] == 0
    assert diagnostics["scope_counts"]["questions"] == 0
    assert diagnostics["scope_counts"]["value_mappings"] == 0
    assert all(diagnostics["local_checks"].values())
    assert len(
        {
            (
                row["archive_relative_path"],
                row["member_path"],
                row["nested_member_path"],
            )
            for row in desired["source_variables"]
        }
    ) == 171
    assert set(diagnostics["mapping_counts_by_target"]) == {
        "final_EC_CSES",
        "final_ED_CSES",
        "final_HH_CSES",
        "final_HL_CSES",
        "final_HO_CSES",
        "final_SURVEY_DATE_CSES",
        "final_VL_CSES",
    }


def test_variable_catalog_reconciliation_detects_conflict() -> None:
    desired = {
        "alignment_releases": [],
        "source_variables": [
            {
                "archive_relative_path": "data/raw/example.zip",
                "member_path": "source.dta",
                "nested_member_path": "",
                "variable_name": "hhid",
                "variable_position": 1,
            }
        ],
        "canonical_variables": [],
        "variable_mappings": [],
        "load_runs": [],
    }
    existing = json.loads(json.dumps(desired))
    operations, conflicts = reconcile_variable_catalog(desired, existing)
    assert [item["action"] for item in operations] == ["noop"]
    assert conflicts == []
    existing["source_variables"][0]["variable_position"] = 2
    operations, conflicts = reconcile_variable_catalog(desired, existing)
    assert [item["action"] for item in operations] == ["conflict"]
    assert len(conflicts) == 1


def test_storage_provenance_reconciliation_is_conflict_sensitive() -> None:
    desired = {
        "alignment_releases": [
            {
                "mapping_version": "storage-v1",
                "status": "approved",
            }
        ],
        "dataset_outputs": [],
        "load_runs": [],
    }
    existing = {
        "alignment_releases": [],
        "dataset_outputs": [],
        "load_runs": [],
    }
    operations, conflicts = reconcile_storage_provenance(desired, existing)
    assert operations[0]["action"] == "insert"
    assert conflicts == []
    existing["alignment_releases"] = [
        {
            "mapping_version": "storage-v1",
            "status": "draft",
        }
    ]
    operations, conflicts = reconcile_storage_provenance(desired, existing)
    assert operations[0]["action"] == "conflict"
    assert len(conflicts) == 1


def test_storage_provenance_importer_binds_exact_reviewed_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    planned = {
        "alignment_releases": [{}],
        "dataset_outputs": [{} for _ in range(134)],
        "load_runs": [
            {
                "storage_provenance_import_id": "storage-v1",
                "code_git_revision": "reviewed-commit",
                "dvc_revision": "md5:input.dir",
            }
        ],
    }
    current = json.loads(json.dumps(planned))
    current["load_runs"][0]["code_git_revision"] = "later-pointer-commit"
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "provenance_release_id": "storage-v1",
                "database_mutated": False,
                "preflight_ready": True,
                "approval_phrase": "APPROVE",
                "desired_record_counts": {
                    "alignment_releases": 1,
                    "dataset_outputs": 134,
                    "load_runs": 1,
                },
                "desired_state": planned,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("import_cses_storage_provenance.subprocess.run", lambda *args, **kwargs: None)
    selected, evidence = validate_storage_provenance_plan(
        tmp_path,
        plan_path,
        {"provenance_release_id": "storage-v1", "approval_phrase": "APPROVE"},
        current,
    )
    assert selected == planned
    assert evidence["code_git_revision"] == "reviewed-commit"
    current["load_runs"][0]["dvc_revision"] = "md5:different.dir"
    with pytest.raises(ValueError, match="differs from the current local evidence"):
        validate_storage_provenance_plan(
            tmp_path,
            plan_path,
            {"provenance_release_id": "storage-v1", "approval_phrase": "APPROVE"},
            current,
        )


def _lineage_snapshot() -> dict[str, object]:
    return {
        "database": {"database": "mda", "transaction_read_only": "on"},
        "schemas": [
            {"schema_name": name, "comment": f"{name} comment"}
            for name in ("public", "cses_meta", "cses_data", "cses_analysis", "cses_alignment")
        ],
        "surveys": [
            {
                "survey_id": 1,
                "dataset_name": "CSES 2021",
                "survey_wave": "2021",
                "nominal_survey_year": 2021,
                "country_name": "Cambodia",
                "country_code": "KHM",
                "release_status": "baseline",
            }
        ],
        "source_archives": [
            {
                "source_archive_id": 2,
                "survey_id": 1,
                "relative_path": "data/raw/CSES 2021.zip",
                "sha256": "a" * 64,
                "size_bytes": 10,
                "archive_member_count": 1,
                "inventory_status": "validated",
            }
        ],
        "datasets": [
            {
                "dataset_id": 3,
                "source_archive_id": 2,
                "survey_id": 1,
                "archive_relative_path": "data/raw/CSES 2021.zip",
                "member_path": "household.dta",
                "nested_member_path": "",
                "module_code": "HH",
                "source_grain": "household-wave",
                "row_count": 2,
                "column_count": 3,
                "read_status": "readable",
            }
        ],
        "alignment_releases": [
            {
                "alignment_release_id": 4,
                "mapping_version": "v1",
                "status": "approved",
                "description": "Test release",
                "specification_sha256": "b" * 64,
            }
        ],
        "storage_tables": [
            {
                "storage_table_id": 5,
                "table_schema": "cses_data",
                "table_name": "final_HH_CSES",
                "object_family": "final",
                "module_code": "HH",
                "analytical_grain": "household-wave",
                "natural_key": ["survey_wave", "household_id"],
                "row_count": 2,
                "column_count": 3,
                "relation_fingerprint": "c" * 64,
            },
            {
                "storage_table_id": 6,
                "table_schema": "cses_data",
                "table_name": "dim_geo_CSES",
                "object_family": "geography",
                "module_code": "GEO",
                "analytical_grain": "PSU-wave",
                "natural_key": ["survey_wave", "psu"],
                "row_count": 1,
                "column_count": 2,
                "relation_fingerprint": "d" * 64,
            },
        ],
        "dataset_outputs": [
            {
                "dataset_id": 3,
                "storage_table_id": 5,
                "alignment_release_id": 4,
                "mapping_version": "v1",
                "contribution_role": "source",
                "output_row_count": 2,
            }
        ],
        "load_runs": [
            {
                "load_run_id": 7,
                "survey_id": None,
                "alignment_release_id": 4,
                "run_scope": "baseline",
                "source_manifest_sha256": "e" * 64,
                "code_git_revision": "code-revision",
                "dvc_revision": "md5:" + "f" * 32 + ".dir",
                "status": "loaded",
                "row_counts": {"surveys": 1},
                "validation_summary": {"passed": True},
            }
        ],
        "compatibility_views": [
            {
                "storage_table_id": storage_id,
                "view_schema": "public",
                "view_name": name,
                "column_count": columns,
                "physical_dependency_verified": True,
            }
            for storage_id, name, columns in ((5, "final_HH_CSES", 3), (6, "dim_geo_CSES", 2))
        ],
        "instruments": [],
        "questions": [],
        "source_variables": [],
        "canonical_variables": [],
        "variable_mappings": [],
    }


def test_lineage_graph_is_deterministic_and_reports_visible_gaps() -> None:
    snapshot = _lineage_snapshot()
    graph = build_lineage_graph(snapshot, "exporter-revision")
    reversed_snapshot = {
        key: list(reversed(value)) if isinstance(value, list) else value for key, value in snapshot.items()
    }
    assert graph == build_lineage_graph(reversed_snapshot, "exporter-revision")
    assert all(graph["checks"].values())
    assert graph["source"]["transaction_read_only"] is True
    assert graph["summary"]["storage_without_dataset_outputs"] == ["cses_data.dim_geo_CSES"]
    assert graph["summary"]["edge_type_counts"]["dataset_materializes_storage"] == 1
    assert graph["summary"]["edge_type_counts"]["storage_exposes_compatibility_view"] == 2
    assert graph["summary"]["node_type_counts"]["dataset"] == 1


def test_lineage_overview_uses_graph_counts() -> None:
    overview = render_lineage_overview(build_lineage_graph(_lineage_snapshot(), "exporter-revision"))
    assert 'DATASET["1 physical datasets"]' in overview
    assert 'STORAGE["2 authoritative relations"]' in overview
    assert 'GAP["1 relations without<br/>registered dataset edges"]' in overview


def test_lineage_graph_preserves_question_and_variable_mapping_paths() -> None:
    snapshot = _lineage_snapshot()
    snapshot["instruments"] = [
        {
            "instrument_id": 8,
            "survey_id": 1,
            "survey_wave": "2021",
            "instrument_type": "HH",
            "source_file": "questionnaire.pdf",
            "source_url": None,
            "source_sha256": "1" * 64,
            "document_title": "Household questionnaire",
            "publication_date": "2021-01-01",
            "language_code": "en",
            "documentation_status": "verified",
        }
    ]
    snapshot["questions"] = [
        {
            "question_id": 9,
            "instrument_id": 8,
            "question_code": "Q1",
            "question_text": "Test question?",
            "section_name": "Section 1",
            "sequence_number": 1,
            "source_page": 1,
            "question_grain": "household-wave",
            "is_exact_question_text": True,
            "documentation_status": "verified",
        }
    ]
    snapshot["source_variables"] = [
        {
            "source_variable_id": 10,
            "dataset_id": 3,
            "question_id": 9,
            "variable_name": "q1",
            "variable_position": 1,
            "storage_type": "int8",
            "variable_label": "Test question",
            "question_link_status": "verified",
            "question_link_role": "direct_response",
            "alignment_status": "loaded",
        }
    ]
    snapshot["canonical_variables"] = [
        {
            "canonical_variable_id": 11,
            "target_table": "final_HH_CSES",
            "canonical_name": "answer",
            "database_type": "smallint",
            "measure_type": "category",
            "canonical_definition": "Reviewed answer",
            "analytical_grain": "household-wave",
            "status": "approved",
        }
    ]
    snapshot["variable_mappings"] = [
        {
            "variable_mapping_id": 12,
            "dataset_id": 3,
            "canonical_variable_id": 11,
            "alignment_release_id": 4,
            "mapping_version": "v1",
            "source_variable_names": ["q1"],
            "source_kind": "explicit",
            "transformation_rule": "Identity mapping.",
            "alignment_status": "loaded",
            "observed_row_count": 2,
            "observed_nonnull_count": 2,
            "observed_distinct_count": 2,
            "observation_status": "observed",
            "value_mapping_count": 2,
        }
    ]
    graph = build_lineage_graph(snapshot, "exporter-revision")
    edge_types = graph["summary"]["edge_type_counts"]
    assert edge_types["survey_has_instrument"] == 1
    assert edge_types["instrument_has_question"] == 1
    assert edge_types["question_links_source_variable"] == 1
    assert edge_types["source_variable_maps_to_canonical"] == 1
    assert edge_types["canonical_variable_belongs_to_storage"] == 1
    assert graph["summary"]["value_mapping_count"] == 2
