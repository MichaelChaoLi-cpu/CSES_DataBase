from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = ROOT / "rsc" / "cses_db"
sys.path.insert(0, str(MODULE_ROOT))

from audit_mda_baseline import TABLE_FILES  # noqa: E402
from build_local_release import BUILD_OUTPUTS, BUILD_SCRIPTS, VALIDATION_SCRIPTS  # noqa: E402
from cses_schema_contract import EXPECTED_FAMILY_COUNTS, default_contract_path, load_contract  # noqa: E402
from inventory_cses_archives import normalize_wave  # noqa: E402
from render_cses_migration_sql import render_migration_sql  # noqa: E402

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
