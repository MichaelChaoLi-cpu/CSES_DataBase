#!/usr/bin/env python3
"""Build HEALTH source-grain artifacts and catalog; never connect to PostgreSQL.

Build reads immutable archives once. Verify and load_source use extracted local
artifacts only. No population filters, joins, recoding or cross-wave stacking.
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath

import pandas as pd
from cache_cses_questionnaires import (
    DEFAULT as QUESTIONNAIRES,
)
from cache_cses_questionnaires import (
    WAVES,
    add_artifact,
    file_sha,
    leaf_name,
    markdown_cell,
    put,
    require,
    safe_path,
    sha,
    source_id,
    verify_manifest,
)
from inventory_cses_archives import discover_sources, is_village_source, normalize_wave, token
from pandas.io.stata import StataMissingValue

SPEC = "rsc/specs/cses_health_intake_v1.json"
DEFAULT = "data/processed/cses_health/v1"
ROW_NUMBER = "_cses_source_row_number"
CONTEXT = {
    "hhid",
    "persid",
    "psu",
    "province",
    "district",
    "commune",
    "village",
    "urban",
    "urbanrural",
    "strata",
    "stratum",
    "zone",
    "region",
    "year",
}


def classify_source(name, spec):
    low = name.lower().replace("\\", "/").replace("::", "/")
    if any(p.startswith("code") for p in PurePosixPath(low).parts):
        return None
    leaf = PurePosixPath(low).name
    if (
        is_village_source(low, token(leaf))
        or "village_data.zip/" in low
        or "/village data/" in low
        or "/village2007/" in low
    ):
        return "village_health_context" if re.search(spec["village_leaf_pattern"], leaf) else None
    matches = [topic for topic, pattern in spec["dedicated_leaf_patterns"].items() if re.search(pattern, leaf)]
    require(len(matches) <= 1, f"Ambiguous health topic: {name}")
    if matches:
        return matches[0]
    if re.search(spec["mixed_household_leaf_pattern"], leaf):
        return "healthcare_access_mixed"
    return None


def read_stata(payload):
    """Retain native numeric codes, label dictionaries and special-missing positions."""
    with pd.io.stata.StataReader(io.BytesIO(payload), convert_categoricals=False, convert_dates=False) as reader:
        labels = reader.variable_labels()
        assignments = dict(zip(reader._varlist, reader._lbllist, strict=True))
        storage = dict(zip(reader._varlist, reader._typlist, strict=True))
        label_sets = reader.value_labels()
        frame = reader.read()
    with pd.io.stata.StataReader(
        io.BytesIO(payload), convert_categoricals=False, convert_dates=False, convert_missing=True
    ) as reader:
        missing_frame = reader.read()
    extended = []
    for column in missing_frame:
        if missing_frame[column].dtype != object:
            continue
        for index, value in enumerate(missing_frame[column]):
            if isinstance(value, StataMissingValue) and str(value) != ".":
                require(pd.isna(frame[column].iloc[index]), "Special missing was not stored as null")
                extended.append(
                    {"source_row_number": index + 1, "variable_name": column, "stata_missing_code": str(value)}
                )
    metadata = []
    for index, column in enumerate(frame):
        series = frame[column]
        label_name = assignments[column]
        dictionary = label_sets.get(label_name, {})
        metadata.append(
            {
                "variable_name": column,
                "variable_position": index + 1,
                "variable_label": labels[column],
                "stata_storage_type": str(storage[column]),
                "pandas_dtype": str(series.dtype),
                "value_label_set": label_name,
                "value_labels": [{"source_value": code, "label": label} for code, label in dictionary.items()],
                "non_null_records": int(series.notna().sum()),
                "distinct_non_null_values": int(series.nunique(dropna=True)),
                "alignment_status": "not_reviewed",
            }
        )
    return frame, metadata, extended


def select_columns(frame, topic, spec):
    if topic != "healthcare_access_mixed":
        return list(frame.columns)
    health = [c for c in frame if token(c).startswith(spec["mixed_household_question_prefix"])]
    if not health:
        return []
    context = [c for c in frame if token(c) in CONTEXT or re.fullmatch(r"(?:hw|pw|hpw)\d+[a-z]?", token(c))]
    return [c for c in frame if c in health or c in context]


def key_profiles(frame):
    """Observed key diagnostics, not a declared respondent grain or join contract."""
    names = {c.lower(): c for c in frame}
    candidates = [("persid",), ("hhid",), ("hhid", "persid"), ("psu", "hhid", "persid")]
    profiles = []
    for candidate in candidates:
        if not all(c in names for c in candidate):
            continue
        keys = [names[c] for c in candidate]
        complete = frame[keys].notna().all(axis=1)
        values = frame.loc[complete, keys]
        profiles.append(
            {
                "columns": keys,
                "complete_key_records": int(complete.sum()),
                "missing_key_records": int((~complete).sum()),
                "distinct_complete_keys": int(len(values.drop_duplicates())),
                "records_in_duplicate_complete_keys": int(values.duplicated(keep=False).sum()),
            }
        )
    return profiles


def questionnaire_links(library, wave):
    result = []
    for source in library["sources"]:
        if source["survey_wave"] != wave or source["instrument_type"] not in {
            "household_questionnaire",
            "forms_bundle",
            "questionnaire_bundle",
        }:
            continue
        result.append(
            {
                k: source[k]
                for k in (
                    "source_id",
                    "local_path",
                    "cells_path",
                    "text_path",
                    "language_code",
                    "documentation_status",
                    "registered_instrument_id",
                    "extraction_status",
                )
            }
        )
    return result


def load_source(base, identity):
    """Load a verified local native-code Parquet without raw archives or a database."""
    catalog = json.loads((base / "manifest.json").read_text())
    matches = [s for s in catalog["sources"] if s["source_id"] == identity]
    require(len(matches) == 1, f"Expected one health source: {identity}")
    record = matches[0]
    path = safe_path(base, record["parquet_path"])
    require(file_sha(path) == catalog["artifacts"][record["parquet_path"]], "Health Parquet changed")
    return pd.read_parquet(path)


def build(root, output, library_path):
    spec = json.loads((root / SPEC).read_text())
    require(
        spec["stage"] == "source_intake_not_harmonized" and not spec["database_publication_authorized"],
        "Source-intake boundary changed",
    )
    library = verify_manifest(library_path)
    for relative, expected in library["archive_sha256"].items():
        require(file_sha(root / relative) == expected, f"Archive changed: {relative}")
    inputs = discover_sources(root)
    sources, artifacts, skipped = [], {}, []
    for source in inputs:
        name = source.display_name(root)
        topic = classify_source(name, spec)
        if topic is None:
            continue
        require(
            source.root_file.relative_to(root).as_posix() in library["archive_sha256"],
            f"Source not in verified archives: {name}",
        )
        payload = source.read_bytes()
        frame, fields, extended = read_stata(payload)
        columns = select_columns(frame, topic, spec)
        if not columns:
            skipped.append({"source_file": name, "reason": "No q13a health fields in mixed source"})
            continue
        wave = normalize_wave(name)
        require(wave in WAVES, f"Unknown wave: {name}")
        identity = source_id(name)
        directory = f"{wave}/{topic}/{identity}"
        original = add_artifact(output, artifacts, f"{directory}/{leaf_name(name)}", payload)
        selected = frame[columns].copy()
        require(ROW_NUMBER not in selected, "Source row number collision")
        selected.insert(0, ROW_NUMBER, range(1, len(selected) + 1))
        parquet = selected.to_parquet(index=False)
        pd.testing.assert_frame_equal(selected, pd.read_parquet(io.BytesIO(parquet)))
        parquet_path = add_artifact(output, artifacts, f"{directory}/source.parquet", parquet)
        missing_path = add_artifact(output, artifacts, f"{directory}/extended_missing.json", extended)
        for field in fields:
            field["included_in_parquet"] = field["variable_name"] in columns
            field["field_role"] = (
                "health_question_candidate"
                if token(field["variable_name"]).startswith("q") and field["included_in_parquet"]
                else "context_or_other_source_field"
            )
        metadata_path = add_artifact(output, artifacts, f"{directory}/variables.json", fields)
        record = {
            "source_id": identity,
            "source_file": name,
            "source_sha256": sha(payload),
            "archive_relative_path": source.root_file.relative_to(root).as_posix(),
            "member_chain": list(source.archive_members),
            "survey_wave": wave,
            "topic": topic,
            "local_path": original,
            "parquet_path": parquet_path,
            "variables_path": metadata_path,
            "extended_missing_path": missing_path,
            "extended_missing_cells": len(extended),
            "source_records": len(frame),
            "data_status": "empty_source" if frame.empty else "records_present",
            "source_columns": len(frame.columns),
            "retained_native_columns": len(columns),
            "key_profiles": key_profiles(frame),
            "fields": fields,
            "stage": "source_intake_not_harmonized",
            "respondents": None,
            "questionnaire_links": questionnaire_links(library, wave),
        }
        sources.append(record)
        print(f"{wave}: {topic}: {len(frame):,} source records", flush=True)
    require(len({s["source_id"] for s in sources}) == len(sources), "Source ID collision")
    require(
        {s["survey_wave"] for s in sources if s["topic"] == "illness_care"} == set(WAVES),
        "Illness-care intake must cover the ten observed source waves",
    )
    # Keep aliases separate. No row concatenation or arbitrary preferred source.
    for source in sources:
        source["identical_content_aliases"] = [
            s["source_id"]
            for s in sources
            if s["source_id"] != source["source_id"] and s["source_sha256"] == source["source_sha256"]
        ]
    wave_rows = []
    for wave in WAVES:
        rows = [s for s in sources if s["survey_wave"] == wave]
        summary = {
            "survey_wave": wave,
            "source_files": len(rows),
            "retained_native_field_occurrences": sum(s["retained_native_columns"] for s in rows),
            "topic_counts": dict(sorted(Counter(s["topic"] for s in rows).items())),
            "topic_nonempty_source_counts": dict(
                sorted(Counter(s["topic"] for s in rows if s["source_records"] > 0).items())
            ),
            "illness_source_records": sum(s["source_records"] for s in rows if s["topic"] == "illness_care"),
            "questionnaire_note": next(w["note"] for w in library["waves"] if w["survey_wave"] == wave),
        }
        wave_rows.append(summary)
        lines = [
            f"# HEALTH sources: {wave}",
            "",
            summary["questionnaire_note"],
            "",
            "[Module index](../README.md)",
            "",
            "Counts below are source records, not verified eligible respondents. "
            "Source IDs are not longitudinal person identifiers.",
            "",
        ]
        for source in rows:
            relative_dir = source["parquet_path"].split("/", 1)[1].rsplit("/", 1)[0]
            lines.extend(
                [
                    f"## {source['topic']}: {leaf_name(source['source_file'])}",
                    "",
                    f"Records: {source['source_records']:,}; native columns retained: "
                    f"{source['retained_native_columns']}/{source['source_columns']}.",
                    "",
                    f"[Native-code Parquet]({relative_dir}/source.parquet) · "
                    f"[Variable dictionaries]({relative_dir}/variables.json)",
                    "",
                    "| Variable | Original label | Non-null source records | Included |",
                    "| --- | --- | ---: | --- |",
                ]
            )
            for f in source["fields"]:
                lines.append(
                    f"| {f['variable_name']} | {markdown_cell(f['variable_label'])} | "
                    f"{f['non_null_records']} | {f['included_in_parquet']} |"
                )
            lines.append("")
        add_artifact(output, artifacts, f"{wave}/README.md", "\n".join(lines))
    lines = [
        "# CSES HEALTH module",
        "",
        "Stage: source intake, not harmonized or published to PostgreSQL.",
        "",
        "All native rows and codes are retained in dedicated sources. Mixed household sources "
        "retain q13a health fields and identifiers/weights; full original DTA files are also available.",
        "",
        "| Wave | Source files | Native field occurrences retained | Illness/care source records |",
        "| --- | ---: | ---: | ---: |",
    ]
    for w in wave_rows:
        lines.append(
            f"| [{w['survey_wave']}]({w['survey_wave']}/README.md) | {w['source_files']} | "
            f"{w['retained_native_field_occurrences']} | {w['illness_source_records']:,} |"
        )
    lines.extend(
        [
            "",
            "Field occurrences include keys/context, repeats and source aliases; "
            "they are not counts of unique health concepts or fully aligned variables.",
            "",
            "Stata system missing values become Parquet nulls. Extended .a–.z codes retain "
            "one-based source-row positions in extended_missing.json; original DTA bytes retain everything. "
            "Numeric codes such as 9/98/99 are not recoded. _cses_source_row_number is an added locator.",
            "",
            "Routine access: use the per-wave index, variables.json and source.parquet. "
            "Verification does not require archives or PostgreSQL.",
            "",
            "## Remaining discovery and review",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in spec["scope_notes"])
    lines.append("")
    add_artifact(output, artifacts, "README.md", "\n".join(lines))
    result = {
        "module_code": "HEALTH",
        "version": "cses-health-intake-v1",
        "stage": spec["stage"],
        "database_mutated": False,
        "cross_wave_harmonization_approved": False,
        "archive_sha256": library["archive_sha256"],
        "spec_sha256": file_sha(root / SPEC),
        "implementation_sha256": file_sha(Path(__file__)),
        "questionnaire_library_manifest_sha256": file_sha(library_path / "manifest.json"),
        "questionnaire_library": library_path.relative_to(root).as_posix(),
        "sources": sources,
        "waves": wave_rows,
        "artifacts": artifacts,
        "skipped_candidates": skipped,
        "discovered_stata_sources": [s.display_name(root) for s in inputs],
        "scope_counts": {
            "source_files": len(sources),
            "waves": len(wave_rows),
            "retained_native_field_occurrences": sum(s["retained_native_columns"] for s in sources),
            "fully_harmonized_variables": 0,
            "published_health_relations": 0,
        },
        "scope_notes": spec["scope_notes"],
    }
    put(output / "manifest.json", result)
    verify_manifest(output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["build", "verify"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--questionnaires", type=Path)
    args = parser.parse_args()
    output = args.output or args.root / DEFAULT
    result = (
        build(args.root, output, args.questionnaires or args.root / QUESTIONNAIRES)
        if args.mode == "build"
        else verify_manifest(output)
    )
    print(json.dumps(result["scope_counts"], sort_keys=True))


if __name__ == "__main__":
    main()
