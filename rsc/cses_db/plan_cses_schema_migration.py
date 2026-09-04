#!/usr/bin/env python3
"""Run a forced read-only preflight for the CSES functional-schema migration."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import psycopg
from cses_schema_contract import RelationSpec, default_contract_path, load_contract
from psycopg import sql
from psycopg.rows import dict_row


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relation_metadata(
    connection: psycopg.Connection[dict[str, Any]], schema: str, relation: RelationSpec
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT c.oid::bigint AS oid, c.relkind, c.relpersistence,
               pg_get_userbyid(c.relowner) AS owner,
               pg_total_relation_size(c.oid) AS total_bytes,
               obj_description(c.oid) AS comment
        FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relname = %s
        """,
        (schema, relation.name),
    ).fetchone()
    if row is None:
        return None

    columns = connection.execute(
        """
        SELECT a.attnum AS position, a.attname AS name,
               format_type(a.atttypid, a.atttypmod) AS data_type,
               a.attnotnull AS not_null,
               pg_get_expr(defaults.adbin, defaults.adrelid) AS default_expression,
               a.attidentity AS identity_kind
        FROM pg_catalog.pg_attribute AS a
        LEFT JOIN pg_catalog.pg_attrdef AS defaults
          ON defaults.adrelid = a.attrelid AND defaults.adnum = a.attnum
        WHERE a.attrelid = %s::oid AND a.attnum > 0 AND NOT a.attisdropped
        ORDER BY a.attnum
        """,
        (row["oid"],),
    ).fetchall()
    indexes = connection.execute(
        """
        SELECT indexname AS name, indexdef AS definition
        FROM pg_catalog.pg_indexes
        WHERE schemaname = %s AND tablename = %s
        ORDER BY indexname
        """,
        (schema, relation.name),
    ).fetchall()
    constraints = connection.execute(
        """
        SELECT con.conname AS name, con.contype AS type,
               pg_get_constraintdef(con.oid, true) AS definition,
               con.convalidated AS validated
        FROM pg_catalog.pg_constraint AS con
        WHERE con.conrelid = %s::oid
        ORDER BY con.conname
        """,
        (row["oid"],),
    ).fetchall()
    grants = connection.execute(
        """
        SELECT grantee, privilege_type, is_grantable
        FROM information_schema.role_table_grants
        WHERE table_schema = %s AND table_name = %s
        ORDER BY grantee, privilege_type
        """,
        (schema, relation.name),
    ).fetchall()
    dependents = connection.execute(
        """
        SELECT dependent_ns.nspname AS schema, dependent.relname AS name,
               dependent.relkind AS kind
        FROM pg_catalog.pg_depend AS dependency
        JOIN pg_catalog.pg_rewrite AS rewrite ON rewrite.oid = dependency.objid
        JOIN pg_catalog.pg_class AS dependent ON dependent.oid = rewrite.ev_class
        JOIN pg_catalog.pg_namespace AS dependent_ns ON dependent_ns.oid = dependent.relnamespace
        WHERE dependency.refobjid = %s::oid AND dependent.oid <> %s::oid
        ORDER BY dependent_ns.nspname, dependent.relname
        """,
        (row["oid"], row["oid"]),
    ).fetchall()
    row_count = connection.execute(
        sql.SQL("SELECT count(*) AS count FROM {}.{}").format(sql.Identifier(schema), sql.Identifier(relation.name))
    ).fetchone()["count"]

    return {
        **row,
        "schema": schema,
        "name": relation.name,
        "family": relation.family,
        "target_schema": relation.target_schema,
        "row_count": row_count,
        "column_count": len(columns),
        "columns": columns,
        "indexes": indexes,
        "constraints": constraints,
        "grants": grants,
        "dependent_views": dependents,
    }


def key_audit(
    connection: psycopg.Connection[dict[str, Any]], schema: str, relation: RelationSpec
) -> dict[str, Any] | None:
    if not relation.natural_key:
        return None
    key_columns = [sql.Identifier(column) for column in relation.natural_key]
    null_predicate = sql.SQL(" OR ").join(sql.SQL("{} IS NULL").format(column) for column in key_columns)
    null_key_rows = connection.execute(
        sql.SQL("SELECT count(*) AS count FROM {}.{} WHERE {}").format(
            sql.Identifier(schema), sql.Identifier(relation.name), null_predicate
        )
    ).fetchone()["count"]
    duplicate = connection.execute(
        sql.SQL(
            """
            SELECT count(*) AS duplicate_group_count,
                   coalesce(sum(group_size - 1), 0)::bigint AS duplicate_excess_rows
            FROM (
                SELECT count(*)::bigint AS group_size
                FROM {}.{}
                WHERE NOT ({})
                GROUP BY {}
                HAVING count(*) > 1
            ) AS duplicate_groups
            """
        ).format(
            sql.Identifier(schema),
            sql.Identifier(relation.name),
            null_predicate,
            sql.SQL(", ").join(key_columns),
        )
    ).fetchone()
    return {
        "columns": list(relation.natural_key),
        "null_key_rows": null_key_rows,
        **duplicate,
        "primary_key_candidate_ready": (
            null_key_rows == 0 and duplicate["duplicate_group_count"] == 0 and duplicate["duplicate_excess_rows"] == 0
        ),
    }


def relation_kind(connection: psycopg.Connection[dict[str, Any]], schema: str, relation: str) -> str | None:
    row = connection.execute(
        """
        SELECT c.relkind
        FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relname = %s
        """,
        (schema, relation),
    ).fetchone()
    return None if row is None else row["relkind"]


def compatibility_interface(
    connection: psycopg.Connection[dict[str, Any]],
    schema: str,
    relation: RelationSpec,
    physical: dict[str, Any],
) -> dict[str, Any] | None:
    interface = connection.execute(
        """
        SELECT c.oid::bigint AS oid, c.relkind,
               pg_get_userbyid(c.relowner) AS owner
        FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relname = %s
        """,
        (schema, relation.name),
    ).fetchone()
    if interface is None or interface["relkind"] != "v":
        return None
    columns = connection.execute(
        """
        SELECT a.attnum AS position, a.attname AS name,
               format_type(a.atttypid, a.atttypmod) AS data_type
        FROM pg_catalog.pg_attribute AS a
        WHERE a.attrelid = %s::oid AND a.attnum > 0 AND NOT a.attisdropped
        ORDER BY a.attnum
        """,
        (interface["oid"],),
    ).fetchall()
    grants = connection.execute(
        """
        SELECT grantee, privilege_type, is_grantable
        FROM information_schema.role_table_grants
        WHERE table_schema = %s AND table_name = %s
        ORDER BY grantee, privilege_type
        """,
        (schema, relation.name),
    ).fetchall()
    physical_columns = [
        {
            "position": column["position"],
            "name": column["name"],
            "data_type": column["data_type"],
        }
        for column in physical["columns"]
    ]
    return {
        **interface,
        "schema": schema,
        "columns": columns,
        "columns_match_physical": columns == physical_columns,
        "grants": grants,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--dbname")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    contract_path = args.contract or default_contract_path(root)
    contract = load_contract(contract_path)
    schema_sql = root / "rsc" / "sql" / "cses_schema_v1.sql"
    migration_sql = root / "rsc" / "sql" / "cses_public_to_functional_v1.sql"
    output = args.output or root / "data" / "processing" / "cses" / "migration_dry_run_v1.json"
    if not output.is_absolute():
        output = root / output

    connection_args: dict[str, object] = {"dbname": args.dbname or contract.database}
    if args.host:
        connection_args.update(host=args.host, port=args.port)
    if args.user:
        connection_args["user"] = args.user

    with psycopg.connect(**connection_args, row_factory=dict_row) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            database = connection.execute(
                """
                SELECT current_database() AS database,
                       current_user AS current_user,
                       current_setting('transaction_read_only') AS transaction_read_only,
                       current_setting('server_version') AS server_version,
                       has_database_privilege(current_user, current_database(), 'CREATE') AS can_create_schema,
                       has_schema_privilege(current_user, 'public', 'CREATE') AS can_create_public_object
                """
            ).fetchone()
            existing_schemas = [
                row["schema_name"]
                for row in connection.execute(
                    """
                    SELECT schema_name
                    FROM information_schema.schemata
                    WHERE schema_name = ANY(%s)
                    ORDER BY schema_name
                    """,
                    (sorted(contract.functional_schemas.values()),),
                ).fetchall()
            ]
            existing_roles = {
                row["rolname"]
                for row in connection.execute(
                    "SELECT rolname FROM pg_catalog.pg_roles WHERE rolname = ANY(%s) ORDER BY rolname",
                    (list(contract.reader_roles),),
                ).fetchall()
            }

            objects = []
            mixed_layout = False
            for relation in contract.relations:
                source_kind = relation_kind(connection, contract.source_schema, relation.name)
                target_kind = relation_kind(connection, relation.target_schema, relation.name)
                if source_kind in {"r", "p"} and target_kind is None:
                    physical_schema = contract.source_schema
                    state = "public_physical"
                elif source_kind == "v" and target_kind in {"r", "p"}:
                    physical_schema = relation.target_schema
                    state = "functional_physical"
                else:
                    physical_schema = contract.source_schema
                    state = "invalid_or_mixed"
                    mixed_layout = True
                metadata = relation_metadata(connection, physical_schema, relation)
                audit = key_audit(connection, physical_schema, relation) if metadata else None
                interface = (
                    compatibility_interface(connection, contract.compatibility_schema, relation, metadata)
                    if metadata and source_kind == "v"
                    else None
                )
                objects.append(
                    {
                        "contract": {
                            "name": relation.name,
                            "family": relation.family,
                            "source_schema": contract.source_schema,
                            "target_schema": relation.target_schema,
                        },
                        "layout_state": state,
                        "source_kind": source_kind,
                        "target_kind": target_kind,
                        "physical": metadata,
                        "compatibility_interface": interface,
                        "natural_key_audit": audit,
                    }
                )

            planned_names = [relation.name for relation in contract.relations]
            protected_public = connection.execute(
                """
                SELECT c.relname AS name, c.oid::bigint AS oid, c.relkind AS kind
                FROM pg_catalog.pg_class AS c
                JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = %s
                  AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
                  AND NOT (c.relname = ANY(%s))
                ORDER BY c.relname
                """,
                (contract.source_schema, planned_names),
            ).fetchall()
            out_of_scope_cses = [row for row in protected_public if "CSES" in row["name"] or "cses" in row["name"]]

    public_layout = all(item["layout_state"] == "public_physical" for item in objects)
    functional_layout = all(item["layout_state"] == "functional_physical" for item in objects)
    all_keys_ready = all(
        item["natural_key_audit"] is None or item["natural_key_audit"]["primary_key_candidate_ready"]
        for item in objects
    )
    all_dependents_clear = all(
        not [
            dependent
            for dependent in item["physical"]["dependent_views"]
            if not (
                dependent["schema"] == contract.compatibility_schema
                and dependent["name"] == item["contract"]["name"]
                and dependent["kind"] == "v"
            )
        ]
        for item in objects
        if item["physical"]
    )
    all_reader_grants_present = all(
        role in {grant["grantee"] for grant in item["physical"]["grants"] if grant["privilege_type"] == "SELECT"}
        for item in objects
        if item["physical"]
        for role in contract.reader_roles
    )
    unexpected_nonowner_grants = [
        {
            "relation": item["contract"]["name"],
            **grant,
        }
        for item in objects
        if item["physical"]
        for grant in item["physical"]["grants"]
        if grant["grantee"] != item["physical"]["owner"]
        and (grant["grantee"] not in contract.reader_roles or grant["privilege_type"] != "SELECT")
    ]
    owners = sorted({item["physical"]["owner"] for item in objects if item["physical"]})
    compatibility_interfaces_valid = public_layout or all(
        item["compatibility_interface"] is not None
        and item["compatibility_interface"]["columns_match_physical"]
        and all(
            role
            in {
                grant["grantee"]
                for grant in item["compatibility_interface"]["grants"]
                if grant["privilege_type"] == "SELECT"
            }
            for role in contract.reader_roles
        )
        for item in objects
    )
    checks = {
        "database_name_matches": database["database"] == contract.database,
        "transaction_is_read_only": database["transaction_read_only"] == "on",
        "layout_is_consistent": not mixed_layout and (public_layout or functional_layout),
        "all_natural_keys_are_unique_and_nonnull": all_keys_ready,
        "no_unplanned_dependent_postgresql_views": all_dependents_clear,
        "all_reader_roles_exist": existing_roles == set(contract.reader_roles),
        "all_current_reader_grants_are_present": all_reader_grants_present,
        "no_unconfigured_nonowner_grants": not unexpected_nonowner_grants,
        "compatibility_interfaces_match_physical_relations": compatibility_interfaces_valid,
        "executor_can_create_schemas": database["can_create_schema"],
        "executor_can_create_public_objects": database["can_create_public_object"],
        "all_physical_relations_owned_by_executor": owners == [database["current_user"]],
        "schema_ddl_exists": schema_sql.is_file(),
        "migration_sql_exists": migration_sql.is_file(),
    }
    layout_observations = {
        "all_source_relations_are_base_tables": public_layout,
        "all_target_relations_are_absent": public_layout,
        "all_source_relations_are_compatibility_views": functional_layout,
        "all_target_relations_are_base_tables": functional_layout,
    }
    migration_ready = all(checks.values()) and public_layout
    post_migration_valid = all(checks.values()) and functional_layout
    report = {
        "schema_version": 1,
        "migration_name": contract.migration_name,
        "database_mutated": False,
        "database": database,
        "contract": {
            "path": "rsc/specs/cses_schema_v1.json",
            "sha256": sha256_file(contract_path),
            "relation_count": len(contract.relations),
            "reader_roles": list(contract.reader_roles),
            "functional_schemas": contract.functional_schemas,
        },
        "sql_artifacts": {
            "schema_ddl": {
                "path": "rsc/sql/cses_schema_v1.sql",
                "sha256": sha256_file(schema_sql) if schema_sql.is_file() else None,
            },
            "object_migration": {
                "path": "rsc/sql/cses_public_to_functional_v1.sql",
                "sha256": sha256_file(migration_sql) if migration_sql.is_file() else None,
            },
        },
        "layout": "public" if public_layout else "functional" if functional_layout else "mixed_or_invalid",
        "existing_functional_schemas": existing_schemas,
        "physical_owners": owners,
        "unexpected_nonowner_grants": unexpected_nonowner_grants,
        "objects": objects,
        "protected_public_relations": protected_public,
        "protected_public_relation_count": len(protected_public),
        "out_of_scope_cses_named_relations": out_of_scope_cses,
        "checks": checks,
        "layout_observations": layout_observations,
        "migration_ready": migration_ready,
        "post_migration_valid": post_migration_valid,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"dry_run={output.relative_to(root)}")
    print(f"layout={report['layout']} objects={len(objects)} protected_public={len(protected_public)}")
    print(f"key_candidates_ready={all_keys_ready} dependent_views_clear={all_dependents_clear}")
    print(f"database_mutated=False migration_ready={migration_ready}")
    if not (migration_ready or post_migration_valid):
        failed = [name for name, passed in checks.items() if not passed]
        raise SystemExit(f"Migration contract validation failed: {failed}")


if __name__ == "__main__":
    main()
