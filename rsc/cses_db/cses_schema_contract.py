"""Load and validate the Git-owned CSES functional-schema contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

EXPECTED_FUNCTIONAL_SCHEMAS = {
    "metadata": "cses_meta",
    "alignment": "cses_alignment",
    "data": "cses_data",
    "analysis": "cses_analysis",
}
EXPECTED_FAMILY_COUNTS = {
    "final": 7,
    "geography": 1,
    "source_dictionary": 7,
    "alignment_summary": 7,
}


@dataclass(frozen=True)
class RelationSpec:
    name: str
    family: str
    target_schema: str
    natural_key: tuple[str, ...]


@dataclass(frozen=True)
class SchemaContract:
    schema_version: int
    migration_name: str
    database: str
    source_schema: str
    compatibility_schema: str
    functional_schemas: dict[str, str]
    reader_roles: tuple[str, ...]
    relations: tuple[RelationSpec, ...]


def default_contract_path(root: Path) -> Path:
    return root / "rsc" / "specs" / "cses_schema_v1.json"


def load_contract(path: Path) -> SchemaContract:
    raw = json.loads(path.read_text(encoding="utf-8"))
    contract = SchemaContract(
        schema_version=int(raw["schema_version"]),
        migration_name=str(raw["migration_name"]),
        database=str(raw["database"]),
        source_schema=str(raw["source_schema"]),
        compatibility_schema=str(raw["compatibility_schema"]),
        functional_schemas=dict(raw["functional_schemas"]),
        reader_roles=tuple(raw["reader_roles"]),
        relations=tuple(
            RelationSpec(
                name=item["name"],
                family=item["family"],
                target_schema=item["target_schema"],
                natural_key=tuple(item["natural_key"]),
            )
            for item in raw["relations"]
        ),
    )
    validate_contract(contract)
    return contract


def validate_contract(contract: SchemaContract) -> None:
    if contract.schema_version != 1:
        raise ValueError(f"Unsupported schema contract version: {contract.schema_version}")
    if contract.source_schema != "public" or contract.compatibility_schema != "public":
        raise ValueError("The v1 migration requires public as both source and compatibility schema")
    if contract.functional_schemas != EXPECTED_FUNCTIONAL_SCHEMAS:
        raise ValueError("Functional schemas differ from the approved v1 architecture")
    if not contract.reader_roles:
        raise ValueError("At least one reader role is required")
    if len(set(contract.reader_roles)) != len(contract.reader_roles):
        raise ValueError("Reader roles must be unique")

    names = [relation.name for relation in contract.relations]
    if len(names) != len(set(names)):
        raise ValueError("Relation names must be unique")
    if len(names) != sum(EXPECTED_FAMILY_COUNTS.values()):
        raise ValueError("The v1 migration must own exactly 22 relations")

    observed_family_counts = {
        family: sum(relation.family == family for relation in contract.relations) for family in EXPECTED_FAMILY_COUNTS
    }
    if observed_family_counts != EXPECTED_FAMILY_COUNTS:
        raise ValueError(f"Relation family counts differ from the v1 contract: {observed_family_counts}")

    allowed_targets = set(EXPECTED_FUNCTIONAL_SCHEMAS.values()) - {"cses_meta"}
    for relation in contract.relations:
        if relation.target_schema not in allowed_targets:
            raise ValueError(f"Invalid target schema for {relation.name}: {relation.target_schema}")
        if relation.family in {"final", "geography"} and not relation.natural_key:
            raise ValueError(f"A natural key is required for {relation.name}")
        if relation.family not in {"final", "geography"} and relation.natural_key:
            raise ValueError(f"Unexpected natural key for {relation.name}")


def quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def qualified(schema: str, relation: str) -> str:
    return f"{quoted_identifier(schema)}.{quoted_identifier(relation)}"
