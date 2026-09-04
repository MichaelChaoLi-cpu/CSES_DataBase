"""Build a deterministic read-only lineage graph from the CSES database."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import quote

import psycopg
from cses_baseline_metadata import connect_database

GRAPH_SCHEMA_VERSION = 1
GRAPH_ID = "cses-lineage-v1"
SCHEMA_ROLES = {
    "cses_alignment": "questionnaire and variable alignment evidence",
    "cses_analysis": "quality, coverage, and stable analytical interfaces",
    "cses_data": "authoritative physical CSES relations",
    "cses_meta": "survey, source, release, storage, and load registry",
    "public": "backward-compatible read interface",
}


def _node_id(kind: str, *parts: object) -> str:
    encoded = [quote(str(part), safe="") for part in parts]
    return ":".join((kind, *encoded))


def _json_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class GraphBuilder:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    def add_node(self, node_id: str, node_type: str, **properties: Any) -> None:
        node = {"id": node_id, "type": node_type, "properties": properties}
        existing = self.nodes.get(node_id)
        if existing is not None and existing != node:
            raise ValueError(f"Conflicting graph node: {node_id}")
        self.nodes[node_id] = node

    def add_edge(self, edge_type: str, source: str, target: str, **properties: Any) -> None:
        if source == target:
            raise ValueError(f"Self-referencing graph edge: {edge_type} {source}")
        key = (edge_type, source, target, _json_key(properties))
        self.edges[key] = {
            "type": edge_type,
            "source": source,
            "target": target,
            "properties": properties,
        }

    def finish(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        dangling = [
            edge
            for edge in self.edges.values()
            if edge["source"] not in self.nodes or edge["target"] not in self.nodes
        ]
        if dangling:
            raise ValueError(f"Graph contains {len(dangling)} dangling edges")
        nodes = sorted(self.nodes.values(), key=lambda item: item["id"])
        edges = sorted(
            self.edges.values(),
            key=lambda item: (item["type"], item["source"], item["target"], _json_key(item["properties"])),
        )
        return nodes, edges


def _require(mapping: dict[int, str], key: int, label: str) -> str:
    try:
        return mapping[key]
    except KeyError as error:
        raise ValueError(f"Missing {label} graph node for database id {key}") from error


def build_lineage_graph(snapshot: dict[str, Any], exporter_code_git_revision: str) -> dict[str, Any]:
    """Build a stable graph using natural-key node identifiers, never surrogate IDs."""
    builder = GraphBuilder()
    database = snapshot["database"]
    database_node = _node_id("database", database["database"])
    builder.add_node(database_node, "database", database=database["database"])

    schema_nodes: dict[str, str] = {}
    for schema in sorted(snapshot["schemas"], key=lambda row: row["schema_name"]):
        name = schema["schema_name"]
        schema_node = _node_id("schema", name)
        schema_nodes[name] = schema_node
        builder.add_node(
            schema_node,
            "schema",
            schema_name=name,
            responsibility=SCHEMA_ROLES[name],
            comment=schema["comment"],
        )
        builder.add_edge("database_has_schema", database_node, schema_node)

    survey_nodes: dict[int, str] = {}
    for survey in sorted(snapshot["surveys"], key=lambda row: row["survey_wave"]):
        survey_node = _node_id("survey", survey["survey_wave"])
        survey_nodes[survey["survey_id"]] = survey_node
        builder.add_node(
            survey_node,
            "survey",
            dataset_name=survey["dataset_name"],
            survey_wave=survey["survey_wave"],
            nominal_survey_year=survey["nominal_survey_year"],
            country_name=survey["country_name"],
            country_code=survey["country_code"],
            release_status=survey["release_status"],
        )
        builder.add_edge("schema_registers_survey", schema_nodes["cses_meta"], survey_node)

    archive_nodes: dict[int, str] = {}
    for archive in sorted(snapshot["source_archives"], key=lambda row: row["relative_path"]):
        archive_node = _node_id("source_archive", archive["relative_path"])
        archive_nodes[archive["source_archive_id"]] = archive_node
        builder.add_node(
            archive_node,
            "source_archive",
            relative_path=archive["relative_path"],
            sha256=archive["sha256"],
            size_bytes=archive["size_bytes"],
            archive_member_count=archive["archive_member_count"],
            inventory_status=archive["inventory_status"],
        )
        builder.add_edge(
            "survey_has_source_archive",
            _require(survey_nodes, archive["survey_id"], "survey"),
            archive_node,
        )

    dataset_nodes: dict[int, str] = {}
    dataset_surveys: dict[int, int] = {}
    for dataset in sorted(
        snapshot["datasets"],
        key=lambda row: (row["archive_relative_path"], row["member_path"], row["nested_member_path"]),
    ):
        dataset_node = _node_id(
            "dataset",
            dataset["archive_relative_path"],
            dataset["member_path"],
            dataset["nested_member_path"],
        )
        dataset_nodes[dataset["dataset_id"]] = dataset_node
        dataset_surveys[dataset["dataset_id"]] = dataset["survey_id"]
        builder.add_node(
            dataset_node,
            "dataset",
            archive_relative_path=dataset["archive_relative_path"],
            member_path=dataset["member_path"],
            nested_member_path=dataset["nested_member_path"],
            module_code=dataset["module_code"],
            source_grain=dataset["source_grain"],
            row_count=dataset["row_count"],
            column_count=dataset["column_count"],
            read_status=dataset["read_status"],
        )
        builder.add_edge(
            "source_archive_contains_dataset",
            _require(archive_nodes, dataset["source_archive_id"], "source archive"),
            dataset_node,
        )
        builder.add_edge(
            "survey_has_dataset",
            _require(survey_nodes, dataset["survey_id"], "survey"),
            dataset_node,
        )

    release_nodes: dict[int, str] = {}
    for release in sorted(snapshot["alignment_releases"], key=lambda row: row["mapping_version"]):
        release_node = _node_id("alignment_release", release["mapping_version"])
        release_nodes[release["alignment_release_id"]] = release_node
        builder.add_node(
            release_node,
            "alignment_release",
            mapping_version=release["mapping_version"],
            status=release["status"],
            description=release["description"],
            specification_sha256=release["specification_sha256"],
        )
        builder.add_edge(
            "schema_registers_alignment_release",
            schema_nodes["cses_meta"],
            release_node,
        )

    storage_nodes: dict[int, str] = {}
    storage_identity: dict[int, str] = {}
    storage_family: dict[int, str] = {}
    for storage in sorted(snapshot["storage_tables"], key=lambda row: (row["table_schema"], row["table_name"])):
        identity = f"{storage['table_schema']}.{storage['table_name']}"
        storage_node = _node_id("storage_table", storage["table_schema"], storage["table_name"])
        storage_nodes[storage["storage_table_id"]] = storage_node
        storage_identity[storage["storage_table_id"]] = identity
        storage_family[storage["storage_table_id"]] = storage["object_family"]
        builder.add_node(
            storage_node,
            "storage_table",
            table_schema=storage["table_schema"],
            table_name=storage["table_name"],
            object_family=storage["object_family"],
            module_code=storage["module_code"],
            analytical_grain=storage["analytical_grain"],
            natural_key=storage["natural_key"],
            row_count=storage["row_count"],
            column_count=storage["column_count"],
            relation_fingerprint=storage["relation_fingerprint"],
        )
        builder.add_edge("schema_contains_storage", schema_nodes[storage["table_schema"]], storage_node)

    view_storage_ids: set[int] = set()
    for view in sorted(snapshot["compatibility_views"], key=lambda row: (row["view_schema"], row["view_name"])):
        view_node = _node_id("compatibility_view", view["view_schema"], view["view_name"])
        view_storage_ids.add(view["storage_table_id"])
        builder.add_node(
            view_node,
            "compatibility_view",
            view_schema=view["view_schema"],
            view_name=view["view_name"],
            column_count=view["column_count"],
            physical_dependency_verified=view["physical_dependency_verified"],
        )
        builder.add_edge("schema_exposes_compatibility_view", schema_nodes[view["view_schema"]], view_node)
        builder.add_edge(
            "storage_exposes_compatibility_view",
            _require(storage_nodes, view["storage_table_id"], "storage table"),
            view_node,
        )

    output_storage_ids: set[int] = set()
    output_dataset_ids: set[int] = set()
    authorization: dict[tuple[int, int], dict[str, set[Any]]] = defaultdict(
        lambda: {"dataset_ids": set(), "roles": set()}
    )
    release_surveys: set[tuple[int, int]] = set()
    for output in sorted(
        snapshot["dataset_outputs"],
        key=lambda row: (row["dataset_id"], row["storage_table_id"], row["contribution_role"]),
    ):
        dataset_node = _require(dataset_nodes, output["dataset_id"], "dataset")
        storage_node = _require(storage_nodes, output["storage_table_id"], "storage table")
        release_node = _require(release_nodes, output["alignment_release_id"], "alignment release")
        builder.add_edge(
            "dataset_materializes_storage",
            dataset_node,
            storage_node,
            mapping_version=output["mapping_version"],
            contribution_role=output["contribution_role"],
            output_row_count=output["output_row_count"],
        )
        output_dataset_ids.add(output["dataset_id"])
        output_storage_ids.add(output["storage_table_id"])
        bucket = authorization[(output["alignment_release_id"], output["storage_table_id"])]
        bucket["dataset_ids"].add(output["dataset_id"])
        bucket["roles"].add(output["contribution_role"])
        release_surveys.add((output["alignment_release_id"], dataset_surveys[output["dataset_id"]]))
        if builder.nodes[release_node]["properties"]["mapping_version"] != output["mapping_version"]:
            raise ValueError("Dataset output mapping version does not match its alignment release")

    for (release_id, storage_id), details in sorted(authorization.items()):
        builder.add_edge(
            "alignment_release_authorizes_storage",
            _require(release_nodes, release_id, "alignment release"),
            _require(storage_nodes, storage_id, "storage table"),
            dataset_count=len(details["dataset_ids"]),
            contribution_roles=sorted(details["roles"]),
        )
    for release_id, survey_id in sorted(release_surveys):
        builder.add_edge(
            "survey_aligned_under",
            _require(survey_nodes, survey_id, "survey"),
            _require(release_nodes, release_id, "alignment release"),
        )

    for run in sorted(
        snapshot["load_runs"],
        key=lambda row: (row["run_scope"], row["source_manifest_sha256"], row["code_git_revision"] or ""),
    ):
        run_node = _node_id(
            "load_run",
            run["run_scope"],
            run["source_manifest_sha256"],
            run["code_git_revision"] or "",
            run["dvc_revision"] or "",
        )
        builder.add_node(
            run_node,
            "load_run",
            run_scope=run["run_scope"],
            status=run["status"],
            source_manifest_sha256=run["source_manifest_sha256"],
            code_git_revision=run["code_git_revision"],
            dvc_revision=run["dvc_revision"],
            row_counts=run["row_counts"],
            validation_summary=run["validation_summary"],
        )
        builder.add_edge("schema_registers_load_run", schema_nodes["cses_meta"], run_node)
        builder.add_edge(
            "alignment_release_has_load_run",
            _require(release_nodes, run["alignment_release_id"], "alignment release"),
            run_node,
        )
        if run["survey_id"] is not None:
            builder.add_edge(
                "survey_has_load_run",
                _require(survey_nodes, run["survey_id"], "survey"),
                run_node,
            )

    instrument_nodes: dict[int, str] = {}
    for instrument in sorted(
        snapshot["instruments"],
        key=lambda row: (row["survey_wave"], row["instrument_type"], row["source_file"]),
    ):
        instrument_node = _node_id(
            "instrument", instrument["survey_wave"], instrument["instrument_type"], instrument["source_file"]
        )
        instrument_nodes[instrument["instrument_id"]] = instrument_node
        builder.add_node(
            instrument_node,
            "instrument",
            instrument_type=instrument["instrument_type"],
            source_file=instrument["source_file"],
            source_url=instrument["source_url"],
            source_sha256=instrument["source_sha256"],
            document_title=instrument["document_title"],
            publication_date=instrument["publication_date"],
            language_code=instrument["language_code"],
            documentation_status=instrument["documentation_status"],
        )
        builder.add_edge(
            "survey_has_instrument",
            _require(survey_nodes, instrument["survey_id"], "survey"),
            instrument_node,
        )

    question_nodes: dict[int, str] = {}
    for question in sorted(
        snapshot["questions"],
        key=lambda row: (row["instrument_id"], row["sequence_number"] or 0, row["question_code"]),
    ):
        instrument_node = _require(instrument_nodes, question["instrument_id"], "instrument")
        question_node = _node_id("question", instrument_node, question["question_code"])
        question_nodes[question["question_id"]] = question_node
        builder.add_node(
            question_node,
            "question",
            question_code=question["question_code"],
            question_text=question["question_text"],
            section_name=question["section_name"],
            sequence_number=question["sequence_number"],
            source_page=question["source_page"],
            question_grain=question["question_grain"],
            is_exact_question_text=question["is_exact_question_text"],
            documentation_status=question["documentation_status"],
        )
        builder.add_edge("instrument_has_question", instrument_node, question_node)

    source_variable_nodes: dict[tuple[int, str], str] = {}
    for variable in sorted(
        snapshot["source_variables"],
        key=lambda row: (row["dataset_id"], row["variable_position"], row["variable_name"]),
    ):
        dataset_node = _require(dataset_nodes, variable["dataset_id"], "dataset")
        variable_node = _node_id("source_variable", dataset_node, variable["variable_name"])
        source_variable_nodes[(variable["dataset_id"], variable["variable_name"])] = variable_node
        builder.add_node(
            variable_node,
            "source_variable",
            variable_name=variable["variable_name"],
            variable_position=variable["variable_position"],
            storage_type=variable["storage_type"],
            variable_label=variable["variable_label"],
            alignment_status=variable["alignment_status"],
            question_link_status=variable["question_link_status"],
            question_link_role=variable["question_link_role"],
        )
        builder.add_edge("dataset_has_source_variable", dataset_node, variable_node)
        if variable["question_id"] is not None:
            builder.add_edge(
                "question_links_source_variable",
                _require(question_nodes, variable["question_id"], "question"),
                variable_node,
                link_status=variable["question_link_status"],
                link_role=variable["question_link_role"],
            )

    canonical_nodes: dict[int, str] = {}
    storage_by_name = {
        builder.nodes[node]["properties"]["table_name"]: node for node in storage_nodes.values()
    }
    for canonical in sorted(
        snapshot["canonical_variables"], key=lambda row: (row["target_table"], row["canonical_name"])
    ):
        canonical_node = _node_id("canonical_variable", canonical["target_table"], canonical["canonical_name"])
        canonical_nodes[canonical["canonical_variable_id"]] = canonical_node
        builder.add_node(
            canonical_node,
            "canonical_variable",
            target_table=canonical["target_table"],
            canonical_name=canonical["canonical_name"],
            database_type=canonical["database_type"],
            measure_type=canonical["measure_type"],
            canonical_definition=canonical["canonical_definition"],
            analytical_grain=canonical["analytical_grain"],
            status=canonical["status"],
        )
        try:
            target_node = storage_by_name[canonical["target_table"]]
        except KeyError as error:
            raise ValueError(f"Canonical target is not a registered storage table: {canonical['target_table']}") from error
        builder.add_edge("canonical_variable_belongs_to_storage", canonical_node, target_node)

    value_mapping_count = 0
    for mapping in sorted(
        snapshot["variable_mappings"],
        key=lambda row: (row["dataset_id"], row["canonical_variable_id"], row["mapping_version"]),
    ):
        release_node = _require(release_nodes, mapping["alignment_release_id"], "alignment release")
        canonical_node = _require(canonical_nodes, mapping["canonical_variable_id"], "canonical variable")
        builder.add_edge("alignment_release_includes_canonical", release_node, canonical_node)
        value_mapping_count += mapping["value_mapping_count"]
        for variable_name in sorted(mapping["source_variable_names"]):
            try:
                source_node = source_variable_nodes[(mapping["dataset_id"], variable_name)]
            except KeyError as error:
                raise ValueError(
                    f"Mapping references missing source variable: dataset={mapping['dataset_id']} variable={variable_name}"
                ) from error
            builder.add_edge(
                "source_variable_maps_to_canonical",
                source_node,
                canonical_node,
                mapping_version=mapping["mapping_version"],
                source_kind=mapping["source_kind"],
                transformation_rule=mapping["transformation_rule"],
                alignment_status=mapping["alignment_status"],
                observed_row_count=mapping["observed_row_count"],
                observed_nonnull_count=mapping["observed_nonnull_count"],
                observed_distinct_count=mapping["observed_distinct_count"],
                observation_status=mapping["observation_status"],
                value_mapping_count=mapping["value_mapping_count"],
            )

    nodes, edges = builder.finish()
    node_types = Counter(node["type"] for node in nodes)
    edge_types = Counter(edge["type"] for edge in edges)
    storage_coverage = []
    for family in sorted(set(storage_family.values())):
        family_ids = {storage_id for storage_id, item_family in storage_family.items() if item_family == family}
        covered_ids = family_ids & output_storage_ids
        storage_coverage.append(
            {
                "object_family": family,
                "storage_count": len(family_ids),
                "with_dataset_output_count": len(covered_ids),
                "without_dataset_output_count": len(family_ids - covered_ids),
            }
        )
    storage_without_outputs = sorted(
        storage_identity[storage_id] for storage_id in set(storage_nodes) - output_storage_ids
    )
    checks = {
        "database_name_matches": database["database"] == "mda",
        "transaction_is_read_only": database["transaction_read_only"] == "on",
        "all_required_schemas_present": set(schema_nodes) == set(SCHEMA_ROLES),
        "all_storage_relations_have_compatibility_views": view_storage_ids == set(storage_nodes),
        "all_compatibility_dependencies_are_verified": all(
            view["physical_dependency_verified"] for view in snapshot["compatibility_views"]
        ),
    }
    summary = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_type_counts": dict(sorted(node_types.items())),
        "edge_type_counts": dict(sorted(edge_types.items())),
        "dataset_with_output_count": len(output_dataset_ids),
        "dataset_without_output_count": len(dataset_nodes) - len(output_dataset_ids),
        "storage_output_coverage": storage_coverage,
        "storage_without_dataset_outputs": storage_without_outputs,
        "value_mapping_count": value_mapping_count,
    }
    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "graph_id": GRAPH_ID,
        "source": {
            "database": database["database"],
            "projection": "authoritative_cses_registry_alignment_storage_and_compatibility_state",
            "transaction_read_only": True,
            "exporter_code_git_revision": exporter_code_git_revision,
        },
        "checks": checks,
        "nodes": nodes,
        "edges": edges,
        "summary": summary,
    }


def _fetchall(
    connection: psycopg.Connection[dict[str, Any]],
    query: str,
    parameters: tuple[Any, ...] = (),
) -> list[dict]:
    if parameters:
        return connection.execute(query, parameters).fetchall()
    return connection.execute(query).fetchall()


def read_lineage_snapshot(connection: psycopg.Connection[dict[str, Any]]) -> dict[str, Any]:
    database = connection.execute(
        """
        SELECT current_database() AS database,
               current_setting('transaction_read_only') AS transaction_read_only
        """
    ).fetchone()
    schemas = _fetchall(
        connection,
        """
        SELECT n.nspname AS schema_name, obj_description(n.oid, 'pg_namespace') AS comment
        FROM pg_catalog.pg_namespace AS n
        WHERE n.nspname = ANY(%s)
        ORDER BY n.nspname
        """,
        (sorted(SCHEMA_ROLES),),
    )
    surveys = _fetchall(
        connection,
        """
        SELECT survey_id, dataset_name, survey_wave, nominal_survey_year,
               country_name, country_code::text, release_status
        FROM cses_meta.cses_survey
        ORDER BY survey_wave
        """,
    )
    source_archives = _fetchall(
        connection,
        """
        SELECT source_archive_id, survey_id, relative_path, sha256::text,
               size_bytes, archive_member_count, inventory_status
        FROM cses_meta.cses_source_archive
        ORDER BY relative_path
        """,
    )
    datasets = _fetchall(
        connection,
        """
        SELECT d.dataset_id, d.source_archive_id, d.survey_id, archive.relative_path AS archive_relative_path,
               d.member_path, d.nested_member_path, d.module_code, d.source_grain,
               d.row_count, d.column_count, d.read_status
        FROM cses_meta.cses_dataset AS d
        JOIN cses_meta.cses_source_archive AS archive USING (source_archive_id)
        ORDER BY archive.relative_path, d.member_path, d.nested_member_path
        """,
    )
    alignment_releases = _fetchall(
        connection,
        """
        SELECT alignment_release_id, mapping_version, status, description, specification_sha256::text
        FROM cses_meta.cses_alignment_release
        ORDER BY mapping_version
        """,
    )
    storage_tables = _fetchall(
        connection,
        """
        SELECT storage_table_id, table_schema, table_name, object_family, module_code,
               analytical_grain, natural_key, row_count, column_count, relation_fingerprint::text
        FROM cses_meta.cses_storage_table
        ORDER BY table_schema, table_name
        """,
    )
    dataset_outputs = _fetchall(
        connection,
        """
        SELECT output.dataset_id, output.storage_table_id, output.alignment_release_id,
               release.mapping_version, output.contribution_role, output.output_row_count
        FROM cses_meta.cses_dataset_output AS output
        LEFT JOIN cses_meta.cses_alignment_release AS release USING (alignment_release_id)
        ORDER BY output.dataset_id, output.storage_table_id, output.contribution_role
        """,
    )
    load_runs = _fetchall(
        connection,
        """
        SELECT load_run_id, survey_id, alignment_release_id, run_scope,
               source_manifest_sha256::text, code_git_revision, dvc_revision,
               status, row_counts, validation_summary
        FROM cses_meta.cses_load_run
        ORDER BY run_scope, source_manifest_sha256, load_run_id
        """,
    )
    compatibility_views = _fetchall(
        connection,
        """
        SELECT storage.storage_table_id, 'public'::text AS view_schema,
               view_class.relname AS view_name,
               count(attribute.attnum)::integer AS column_count,
               EXISTS (
                   SELECT 1
                   FROM pg_catalog.pg_rewrite AS rewrite
                   JOIN pg_catalog.pg_depend AS dependency ON dependency.objid = rewrite.oid
                   WHERE rewrite.ev_class = view_class.oid
                     AND dependency.refobjid = target_class.oid
               ) AS physical_dependency_verified
        FROM cses_meta.cses_storage_table AS storage
        JOIN pg_catalog.pg_class AS target_class
          ON target_class.oid = to_regclass(format('%I.%I', storage.table_schema, storage.table_name))
        JOIN pg_catalog.pg_class AS view_class ON view_class.relname = storage.table_name
        JOIN pg_catalog.pg_namespace AS view_namespace ON view_namespace.oid = view_class.relnamespace
        LEFT JOIN pg_catalog.pg_attribute AS attribute
          ON attribute.attrelid = view_class.oid
         AND attribute.attnum > 0
         AND NOT attribute.attisdropped
        WHERE view_namespace.nspname = 'public' AND view_class.relkind = 'v'
        GROUP BY storage.storage_table_id, view_class.oid, view_class.relname, target_class.oid
        ORDER BY view_class.relname
        """,
    )
    instruments = _fetchall(
        connection,
        """
        SELECT instrument.instrument_id, instrument.survey_id, survey.survey_wave,
               instrument.instrument_type, instrument.source_file, instrument.source_url,
               instrument.source_sha256::text, instrument.document_title,
               instrument.publication_date::text, instrument.language_code,
               instrument.documentation_status
        FROM cses_alignment.cses_instrument AS instrument
        JOIN cses_meta.cses_survey AS survey USING (survey_id)
        ORDER BY survey.survey_wave, instrument.instrument_type, instrument.source_file
        """,
    )
    questions = _fetchall(
        connection,
        """
        SELECT question_id, instrument_id, question_code, question_text, section_name,
               sequence_number, source_page, question_grain, is_exact_question_text,
               documentation_status
        FROM cses_alignment.cses_question
        ORDER BY instrument_id, sequence_number, question_code
        """,
    )
    source_variables = _fetchall(
        connection,
        """
        SELECT source_variable_id, dataset_id, question_id, variable_name, variable_position,
               storage_type, variable_label, question_link_status, question_link_role,
               alignment_status
        FROM cses_alignment.cses_source_variable
        ORDER BY dataset_id, variable_position, variable_name
        """,
    )
    canonical_variables = _fetchall(
        connection,
        """
        SELECT canonical_variable_id, target_table, canonical_name, database_type,
               measure_type, canonical_definition, analytical_grain, status
        FROM cses_alignment.cses_canonical_variable
        ORDER BY target_table, canonical_name
        """,
    )
    variable_mappings = _fetchall(
        connection,
        """
        SELECT mapping.variable_mapping_id, mapping.dataset_id, mapping.canonical_variable_id,
               mapping.alignment_release_id, release.mapping_version, mapping.source_variable_names,
               mapping.source_kind, mapping.transformation_rule, mapping.alignment_status,
               mapping.observed_row_count, mapping.observed_nonnull_count,
               mapping.observed_distinct_count, mapping.observation_status,
               count(value.source_value)::integer AS value_mapping_count
        FROM cses_alignment.cses_variable_mapping AS mapping
        JOIN cses_meta.cses_alignment_release AS release USING (alignment_release_id)
        LEFT JOIN cses_alignment.cses_value_mapping AS value USING (variable_mapping_id)
        GROUP BY mapping.variable_mapping_id, release.mapping_version
        ORDER BY mapping.dataset_id, mapping.canonical_variable_id, release.mapping_version
        """,
    )
    return {
        "database": database,
        "schemas": schemas,
        "surveys": surveys,
        "source_archives": source_archives,
        "datasets": datasets,
        "alignment_releases": alignment_releases,
        "storage_tables": storage_tables,
        "dataset_outputs": dataset_outputs,
        "load_runs": load_runs,
        "compatibility_views": compatibility_views,
        "instruments": instruments,
        "questions": questions,
        "source_variables": source_variables,
        "canonical_variables": canonical_variables,
        "variable_mappings": variable_mappings,
    }


def render_lineage_overview(graph: dict[str, Any]) -> str:
    """Render a compact aggregate Mermaid view from the full graph summary."""
    nodes = graph["summary"]["node_type_counts"]
    edges = graph["summary"]["edge_type_counts"]
    gaps = len(graph["summary"]["storage_without_dataset_outputs"])
    return "\n".join(
        [
            "%% Deterministic aggregate view of cses-lineage-v1.",
            "flowchart LR",
            f'    SURVEY["{nodes.get("survey", 0)} survey waves"]',
            f'    ARCHIVE["{nodes.get("source_archive", 0)} source archives"]',
            f'    DATASET["{nodes.get("dataset", 0)} physical datasets"]',
            f'    RELEASE["{nodes.get("alignment_release", 0)} alignment release"]',
            f'    STORAGE["{nodes.get("storage_table", 0)} authoritative relations"]',
            f'    VIEW["{nodes.get("compatibility_view", 0)} public compatibility views"]',
            f'    RUN["{nodes.get("load_run", 0)} load run"]',
            f'    ALIGN["{nodes.get("source_variable", 0)} source variables<br/>{nodes.get("canonical_variable", 0)} canonical variables"]',
            f'    GAP["{gaps} relations without<br/>registered dataset edges"]',
            "",
            f'    SURVEY -->|"{edges.get("survey_has_source_archive", 0)}"| ARCHIVE',
            f'    ARCHIVE -->|"{edges.get("source_archive_contains_dataset", 0)}"| DATASET',
            f'    DATASET -->|"{edges.get("dataset_materializes_storage", 0)}"| STORAGE',
            f'    RELEASE -->|"{edges.get("alignment_release_authorizes_storage", 0)} targets"| STORAGE',
            "    RELEASE --> RUN",
            f'    STORAGE -->|"{edges.get("storage_exposes_compatibility_view", 0)} verified projections"| VIEW',
            "    DATASET -.-> ALIGN",
            "    ALIGN -.-> STORAGE",
            "    STORAGE -.-> GAP",
            "",
        ]
    )


def _write_atomic(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def export_lineage_graph(
    connection_arguments: dict[str, object],
    output_path: Path,
    overview_path: Path,
    exporter_code_git_revision: str,
) -> dict[str, Any]:
    with connect_database(connection_arguments) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            snapshot = read_lineage_snapshot(connection)
    graph = build_lineage_graph(snapshot, exporter_code_git_revision)
    failed_checks = sorted(name for name, passed in graph["checks"].items() if not passed)
    if failed_checks:
        raise RuntimeError(f"CSES lineage export checks failed: {failed_checks}")
    graph_payload = json.dumps(graph, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    overview_payload = render_lineage_overview(graph)
    _write_atomic(output_path, graph_payload)
    _write_atomic(overview_path, overview_payload)
    return {
        "status": "exported",
        "database_mutated": False,
        "output_file": str(output_path),
        "output_sha256": hashlib.sha256(graph_payload.encode("utf-8")).hexdigest(),
        "output_bytes": len(graph_payload.encode("utf-8")),
        "overview_file": str(overview_path),
        "overview_sha256": hashlib.sha256(overview_payload.encode("utf-8")).hexdigest(),
        "overview_bytes": len(overview_payload.encode("utf-8")),
        "summary": graph["summary"],
    }
