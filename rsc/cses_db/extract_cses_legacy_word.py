#!/usr/bin/env python3
"""Cache literal legacy Word text without changing original questionnaires.

macOS textutil is a read-only fallback for binary DOC, not a layout verifier.
Embedded objects, table alignment and visual order are not certified. Existing
PDF/XLSM extracts and their manifests remain unchanged.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from cache_cses_questionnaires import file_sha, put, safe_path
from organize_cses_questionnaires import encoded

BASE = "data/processed/cses_questionnaires/additional_waves_v1"
OUTPUT = "legacy_word_text_v1"


def extract(root, textutil):
    if not textutil or not Path(textutil).is_file():
        raise ValueError("Binary DOC extraction requires a working macOS textutil executable")
    base = root / BASE
    manifest = json.loads((base / "manifest.json").read_text())
    records, artifacts = [], {}
    for source in manifest["sources"]:
        original = safe_path(base, source["local_path"])
        if original.suffix.lower() != ".doc":
            continue
        if file_sha(original) != source["sha256"]:
            raise ValueError(f"Original cache fingerprint mismatch: {original}")
        result = subprocess.run([textutil, "-convert", "txt", "-encoding", "UTF-8", "-stdout", str(original)],
                                capture_output=True, check=True, timeout=55)
        text = result.stdout.decode("utf-8")
        if len(text.strip()) < 100:
            raise ValueError(f"Empty or unexpectedly short DOC extraction: {original}")
        if file_sha(original) != source["sha256"]:
            raise ValueError("Original changed during extraction")
        relative = f"{source['wave']}/{original.stem}"
        payload = {"source_sha256": source["sha256"], "source_member": source["source_member"],
                   "lines": [{"line": i + 1, "text": line} for i, line in enumerate(text.splitlines())],
                   "limitation": "Literal text only; line numbers are extraction locators, not printed page numbers."}
        for suffix, content in ((".txt", text.encode()), (".json", encoded(payload))):
            name = relative + suffix
            artifacts[name] = put(safe_path(base / OUTPUT, name), content)
        records.append({"wave": source["wave"], "original_path": source["local_path"],
                        "original_sha256": source["sha256"], "text_path": relative + ".txt",
                        "json_path": relative + ".json", "characters": len(text),
                        "lines": len(payload["lines"]), "form_feed_count": text.count("\f"),
                        "embedded_object_markers": text.count("EMBED "),
                        "role": "editing_manual" if "manual" in original.name.lower() else "questionnaire_or_cover"})
    report = {"source_manifest_sha256": file_sha(base / "manifest.json"),
              "extractor_sha256": file_sha(Path(__file__)), "converter_path": str(Path(textutil).resolve()),
              "converter_sha256": file_sha(Path(textutil)), "sources": records, "artifacts": artifacts,
              "layout_verified": False, "question_links_approved": False}
    put(base / OUTPUT / "manifest.json", encoded(report))
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--textutil", default=shutil.which("textutil"))
    args = parser.parse_args()
    print(json.dumps(extract(args.root, args.textutil), indent=2))
