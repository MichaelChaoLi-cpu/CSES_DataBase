#!/usr/bin/env python3
"""Render the deterministic, reviewable CSES object-migration SQL."""

from __future__ import annotations

import argparse
from pathlib import Path

from cses_schema_contract import SchemaContract, default_contract_path, load_contract, quoted_identifier


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_migration_sql(contract: SchemaContract, schema_ddl: str) -> str:
    relation_values = ",\n".join(
        f"    ({position}, {_literal(relation.name)}, {_literal(relation.family)}, {_literal(relation.target_schema)})"
        for position, relation in enumerate(contract.relations, start=1)
    )
    grant_statements = []
    for role in contract.reader_roles:
        quoted_role = quoted_identifier(role)
        for schema in contract.functional_schemas.values():
            quoted_schema = quoted_identifier(schema)
            grant_statements.extend(
                [
                    f"GRANT USAGE ON SCHEMA {quoted_schema} TO {quoted_role};",
                    f"GRANT SELECT ON ALL TABLES IN SCHEMA {quoted_schema} TO {quoted_role};",
                    (f"ALTER DEFAULT PRIVILEGES IN SCHEMA {quoted_schema} GRANT SELECT ON TABLES TO {quoted_role};"),
                ]
            )
    compatibility_grants = "\n".join(
        f"GRANT SELECT ON {quoted_identifier(contract.compatibility_schema)}."
        f"{quoted_identifier(relation.name)} TO {quoted_identifier(role)};"
        for relation in contract.relations
        for role in contract.reader_roles
    )

    return f"""-- Generated from rsc/specs/cses_schema_v1.json. Do not edit by hand.
-- Execute only after a verified backup and explicit database-write approval.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '0';
SELECT pg_advisory_xact_lock(hashtext({_literal(contract.migration_name)}));

-- Begin rsc/sql/cses_schema_v1.sql.
{schema_ddl.rstrip()}
-- End rsc/sql/cses_schema_v1.sql.

CREATE TEMPORARY TABLE cses_migration_plan (
    sequence_number integer PRIMARY KEY,
    relation_name text NOT NULL UNIQUE,
    object_family text NOT NULL,
    target_schema text NOT NULL
) ON COMMIT DROP;

INSERT INTO cses_migration_plan (sequence_number, relation_name, object_family, target_schema)
VALUES
{relation_values};

CREATE TEMPORARY TABLE cses_object_identity_before ON COMMIT DROP AS
SELECT
    plan.relation_name,
    plan.target_schema,
    COALESCE(target.oid, source.oid)::bigint AS physical_oid
FROM cses_migration_plan AS plan
LEFT JOIN pg_catalog.pg_namespace AS source_ns
    ON source_ns.nspname = {_literal(contract.source_schema)}
LEFT JOIN pg_catalog.pg_class AS source
    ON source.relnamespace = source_ns.oid
   AND source.relname = plan.relation_name
   AND source.relkind IN ('r', 'p')
LEFT JOIN pg_catalog.pg_namespace AS target_ns
    ON target_ns.nspname = plan.target_schema
LEFT JOIN pg_catalog.pg_class AS target
    ON target.relnamespace = target_ns.oid
   AND target.relname = plan.relation_name
   AND target.relkind IN ('r', 'p');

DO $precondition$
DECLARE
    invalid_count integer;
    plan_count integer;
    public_layout_count integer;
    functional_layout_count integer;
BEGIN
    SELECT count(*) INTO invalid_count
    FROM cses_object_identity_before
    WHERE physical_oid IS NULL;
    IF invalid_count <> 0 THEN
        RAISE EXCEPTION 'CSES migration precondition failed: % physical relations are missing', invalid_count;
    END IF;

    SELECT count(*) INTO invalid_count
    FROM cses_migration_plan AS plan
    LEFT JOIN pg_catalog.pg_namespace AS source_ns
        ON source_ns.nspname = {_literal(contract.source_schema)}
    LEFT JOIN pg_catalog.pg_class AS source
        ON source.relnamespace = source_ns.oid AND source.relname = plan.relation_name
    LEFT JOIN pg_catalog.pg_namespace AS target_ns
        ON target_ns.nspname = plan.target_schema
    LEFT JOIN pg_catalog.pg_class AS target
        ON target.relnamespace = target_ns.oid AND target.relname = plan.relation_name
    WHERE NOT (
        (source.relkind IN ('r', 'p') AND target.oid IS NULL)
        OR (source.relkind = 'v' AND target.relkind IN ('r', 'p'))
    );
    IF invalid_count <> 0 THEN
        RAISE EXCEPTION 'CSES migration refuses a missing, conflicting, or mixed layout (% objects)', invalid_count;
    END IF;

    SELECT count(*) INTO plan_count FROM cses_migration_plan;
    SELECT
        count(*) FILTER (WHERE source.relkind IN ('r', 'p') AND target.oid IS NULL),
        count(*) FILTER (WHERE source.relkind = 'v' AND target.relkind IN ('r', 'p'))
    INTO public_layout_count, functional_layout_count
    FROM cses_migration_plan AS plan
    LEFT JOIN pg_catalog.pg_namespace AS source_ns
        ON source_ns.nspname = {_literal(contract.source_schema)}
    LEFT JOIN pg_catalog.pg_class AS source
        ON source.relnamespace = source_ns.oid AND source.relname = plan.relation_name
    LEFT JOIN pg_catalog.pg_namespace AS target_ns
        ON target_ns.nspname = plan.target_schema
    LEFT JOIN pg_catalog.pg_class AS target
        ON target.relnamespace = target_ns.oid AND target.relname = plan.relation_name;
    IF NOT (
        (public_layout_count = plan_count AND functional_layout_count = 0)
        OR (public_layout_count = 0 AND functional_layout_count = plan_count)
    ) THEN
        RAISE EXCEPTION
            'CSES migration refuses a mixed layout: public %, functional %, planned %',
            public_layout_count, functional_layout_count, plan_count;
    END IF;
END
$precondition$;

CREATE TEMPORARY TABLE cses_protected_public_before ON COMMIT DROP AS
SELECT c.relname, c.oid::bigint AS relation_oid, c.relkind
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = {_literal(contract.source_schema)}
  AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND NOT EXISTS (
      SELECT 1 FROM cses_migration_plan AS plan WHERE plan.relation_name = c.relname
  );

DO $move$
DECLARE
    item record;
    source_kind "char";
    target_kind "char";
BEGIN
    FOR item IN SELECT * FROM cses_migration_plan ORDER BY sequence_number LOOP
        SELECT c.relkind INTO source_kind
        FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = {_literal(contract.source_schema)} AND c.relname = item.relation_name;

        SELECT c.relkind INTO target_kind
        FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = item.target_schema AND c.relname = item.relation_name;

        IF source_kind IN ('r', 'p') AND target_kind IS NULL THEN
            EXECUTE format(
                'ALTER TABLE %I.%I SET SCHEMA %I',
                {_literal(contract.source_schema)}, item.relation_name, item.target_schema
            );
        ELSIF source_kind = 'v' AND target_kind IN ('r', 'p') THEN
            NULL;
        ELSE
            RAISE EXCEPTION 'Unexpected state for %: source kind %, target kind %',
                item.relation_name, source_kind, target_kind;
        END IF;
    END LOOP;
END
$move$;

DO $views$
DECLARE
    item record;
    target_owner text;
BEGIN
    FOR item IN SELECT * FROM cses_migration_plan ORDER BY sequence_number LOOP
        EXECUTE format(
            'CREATE OR REPLACE VIEW %I.%I AS SELECT * FROM %I.%I',
            {_literal(contract.compatibility_schema)}, item.relation_name,
            item.target_schema, item.relation_name
        );
        SELECT pg_get_userbyid(c.relowner) INTO target_owner
        FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = item.target_schema AND c.relname = item.relation_name;
        EXECUTE format(
            'ALTER VIEW %I.%I OWNER TO %I',
            {_literal(contract.compatibility_schema)}, item.relation_name, target_owner
        );
        EXECUTE format(
            'COMMENT ON VIEW %I.%I IS %L',
            {_literal(contract.compatibility_schema)}, item.relation_name,
            'Compatibility view; authoritative relation is ' || item.target_schema || '.' || item.relation_name
        );
    END LOOP;
END
$views$;

{compatibility_grants}

{chr(10).join(grant_statements)}

DO $postcondition$
DECLARE
    invalid_count integer;
BEGIN
    SELECT count(*) INTO invalid_count
    FROM cses_object_identity_before AS before
    JOIN cses_migration_plan AS plan USING (relation_name, target_schema)
    LEFT JOIN pg_catalog.pg_namespace AS target_ns ON target_ns.nspname = plan.target_schema
    LEFT JOIN pg_catalog.pg_class AS target
        ON target.relnamespace = target_ns.oid AND target.relname = plan.relation_name
    LEFT JOIN pg_catalog.pg_namespace AS compatibility_ns
        ON compatibility_ns.nspname = {_literal(contract.compatibility_schema)}
    LEFT JOIN pg_catalog.pg_class AS compatibility
        ON compatibility.relnamespace = compatibility_ns.oid
       AND compatibility.relname = plan.relation_name
    WHERE target.relkind NOT IN ('r', 'p')
       OR target.oid::bigint IS DISTINCT FROM before.physical_oid
       OR compatibility.relkind IS DISTINCT FROM 'v'::"char";
    IF invalid_count <> 0 THEN
        RAISE EXCEPTION 'CSES migration postcondition failed for % objects', invalid_count;
    END IF;

    SELECT count(*) INTO invalid_count
    FROM (
        (SELECT relname, relation_oid, relkind FROM cses_protected_public_before
         EXCEPT
         SELECT c.relname, c.oid::bigint, c.relkind
         FROM pg_catalog.pg_class AS c
         JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = {_literal(contract.source_schema)}
           AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
           AND NOT EXISTS (
               SELECT 1 FROM cses_migration_plan AS plan WHERE plan.relation_name = c.relname
           ))
        UNION ALL
        (SELECT c.relname, c.oid::bigint, c.relkind
         FROM pg_catalog.pg_class AS c
         JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = {_literal(contract.source_schema)}
           AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
           AND NOT EXISTS (
               SELECT 1 FROM cses_migration_plan AS plan WHERE plan.relation_name = c.relname
           )
         EXCEPT
         SELECT relname, relation_oid, relkind FROM cses_protected_public_before)
    ) AS difference;
    IF invalid_count <> 0 THEN
        RAISE EXCEPTION 'A protected public relation changed; rolling back';
    END IF;
END
$postcondition$;

COMMIT;
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    contract_path = args.contract or default_contract_path(root)
    output = args.output or root / "rsc" / "sql" / "cses_public_to_functional_v1.sql"
    schema_ddl_path = root / "rsc" / "sql" / "cses_schema_v1.sql"
    rendered = render_migration_sql(load_contract(contract_path), schema_ddl_path.read_text(encoding="utf-8"))
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"Generated migration SQL is stale: {output}")
        print(f"migration_sql_current={output.relative_to(root)}")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(f"migration_sql={output.relative_to(root)}")


if __name__ == "__main__":
    main()
