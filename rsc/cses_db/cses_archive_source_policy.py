#!/usr/bin/env python3
"""Explicit archive-first discovery without modifying fingerprinted legacy code.

Only byte-identical extraction aliases at matching container/member paths are
excluded. Independent files and changed copies remain visible. This adapter
changes source discovery, never source bytes, database state or acceptance gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

import inventory_cses_archives as inventory

LEGACY_DISCOVER = inventory.discover_sources


def identity(source):
    return source.root_file.absolute(), source.archive_members


def extraction_aliases(source, raw):
    """Enumerate paths created by extract-here and extract-to-container-folder.

    Also identify standalone nested ZIPs with the same remaining member chain.
    No path traversal, guessed basename match or cross-wave content-only merge.
    """
    bases = {source.root_file.parent, source.root_file.with_suffix("")}
    for index, member in enumerate(source.archive_members):
        posix = PurePosixPath(member)
        if posix.is_absolute() or ".." in posix.parts:
            return
        paths = {base.joinpath(*posix.parts).absolute() for base in bases}
        paths = {p for p in paths if p.is_relative_to(raw.absolute())}
        remaining = source.archive_members[index + 1:]
        for path in sorted(paths):
            yield path, remaining
        bases = {p for path in paths for p in (path.parent, path.with_suffix(""))}


def resolve_sources(root, sources):
    root = Path(root).absolute()
    raw = root / "data/raw"
    records = {identity(s): s for s in sources}
    removed = set()
    hashes = {}
    aliases, changed, noise = [], [], []

    def fingerprint(source):
        key = identity(source)
        if key not in hashes:
            if source.archive_members:
                hashes[key] = hashlib.sha256(source.read_bytes()).hexdigest()
            else:
                with source.root_file.open("rb") as stream:
                    hashes[key] = hashlib.file_digest(stream, "sha256").hexdigest()
        return hashes[key]

    for key, source in records.items():
        if inventory.is_noise(source.root_file.as_posix()) or any(inventory.is_noise(m) for m in source.archive_members):
            removed.add(key)
            noise.append(source.display_name(root))
    ordered = sorted(records.values(), key=lambda s: (
        len(s.root_file.relative_to(raw).parts), s.display_name(root)))
    for source in ordered:
        if identity(source) in removed or not source.archive_members:
            continue
        for alias_key in extraction_aliases(source, raw):
            if alias_key == identity(source) or alias_key not in records or alias_key in removed:
                continue
            alias = records[alias_key]
            pair = {"authoritative": source.display_name(root), "extracted": alias.display_name(root)}
            if fingerprint(source) == fingerprint(alias):
                removed.add(alias_key)
                aliases.append({**pair, "sha256": fingerprint(source)})
            else:
                changed.append(pair)
    retained = sorted((s for key, s in records.items() if key not in removed), key=lambda s: s.display_name(root))
    report = {"policy": "archive-first-byte-identical-extraction-aliases-v1", "discovered": len(records),
              "retained": len(retained), "identical_aliases": aliases, "changed_copies_retained": changed,
              "macos_noise_excluded": sorted(noise), "source_files_mutated": False}
    return retained, report


def discover_sources(root):
    return resolve_sources(root, LEGACY_DISCOVER(root))[0]


@contextmanager
def archive_source_policy():
    """Opt-in, single-threaded adapter for legacy modules; restore on every exit.

    Tests use this same production entry point rather than bypassing assertions.
    Frozen on-disk implementations and their hashes are left untouched.
    """
    if inventory.discover_sources is discover_sources:
        yield
        return
    module_dir = Path(__file__).resolve().parent

    def local_modules():
        return [module for module in list(sys.modules.values())
                if getattr(module, "__file__", None)
                and Path(module.__file__).resolve().parent == module_dir
                and module is not sys.modules[__name__]]

    for module in local_modules():
        if getattr(module, "discover_sources", None) is LEGACY_DISCOVER:
            module.discover_sources = discover_sources
    try:
        yield
    finally:
        # Includes modules imported while the policy was enabled.
        for module in local_modules():
            if getattr(module, "discover_sources", None) is discover_sources:
                module.discover_sources = LEGACY_DISCOVER


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", action="store_true", help="Read-only discovery summary; do not run a legacy script")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2],
                        help="Audit root; for a legacy script place its --root after the script name")
    parser.add_argument("script", nargs="?", help="Existing Python script basename in rsc/cses_db")
    parser.add_argument("script_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.audit:
        if args.script:
            parser.error("--audit cannot execute a script")
        _, report = resolve_sources(args.root, LEGACY_DISCOVER(args.root))
        print(json.dumps({k: len(v) if isinstance(v, list) else v for k, v in report.items()}))
        return
    script = Path(__file__).resolve().parent / (args.script or "")
    if not args.script or Path(args.script).name != args.script or script.suffix != ".py" or not script.is_file():
        parser.error("Specify an existing script basename, or --audit")
    if script.resolve() == Path(__file__).resolve():
        parser.error("Cannot launch the policy runner recursively")
    old_argv = sys.argv
    try:
        sys.argv = [str(script), *args.script_args]
        with archive_source_policy():
            runpy.run_path(str(script), run_name="__main__")
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    main()
