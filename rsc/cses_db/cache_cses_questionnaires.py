#!/usr/bin/env python3
"""Materialize immutable, wave-indexed questionnaire sources; verify without archives.

Original documents are copied byte-for-byte, not authored or converted. Literal
cell extracts are reused from the fingerprinted historical all-sheet extraction.
Use the bundled artifact Python runtime for this command.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import re
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from organize_cses_questionnaires import WAVES, coordinate, encoded

BASE = "data/processing/cses/questionnaire_alignment_v1"
DEFAULT = "data/processed/cses_questionnaires/v1"
FORM_ROLES = {
    "household_questionnaire",
    "village_questionnaire",
    "household_diary",
    "household_listing",
    "forms_bundle",
    "questionnaire_bundle",
}
WAVE_NOTES = {
    "2004": "Multiple original versions retained; registered evidence is not blanket version precedence.",
    "2007": "Village form available; no household questionnaire located in supplied sources.",
    "2009": "Alternate household, village and diary versions retained separately.",
    "2011-12": "Distributed 2011 household form; not independently verified as a separate 2012 form.",
    "2013": "Household form recovered from the nested CSES 2013 archive.",
    "2014": "Household form is a draft with WFP comments; provisional evidence.",
    "2016": "English household and village forms available.",
    "2017": "No questionnaire located in supplied sources. Do not substitute the 2016 form.",
    "2019": "Original image-based DOCX bundle available; question transcription remains pending.",
    "2021": "English and Khmer household forms retained independently; macro-enabled originals are not executed.",
}


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def file_sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_path(base, relative):
    """All manifest paths are relative and contained, including through symlinks."""
    path = PurePosixPath(relative)
    require(not path.is_absolute() and ".." not in path.parts, f"Unsafe path: {relative}")
    target = base.joinpath(*path.parts)
    require(target.resolve().is_relative_to(base.resolve()), f"Escaping path: {relative}")
    return target


def put(path, payload):
    """Exclusive creation: never replace a different pre-existing artifact."""
    if not isinstance(payload, bytes):
        payload = payload.encode() if isinstance(payload, str) else encoded(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        require(path.read_bytes() == payload, f"Refusing differing overwrite: {path}")
    return sha(payload)


def add_artifact(base, files, relative, payload):
    digest = put(safe_path(base, relative), payload)
    files[relative] = digest
    return relative


def source_id(source_file):
    return sha(source_file.encode())[:16]


def leaf_name(name):
    # Retain readable original leaf names, without invisible controls or path syntax.
    name = PurePosixPath(name.replace("\\", "/")).name
    name = "".join(c for c in name if c.isprintable())
    return re.sub(r"[^\w. ()-]", "_", name).strip(". ") or "source"


def member_bytes(root, source_file):
    archive_path, *chain = source_file.split("::")
    require(chain, f"Expected archive-member source: {source_file}")
    payload = None
    for member in chain:
        with zipfile.ZipFile(safe_path(root, archive_path) if payload is None else io.BytesIO(payload)) as z:
            payload = z.read(member)
    return payload


def markdown_cell(value):
    return html.escape(str(value)).replace("|", "&#124;").replace("\n", "<br>")


def cells_markdown(source, sheets):
    lines = [
        f"# {leaf_name(source['source_file'])}",
        "",
        f"Wave: {source['survey_wave']}. Language: {source['language_code']}.",
        "",
        "Literal worksheet cells, not a reviewed list of distinct questions. "
        "Formula cells and image-only content are not transcribed.",
        "",
    ]
    for name, cells in sheets.items():
        lines.extend([f"## {markdown_cell(name)}", "", "| Cell | Literal value |", "| --- | --- |"])
        lines.extend(f"| {cell} | {markdown_cell(cells[cell])} |" for cell in sorted(cells, key=coordinate))
        lines.append("")
    return "\n".join(lines)


def verify_manifest(base):
    """Only local artifacts are opened; source archives need not be mounted."""
    manifest = json.loads((base / "manifest.json").read_text())
    for relative, expected in manifest["artifacts"].items():
        path = safe_path(base, relative)
        require(path.is_file() and file_sha(path) == expected, f"Cached artifact changed/missing: {relative}")
    return manifest


def cached_source(base, source_file):
    """Strict cache-only access; no silent archive fallback on corruption/missing files."""
    manifest = json.loads((base / "manifest.json").read_text())
    found = [s for s in manifest["sources"] if s["source_file"] == source_file]
    require(len(found) == 1, f"Expected one cached source: {source_file}")
    record = found[0]
    path = safe_path(base, record["local_path"])
    require(file_sha(path) == record["source_sha256"], f"Cached source changed: {path}")
    return path, record


def build(root, output):
    inventory_path = root / BASE / "source_inventory.json"
    cell_path = root / BASE / "source_cells.json"
    inventory = json.loads(inventory_path.read_text())
    require(file_sha(cell_path) == inventory["source_cells_sha256"], "Historical cell extract changed")
    cells = {s["source_file"]: s for s in json.loads(cell_path.read_text())}
    for relative, expected in inventory["archive_sha256"].items():
        require(file_sha(safe_path(root, relative)) == expected, f"Archive changed: {relative}")
    sources, artifacts = [], {}
    for source in sorted(inventory["sources"], key=lambda s: s["source_file"]):
        source = dict(source)
        payload = member_bytes(root, source["source_file"])
        require(sha(payload) == source["source_sha256"], f"Original member changed: {source['source_file']}")
        identity = source_id(source["source_file"])
        wave = source["survey_wave"]
        folder = "forms" if source["instrument_type"] in FORM_ROLES else "references"
        relative = f"{wave}/{folder}/{identity}/{leaf_name(source['source_file'])}"
        source.update(source_id=identity, local_path=relative, cells_path=None, text_path=None)
        add_artifact(output, artifacts, relative, payload)
        if source["source_file"] in cells:
            extract = cells[source["source_file"]]
            require(extract["source_sha256"] == sha(payload), "Cell/source fingerprint mismatch")
            source["cells_path"] = add_artifact(output, artifacts, f"{wave}/text/{identity}.json", extract)
            source["text_path"] = add_artifact(
                output, artifacts, f"{wave}/text/{identity}.md", cells_markdown(source, extract["sheets"])
            )
        sources.append(source)
    require(len({s["source_id"] for s in sources}) == len(sources), "Source identity collision")
    waves = []
    for wave in WAVES:
        selected = [s for s in sources if s["survey_wave"] == wave]
        forms = [s for s in selected if s["instrument_type"] in FORM_ROLES]
        status = {
            "survey_wave": wave,
            "original_files": len(selected),
            "form_files": len(forms),
            "literal_workbooks": sum(s["cells_path"] is not None for s in selected),
            "household_form_source_ids": [
                s["source_id"] for s in forms if s["instrument_type"] == "household_questionnaire"
            ],
            "note": WAVE_NOTES[wave],
        }
        waves.append(status)
        lines = [
            f"# CSES {wave} questionnaires",
            "",
            WAVE_NOTES[wave],
            "",
            "[All waves](../README.md)",
            "",
            "Registered status is historical provenance, not new approval for every section.",
            "",
        ]
        for folder in ("forms", "references"):
            lines.extend([f"## {folder.title()}", ""])
            items = [s for s in selected if (s["instrument_type"] in FORM_ROLES) == (folder == "forms")]
            if not items:
                lines.extend(["No located sources in this category.", ""])
            for s in items:
                original = quote(s["local_path"].split("/", 1)[1])
                lines.append(
                    f"- [{leaf_name(s['source_file'])}]({original}) — "
                    f"{s['instrument_type']}; {s['language_code']}; {s['documentation_status']}."
                )
                if s["text_path"]:
                    lines.append(f"  [Searchable cells](text/{s['source_id']}.md) · [JSON](text/{s['source_id']}.json)")
            lines.append("")
        add_artifact(output, artifacts, f"{wave}/README.md", "\n".join(lines))
    lines = [
        "# CSES questionnaire library",
        "",
        "Open a wave below. Originals are byte-identical copies. Routine access and verification "
        "do not read archives. All original variants and languages remain separate.",
        "",
        "No macros executed, OCR performed, questions approved or database objects changed.",
        "",
        "| Wave | Form files | Reference files | Searchable workbooks | Evidence limits |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for w in waves:
        lines.append(
            f"| [{w['survey_wave']}]({w['survey_wave']}/README.md) | {w['form_files']} | "
            f"{w['original_files'] - w['form_files']} | {w['literal_workbooks']} | {w['note']} |"
        )
    lines.extend(
        [
            "",
            "File counts include alternate versions; they are not counts of distinct instruments or questions.",
            "",
            "Use `manifest.json` for original archive/member chains, hashes, local paths and extraction status.",
            "",
        ]
    )
    add_artifact(output, artifacts, "README.md", "\n".join(lines))
    result = {
        "library_version": "cses-questionnaires-v1",
        "database_mutated": False,
        "source_archives_modified": False,
        "macros_executed": False,
        "archive_sha256": inventory["archive_sha256"],
        "sources": sources,
        "waves": waves,
        "artifacts": artifacts,
        "inventory_sha256": file_sha(inventory_path),
        "historical_cells_sha256": file_sha(cell_path),
        "literal_cell_basis": "Reused complete historical extracts pinned to identical original bytes.",
        "implementation_sha256": file_sha(Path(__file__)),
        "scope_counts": {
            "original_files": len(sources),
            "form_files": sum(s["instrument_type"] in FORM_ROLES for s in sources),
            "searchable_workbooks": len(cells),
            "waves": len(waves),
        },
        "role_counts": dict(sorted(Counter(s["instrument_type"] for s in sources).items())),
    }
    put(output / "manifest.json", result)
    verify_manifest(output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["build", "verify"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.root / DEFAULT
    result = build(args.root, output) if args.mode == "build" else verify_manifest(output)
    print(json.dumps(result["scope_counts"], sort_keys=True))


if __name__ == "__main__":
    main()
