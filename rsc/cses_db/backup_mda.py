#!/usr/bin/env python3
"""Create and verify a uniquely named external custom-format mda backup."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import psycopg


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command_version(command: str) -> str:
    return subprocess.run(
        [command, "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--dbname", default="mda")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user")
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--confirm-backup", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.confirm_backup:
        raise SystemExit("Refusing external backup without --confirm-backup")

    root = args.root.resolve()
    backup_dir = args.backup_dir.resolve()
    if not backup_dir.is_dir():
        raise FileNotFoundError(backup_dir)
    output = args.output or root / "data" / "processing" / "cses" / "mda_backup_verification_v1.json"
    started_at = datetime.now(timezone.utc)
    date_label = started_at.astimezone().strftime("%Y%m%d-%H%M%S")
    file_descriptor, raw_path = tempfile.mkstemp(
        prefix=f"mda_pre_CSES_schema_v1_{date_label}_",
        suffix=".dump",
        dir=backup_dir,
    )
    os.close(file_descriptor)
    backup_path = Path(raw_path)
    backup_path.chmod(0o600)
    print(f"backup_path={backup_path}", flush=True)

    connection_args: dict[str, object] = {"dbname": args.dbname}
    pg_connection_args = ["-d", args.dbname]
    if args.host:
        connection_args.update(host=args.host, port=args.port)
        pg_connection_args.extend(["-h", args.host, "-p", str(args.port)])
    if args.user:
        connection_args["user"] = args.user
        pg_connection_args.extend(["-U", args.user])

    with psycopg.connect(**connection_args) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            database_snapshot = connection.execute(
                """
                SELECT current_database(), pg_database_size(current_database()),
                       current_setting('server_version'),
                       current_setting('transaction_read_only')
                """
            ).fetchone()

    dump_command = [
        "pg_dump",
        *pg_connection_args,
        "--format=custom",
        "--compress=6",
        f"--file={backup_path}",
    ]
    subprocess.run(dump_command, check=True)
    backup_path.chmod(0o600)
    if backup_path.stat().st_size == 0:
        raise RuntimeError(f"Backup is empty: {backup_path}")

    toc = subprocess.run(
        ["pg_restore", "--list", str(backup_path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    subprocess.run(
        ["pg_restore", "--file=/dev/null", str(backup_path)],
        check=True,
    )
    completed_at = datetime.now(timezone.utc)
    mode = stat.S_IMODE(backup_path.stat().st_mode)
    report = {
        "schema_version": 1,
        "database_mutated": False,
        "database": {
            "name": database_snapshot[0],
            "size_bytes_at_start": database_snapshot[1],
            "server_version": database_snapshot[2],
            "inspection_transaction_read_only": database_snapshot[3] == "on",
        },
        "backup": {
            "path": str(backup_path),
            "filename": backup_path.name,
            "size_bytes": backup_path.stat().st_size,
            "sha256": sha256_file(backup_path),
            "mode": oct(mode),
            "custom_format": True,
        },
        "verification": {
            "pg_restore_list_passed": True,
            "pg_restore_full_decompression_passed": True,
            "toc_entry_count": sum(bool(line.strip()) and not line.startswith(";") for line in toc.splitlines()),
        },
        "tool_versions": {
            "pg_dump": command_version("pg_dump"),
            "pg_restore": command_version("pg_restore"),
        },
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_seconds": round((completed_at - started_at).total_seconds(), 3),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"backup_size_bytes={report['backup']['size_bytes']}")
    print(f"backup_sha256={report['backup']['sha256']}")
    print(f"backup_mode={report['backup']['mode']}")
    print(f"toc_entry_count={report['verification']['toc_entry_count']}")
    print("pg_restore_full_decompression_passed=True")
    print(f"verification={output.relative_to(root)}")


if __name__ == "__main__":
    main()
