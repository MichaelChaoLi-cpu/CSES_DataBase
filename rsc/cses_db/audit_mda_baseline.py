#!/usr/bin/env python3
"""Compare local CSES release structure with an existing PostgreSQL baseline.

The database transaction is forced read-only. This audit checks relation presence, exact row
counts, ordered column names, comments, and index definitions; it never publishes or replaces data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import psycopg
import pyarrow.parquet as pq
from cses_hh_hl_common import snake_case
from cses_survey_date_contract import ACTUAL_DATE_COLUMNS
from psycopg import sql

TABLE_FILES = {
    "final_HH_CSES": "final_HH_CSES.parquet",
    "final_HL_CSES": "final_HL_CSES.parquet",
    "final_ED_CSES": "final_ED_CSES.parquet",
    "final_HO_CSES": "final_HO_CSES.parquet",
    "final_EC_CSES": "final_EC_CSES.parquet",
    "final_VL_CSES": "final_VL_CSES.parquet",
    "final_SURVEY_DATE_CSES": "final_SURVEY_DATE_CSES.parquet",
}


def expected_columns(path: Path, table: str) -> list[str]:
    columns = [snake_case(name) for name in pq.ParquetFile(path).schema.names]
    if table == "final_HH_CSES":
        columns.extend(ACTUAL_DATE_COLUMNS)
    return columns


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--dbname", default="mda")
    parser.add_argument("--schema", default="public")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    local_dir = root / "data" / "processing" / "cses"
    connection_args: dict[str, object] = {"dbname": args.dbname}
    if args.host:
        connection_args.update(host=args.host, port=args.port)

    results = []
    with psycopg.connect(**connection_args) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            read_only = connection.execute("SELECT current_setting('transaction_read_only')").fetchone()[0]
            if read_only != "on":
                raise RuntimeError("Database audit transaction is not read-only")

            for table, filename in TABLE_FILES.items():
                local_path = local_dir / filename
                if not local_path.exists():
                    raise FileNotFoundError(local_path)
                local_metadata = pq.ParquetFile(local_path).metadata

                relation_exists = connection.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = %s AND c.relname = %s
                          AND c.relkind IN ('r', 'p', 'v', 'm')
                    )
                    """,
                    (args.schema, table),
                ).fetchone()[0]
                if not relation_exists:
                    results.append({"table": table, "relation_exists": False})
                    continue

                row_count = connection.execute(
                    sql.SQL("SELECT count(*) FROM {}.{}").format(sql.Identifier(args.schema), sql.Identifier(table))
                ).fetchone()[0]
                columns = [
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = %s AND table_name = %s
                        ORDER BY ordinal_position
                        """,
                        (args.schema, table),
                    )
                ]
                indexes = [
                    {"name": row[0], "definition": row[1]}
                    for row in connection.execute(
                        """
                        SELECT indexname, indexdef
                        FROM pg_indexes
                        WHERE schemaname = %s AND tablename = %s
                        ORDER BY indexname
                        """,
                        (args.schema, table),
                    )
                ]
                qualified_name = (
                    sql.SQL("{}.{}").format(sql.Identifier(args.schema), sql.Identifier(table)).as_string(connection)
                )
                comment = connection.execute(
                    "SELECT obj_description(to_regclass(%s))",
                    (qualified_name,),
                ).fetchone()[0]
                expected = expected_columns(local_path, table)
                results.append(
                    {
                        "table": table,
                        "relation_exists": True,
                        "local_rows": local_metadata.num_rows,
                        "database_rows": row_count,
                        "row_count_match": local_metadata.num_rows == row_count,
                        "local_expected_columns": expected,
                        "database_columns": columns,
                        "ordered_columns_match": expected == columns,
                        "table_comment_present": bool(comment),
                        "indexes": indexes,
                    }
                )

    report = {
        "schema_version": 1,
        "database": args.dbname,
        "schema": args.schema,
        "transaction_read_only": True,
        "tables": results,
        "all_relations_exist": all(result["relation_exists"] for result in results),
        "all_row_counts_match": all(result.get("row_count_match", False) for result in results),
        "all_ordered_columns_match": all(result.get("ordered_columns_match", False) for result in results),
    }
    output = args.output or local_dir / "mda_baseline_audit.json"
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"audit={output.relative_to(root)} relations={report['all_relations_exist']} "
        f"rows={report['all_row_counts_match']} columns={report['all_ordered_columns_match']}"
    )
    for result in results:
        print(
            f"{result['table']}: exists={result['relation_exists']} "
            f"rows={result.get('row_count_match')} columns={result.get('ordered_columns_match')}"
        )
    if not (report["all_relations_exist"] and report["all_row_counts_match"] and report["all_ordered_columns_match"]):
        raise SystemExit("Local release structure differs from the PostgreSQL baseline")


if __name__ == "__main__":
    main()
