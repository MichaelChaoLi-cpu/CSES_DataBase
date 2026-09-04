#!/usr/bin/env python3
"""Export the deterministic, read-only CSES database lineage graph."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from cses_baseline_metadata import connection_arguments
from cses_lineage_graph import export_lineage_graph

EXPORTER_PATHS = (
    "rsc/cses_db/cses_lineage_graph.py",
    "rsc/cses_db/export_cses_lineage_graph.py",
)


def exporter_git_revision(root: Path) -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", *EXPORTER_PATHS],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    revision = result.stdout.strip()
    if not revision:
        raise RuntimeError("CSES lineage exporter code is not committed in Git")
    return revision


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--dbname", default="mda")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--overview", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    output = args.output or root / "data" / "lineage" / "cses_lineage_graph_v1.json"
    overview = args.overview or root / "data" / "lineage" / "cses_lineage_overview_v1.mmd"
    output = output if output.is_absolute() else root / output
    overview = overview if overview.is_absolute() else root / overview
    result = export_lineage_graph(
        connection_arguments(args.dbname, args.host, args.port, args.user),
        output,
        overview,
        exporter_git_revision(root),
    )
    result["output_file"] = str(output.relative_to(root))
    result["overview_file"] = str(overview.relative_to(root))
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
