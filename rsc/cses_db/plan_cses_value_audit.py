#!/usr/bin/env python3
"""Audit response options, raw code frequencies and current published codes read-only."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
from cses_baseline_metadata import canonical_sha256, connect_database, connection_arguments, sha256_file
from cses_questionnaire_provenance import inspect_database
from inventory_cses_archives import DataSource
from pandas.io.stata import StataMissingValue
from psycopg import sql

DATASET_KEY = ("archive_relative_path", "member_path", "nested_member_path")
CODE_PATHS = (
    "rsc/cses_db/plan_cses_value_audit.py",
    "rsc/cses_db/extract_cses_response_option_cells.py",
    "rsc/cses_db/cses_baseline_metadata.py",
    "rsc/cses_db/cses_questionnaire_provenance.py",
    "rsc/cses_db/cses_variable_catalog.py",
    "rsc/cses_db/inventory_cses_archives.py",
    "pyproject.toml",
    "uv.lock",
)


def dataset_key(record: dict) -> tuple:
    return tuple(record.get(field) or "" for field in DATASET_KEY)


def normalized_label(text: str) -> str:
    return " ".join(text.replace("’", "'").split()).casefold()


def parse_option_cell(text: str, cell: str) -> list[dict]:
    """Parse only explicitly located numbered options; retain skip text separately."""
    records = []
    for line in text.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"\s*(\d+)\s*=\s*(.+?)\s*", line)
        if not match:
            raise ValueError(f"Unparsed option line at {cell}: {line!r}")
        code, content = match.groups()
        skip = re.search(r"\s*\(\s*=?\s*>{2}.*?\)\s*$", content)
        label = content[:skip.start()].strip() if skip else content.strip()
        records.append({"source_code": str(int(code)), "label": label, "source_cell": cell,
                        "raw_line": line, "skip_text": skip.group().strip() if skip else None})
    return records


def classify_label(label: str | None, spec: dict) -> tuple[str, str | None]:
    if not label:
        return "unresolved", None
    normalized = normalized_label(label)
    for category, aliases in spec["missing_label_aliases"].items():
        if normalized in {normalized_label(alias) for alias in aliases}:
            return category, None
    for category, aliases in spec["category_aliases"].items():
        if normalized in {normalized_label(alias) for alias in aliases}:
            return "substantive", category
    return "unresolved", None


def code_identity(value: Any) -> tuple[str, str]:
    if isinstance(value, StataMissingValue):
        return "stata_missing", value.string
    if pd.isna(value):
        return "system_missing", "NULL"
    if isinstance(value, str):
        return "string", value
    number = float(value)
    return "numeric", str(int(number)) if number.is_integer() else str(number)


def frequencies(values) -> dict[tuple[str, str], int]:
    return dict(Counter(code_identity(value) for value in values))


def code_sort_key(identity: tuple[str, str]) -> tuple:
    kind, code = identity
    return (kind, float(code) if kind == "numeric" else 0, code)


def read_evidence(root: Path, spec: dict) -> dict:
    result = {}
    for name, descriptor in spec["evidence"].items():
        path = root / descriptor["path"]
        if sha256_file(path) != descriptor["sha256"]:
            raise ValueError(f"Evidence fingerprint changed: {descriptor['path']}")
        if path.suffix == ".json":
            result[name] = json.loads(path.read_text())
    if "questionnaire_cells" in result:
        cells = result["questionnaire_cells"]
        if cells["extractor_sha256"] != sha256_file(root / "rsc/cses_db/extract_cses_response_option_cells.py"):
            raise ValueError("Questionnaire extraction code changed; regenerate cell evidence")
        if cells["questionnaire_spec_sha256"] != sha256_file(root / "rsc/specs/cses_questionnaire_provenance_v1.json"):
            raise ValueError("Questionnaire specification changed; regenerate cell evidence")
    return result


def reconcile_value(code: str, kind: str, label: str | None, option: dict | None,
                    provisional: bool, spec: dict) -> dict:
    if kind in {"stata_missing", "system_missing"}:
        return {"missing_class": kind, "candidate_category": None, "flags": ["missing_reason_unknown"]}
    source_class, source_category = classify_label(label, spec)
    option_class, option_category = classify_label(option["label"] if option else None, spec)
    flags = []
    if label and option and (source_class, source_category) != (option_class, option_category):
        flags.append("source_label_option_conflict")
        classification, category = "unresolved", None
    elif label:
        classification, category = source_class, source_category
    else:
        classification, category = option_class, option_category
    if classification == "unresolved":
        flags.append("meaning_unresolved")
        if label and not label.isascii():
            flags.append("source_label_translation_required")
    if provisional and option:
        flags.append("draft_questionnaire")
    if category in {"other", "firewood_and_charcoal", "gas_and_electricity", "kerosene_or_diesel"}:
        flags.append("category_comparability_review")
    return {"missing_class": classification, "candidate_category": category, "flags": flags}


def build_local_report(root: Path, spec: dict, evidence: dict) -> dict:
    baseline = evidence["baseline_plan"]["desired_state"]
    variable_plan = evidence["variable_plan"]["desired_state"]
    questionnaire = evidence["questionnaire_plan"]["desired_state"]
    datasets = {dataset_key(row): row for row in baseline["datasets"]}
    sources = {(*dataset_key(row), row["variable_name"]): row for row in variable_plan["source_variables"]}
    links = {(*dataset_key(row), row["variable_name"]): row for row in questionnaire["source_variable_links"]}
    questions = {(row["survey_wave"], row["question_code"]): row for row in questionnaire["questions"]}
    instruments = {row["survey_wave"]: row for row in evidence["questionnaire_cells"]["instruments"]}
    blocks = {(row["survey_wave"], row["canonical_name"]): row for row in spec["option_blocks"]}
    variables = {row["canonical_name"]: row for row in spec["variables"]}
    selected = [row for row in variable_plan["variable_mappings"]
                if row["target_table"] == spec["target_table"] and row["canonical_name"] in variables]
    selected.sort(key=lambda row: (datasets[dataset_key(row)]["survey_wave"], row["canonical_name"]))
    if len(selected) != 30 or len({(datasets[dataset_key(row)]["survey_wave"], row["canonical_name"])
                                  for row in selected}) != 30:
        raise ValueError("Pilot requires exactly one source per canonical field in each of ten waves")
    if any(len(row["source_variable_names"]) != 1 for row in selected):
        raise ValueError("Pilot cannot profile composite source mappings")
    selected_archives = {row["archive_relative_path"] for row in selected}
    archive_fingerprints = {}
    for archive in baseline["source_archives"]:
        if archive["relative_path"] in selected_archives:
            observed = sha256_file(root / archive["relative_path"])
            if observed != archive["sha256"]:
                raise ValueError(f"Source archive changed: {archive['relative_path']}")
            archive_fingerprints[archive["relative_path"]] = observed
    if set(archive_fingerprints) != selected_archives:
        raise ValueError("An input archive is not registered")
    for wave, instrument in instruments.items():
        registered = next(i for i in questionnaire["instruments"] if i["source_file"] == instrument["source_file"])
        if registered["source_sha256"] != instrument["source_sha256"]:
            raise ValueError(f"Questionnaire evidence identity changed: {wave}")
        archive, member = instrument["source_file"].split("::", 1)
        if hashlib.sha256(DataSource(root / archive, (member,)).read_bytes()).hexdigest() != registered["source_sha256"]:
            raise ValueError(f"Questionnaire archive member changed: {wave}")
    local_frame = pd.read_parquet(root / spec["evidence"]["local_housing"]["path"],
                                 columns=["Survey Wave"] + [v["local_column"] for v in variables.values()])
    profiles, rows = [], []
    source_cache = {}
    for mapping in selected:
        key = dataset_key(mapping)
        wave = datasets[key]["survey_wave"]
        canonical = mapping["canonical_name"]
        name = mapping["source_variable_names"][0]
        source = sources[(*key, name)]
        if key not in source_cache:
            names = [row["source_variable_names"][0] for row in selected if dataset_key(row) == key]
            payload = DataSource(root / key[0], tuple(part for part in key[1:] if part)).read_bytes()
            with pd.io.stata.StataReader(io.BytesIO(payload), convert_categoricals=False, convert_missing=True) as reader:
                label_sets = reader.value_labels()
                variable_labels = reader.variable_labels()
                assigned = dict(zip(reader._varlist, reader._lbllist, strict=True))
                metadata = {column: {"variable_label": variable_labels.get(column) or None,
                                     "value_labels": {code_identity(k)[1]: str(v)
                                                      for k, v in label_sets.get(assigned[column], {}).items()} or None}
                            for column in names}
                frame = reader.read(columns=names)
            source_cache[key] = (frame, metadata, hashlib.sha256(payload).hexdigest())
        frame, metadata, member_sha256 = source_cache[key]
        if any(metadata[name][field] != source[field] for field in ("variable_label", "value_labels")):
            raise ValueError(f"Source metadata differs from accepted catalog: {wave}/{name}")
        counts = frequencies(frame[name])
        if any(kind == "string" for kind, _ in counts):
            raise ValueError("This pilot expects numeric Stata code columns")
        local_counts = frequencies(local_frame.loc[local_frame["Survey Wave"].eq(wave), variables[canonical]["local_column"]])
        block = blocks.get((wave, canonical))
        options, question_evidence = {}, None
        if block:
            question = questions[(wave, block["question_code"])]
            link = links.get((*key, name))
            instrument = instruments[wave]
            if not link or link["question_code"] != block["question_code"] or link["source_file"] != instrument["source_file"]:
                raise ValueError(f"Pilot question link not in approved provenance: {wave}/{name}")
            context = question["repeat_context"]
            if normalized_label(instrument["cells"][context["question_text_cell"]]) != normalized_label(question["question_text"]):
                raise ValueError(f"Question text changed at cataloged cell: {wave}/{name}")
            for cell in block["option_cells"]:
                for option in parse_option_cell(instrument["cells"][cell], cell):
                    if option["source_code"] in options:
                        raise ValueError(f"Duplicate response code in selected option cells: {wave}/{name}")
                    options[option["source_code"]] = option
            if len(options) != block["expected_option_count"]:
                raise ValueError(f"Response option count changed: {wave}/{name}")
            question_evidence = {
                "question_code": question["question_code"], "question_text": question["question_text"],
                "source_file": instrument["source_file"], "source_sha256": instrument["source_sha256"],
                "source_sheet": instrument["source_sheet"], "question_text_cell": context["question_text_cell"],
                "question_code_cell": context["question_code_cell"], "option_cells": block["option_cells"],
                "documentation_status": instrument["documentation_status"],
                "extraction_method": instrument["extraction_method"], "is_exact_question_text": False,
            }
        labels = source["value_labels"] or {}
        codes = set(counts) | {("numeric", code) for code in set(labels) | set(options)}
        profile_id = f"{wave}/{canonical}"
        profile = {
            "profile_id": profile_id, "survey_wave": wave, "canonical_name": canonical,
            "target_table": spec["target_table"], "mapping_version": mapping["mapping_version"],
            **dict(zip(DATASET_KEY, key, strict=True)), "source_variable": name,
            "source_variable_label": source["variable_label"], "source_value_labels": source["value_labels"],
            "member_sha256": member_sha256, "questionnaire": question_evidence,
            "raw_row_count": len(frame), "local_published_row_count": sum(local_counts.values()),
            "local_published_frequencies": [
                {"code_kind": kind, "source_code": code, "count": count}
                for (kind, code), count in sorted(local_counts.items())],
        }
        profiles.append(profile)
        for kind, code in sorted(codes, key=code_sort_key):
            option = options.get(code) if kind == "numeric" else None
            decision = reconcile_value(code, kind, labels.get(code), option,
                                       bool(question_evidence and question_evidence["documentation_status"] == "provisional"),
                                       spec)
            count = counts.get((kind, code), 0)
            flags = decision["flags"]
            if not block:
                flags.append("questionnaire_options_unavailable")
            if kind == "numeric" and not labels:
                flags.append("source_value_labels_absent")
            if kind == "numeric" and count and options and not option and decision["missing_class"] not in spec["missing_label_aliases"]:
                flags.append("observed_code_outside_questionnaire")
            published_count = local_counts.get((kind, code), 0) if kind == "numeric" else None
            if decision["missing_class"] in spec["missing_label_aliases"] and published_count:
                flags.append("documented_missing_code_retained_in_published_source_code")
            if kind == "numeric" and published_count != count:
                flags.append("raw_published_frequency_difference")
            if option and option["skip_text"]:
                flags.append("skip_instruction_retained_not_evaluated")
            rows.append({
                "profile_id": profile_id, "survey_wave": wave, "canonical_name": canonical,
                "source_variable": name, "code_kind": kind, "source_code": code,
                "raw_count": count, "local_published_code_count": published_count,
                "source_label": labels.get(code) if kind == "numeric" else None,
                "questionnaire_option": option, **decision, "flags": sorted(set(flags)),
                "review_status": "unresolved" if "meaning_unresolved" in flags else "proposed",
                "publication_ready": False,
            })
    conflicts = []
    groups = defaultdict(list)
    for row in rows:
        if row["code_kind"] == "numeric" and row["missing_class"] != "unresolved":
            groups[(row["canonical_name"], row["source_code"])].append(row)
    for (canonical, code), group in sorted(groups.items()):
        meanings = {(row["missing_class"], row["candidate_category"]) for row in group}
        if len(meanings) > 1:
            conflicts.append({"type": "cross_wave_code_meaning_change", "canonical_name": canonical,
                              "source_code": code,
                              "evidence": [{"survey_wave": row["survey_wave"], "raw_count": row["raw_count"],
                                            "missing_class": row["missing_class"],
                                            "candidate_category": row["candidate_category"]} for row in group]})
    return {"profiles": profiles, "code_rows": rows, "cross_wave_conflicts": conflicts,
            "archive_fingerprints": archive_fingerprints,
            "questionnaire_coverage_gaps": evidence["questionnaire_plan"]["coverage_gaps"]}


def database_audit(arguments: dict, report: dict, spec: dict, evidence: dict, root: Path) -> dict:
    with connect_database(arguments) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '55s'")
            qspec = json.loads((root / "rsc/specs/cses_questionnaire_provenance_v1.json").read_text())
            previous = inspect_database(connection, evidence["questionnaire_plan"]["desired_state"], qspec)
            checks = dict(previous["checks"])
            checks["questionnaire_release_reconciles_as_471_noops"] = previous["action_counts"] == {
                "noop": 471, "insert": 0, "update": 0, "conflict": 0}
            observed = connection.execute("""
                SELECT s.survey_wave, a.relative_path AS archive_relative_path,
                       d.member_path, coalesce(d.nested_member_path, '') AS nested_member_path,
                       v.variable_name, v.variable_label, v.value_labels,
                       c.canonical_name, m.source_variable_names, r.mapping_version
                FROM cses_alignment.cses_variable_mapping m
                JOIN cses_alignment.cses_canonical_variable c USING (canonical_variable_id)
                JOIN cses_meta.cses_alignment_release r USING (alignment_release_id)
                JOIN cses_meta.cses_dataset d USING (dataset_id)
                JOIN cses_meta.cses_survey s ON s.survey_id = d.survey_id
                JOIN cses_meta.cses_source_archive a ON a.source_archive_id = d.source_archive_id
                JOIN cses_alignment.cses_source_variable v
                  ON v.dataset_id = d.dataset_id AND v.variable_name = ANY(m.source_variable_names)
                WHERE c.target_table = %s AND c.canonical_name = ANY(%s)
                ORDER BY s.survey_wave, c.canonical_name
                """, (spec["target_table"], [v["canonical_name"] for v in spec["variables"]])).fetchall()
            expected = [{"survey_wave": p["survey_wave"], **{f: p[f] for f in DATASET_KEY},
                         "variable_name": p["source_variable"], "variable_label": p["source_variable_label"],
                         "value_labels": p["source_value_labels"], "canonical_name": p["canonical_name"],
                         "source_variable_names": [p["source_variable"]], "mapping_version": p["mapping_version"]}
                        for p in report["profiles"]]
            checks["selected_database_metadata_matches_pinned_sources"] = observed == expected
            aggregates = []
            for variable in spec["variables"]:
                canonical = variable["canonical_name"]
                query = sql.SQL("SELECT survey_wave, {column} AS source_code, count(*) AS count "
                                "FROM cses_data.{table} GROUP BY survey_wave, {column} "
                                "ORDER BY survey_wave, {column} NULLS LAST").format(
                                    column=sql.Identifier(canonical), table=sql.Identifier(spec["target_table"]))
                found = connection.execute(query).fetchall()
                by_wave = defaultdict(dict)
                for row in found:
                    kind, code = code_identity(row["source_code"])
                    by_wave[row["survey_wave"]][(kind, code)] = row["count"]
                    aggregates.append({"canonical_name": canonical, "survey_wave": row["survey_wave"],
                                       "code_kind": kind, "source_code": code, "count": row["count"]})
                expected_waves = {p["survey_wave"] for p in report["profiles"] if p["canonical_name"] == canonical}
                checks[f"{canonical}_wave_coverage_matches"] = set(by_wave) == expected_waves
                for profile in report["profiles"]:
                    if profile["canonical_name"] == canonical:
                        expected_counts = {(r["code_kind"], r["source_code"]): r["count"]
                                           for r in profile["local_published_frequencies"]}
                        checks[f"published_frequencies_match_{profile['profile_id']}"] = (
                            by_wave[profile["survey_wave"]] == expected_counts)
            return {"checks": checks, "scope_counts": previous["scope_counts"],
                    "questionnaire_action_counts": previous["action_counts"],
                    "transaction_read_only": previous["database"]["transaction_read_only"],
                    "isolation_level": "repeatable read", "database": previous["database"]["database"],
                    "selected_metadata_sha256": canonical_sha256(observed), "published_frequencies": aggregates}


def markdown_review(report: dict, spec: dict) -> str:
    def text(value):
        return str(value or "—").replace("|", "\\|").replace("\n", " ")

    summary = report["summary"]
    lines = ["# CSES Housing Code Review v1", "",
             "Proposed evidence review. No response option, value mapping, or data row has been published.", "",
             f"Profiles: {summary['profiles']}; code rows: {summary['code_rows']}; "
             f"cross-wave code-meaning changes: {summary['cross_wave_code_meaning_changes']}.", "",
             "Counts are unweighted source records, including retained unmatched records. They are not population estimates.",
             "A missing code has no inferred reason. Blank/extended missing codes are not automatically refusal or inapplicability.",
             "Proposed categories are scoped to the named variable. Residual Other and compound categories still need review.", "",
             "## Coverage", "", "| Wave | Field | Raw rows | Questionnaire | Raw Stata labels |",
             "|---|---|---:|---|---|"]
    for p in report["profiles"]:
        q = p["questionnaire"]
        lines.append(f"| {p['survey_wave']} | {p['canonical_name']} | {p['raw_row_count']:,} | "
                     f"{q['documentation_status'] if q else 'unavailable'} | "
                     f"{'present' if p['source_value_labels'] else 'absent'} |")
    lines += ["", "## Cross-wave code conflicts", "",
              "Each row identifies a reused number with different documented meanings. Draft evidence remains provisional.", "",
              "| Field | Code | Wave, meaning and observed count |", "|---|---|---|"]
    for conflict in report["cross_wave_conflicts"]:
        meaning = "; ".join(f"{e['survey_wave']}: {e['candidate_category'] or e['missing_class']} ({e['raw_count']:,})"
                            for e in conflict["evidence"])
        lines.append(f"| {conflict['canonical_name']} | {conflict['source_code']} | {meaning} |")
    lines += ["", "## Findings requiring attention", "", "| Finding | Code rows |", "|---|---:|"]
    for flag, count in sorted(summary["flag_counts"].items()):
        lines.append(f"| {flag} | {count} |")
    lines += ["", "Flags count code rows and may overlap. Zero-frequency labeled or questionnaire-only codes are included.", "",
              "## Complete code comparison", ""]
    for p in report["profiles"]:
        lines += ["", f"### {p['profile_id']}", "", f"Source: `{p['archive_relative_path']}::{p['member_path']}"
                  f"{'::' + p['nested_member_path'] if p['nested_member_path'] else ''}`; variable `{p['source_variable']}`.", ""]
        q = p["questionnaire"]
        if q:
            lines += [f"Questionnaire: `{q['source_file']}`; sheet `{q['source_sheet']}`; question "
                      f"`{q['question_code']}` at `{q['question_text_cell']}`; options "
                      f"`{', '.join(q['option_cells'])}`. Status: {q['documentation_status']}.", ""]
        else:
            lines += ["No authoritative option cells are available in the current questionnaire catalog.", ""]
        lines += ["| Code | Raw n | Published code n | Stata label | Questionnaire option | Proposed category / missing class | Flags |",
                  "|---|---:|---:|---|---|---|---|"]
        for row in report["code_rows"]:
            if row["profile_id"] != p["profile_id"]:
                continue
            option = row["questionnaire_option"]
            option_label = f"{option['label']} ({option['source_cell']})" if option else None
            published = row["local_published_code_count"]
            lines.append(f"| {row['source_code']} | {row['raw_count']:,} | "
                         f"{published if published is not None else '—'} | {text(row['source_label'])} | "
                         f"{text(option_label)} | {text(row['candidate_category'] or row['missing_class'])} | "
                         f"{text(', '.join(row['flags']))} |")
    lines += ["", "## Reproduction", "", "See docs/cses-value-audit-runbook.md. "
              "The JSON preflight carries hashes, option skip text, database checks and all seven questionnaire gaps.", ""]
    return "\n".join(lines)


def conflict_report(report: dict) -> str:
    lines = ["# CSES Value Audit Conflicts v1", "",
             "Read-only review of three housing fields across ten waves. Counts are unweighted records.", "",
             "## Published-code findings", "",
             "| Wave | Field | Raw code | Raw n | Published code n | Evidence classification | Finding |",
             "|---|---|---|---:|---:|---|---|"]
    important = {"documented_missing_code_retained_in_published_source_code",
                 "raw_published_frequency_difference", "source_label_option_conflict",
                 "observed_code_outside_questionnaire", "source_label_translation_required"}
    for row in report["code_rows"]:
        flags = sorted(set(row["flags"]) & important)
        if flags:
            lines.append(f"| {row['survey_wave']} | {row['canonical_name']} | {row['source_code']} | "
                         f"{row['raw_count']} | {row['local_published_code_count']} | {row['missing_class']} | "
                         f"{', '.join(flags)} |")
    lines += ["", "The published frequency was verified against both the pinned local Parquet and mda. "
              "A frequency difference alone does not establish a defect: documented missing sentinels may already be nulled.",
              "", "## Missingness", "", "| Class | Code rows | Raw variable observations |", "|---|---:|---:|"]
    for category in ["stata_missing", "unspecified_missing", "refused", "dont_know", "not_applicable", "unresolved"]:
        selected = [r for r in report["code_rows"] if r["missing_class"] == category]
        lines.append(f"| {category} | {len(selected)} | {sum(r['raw_count'] for r in selected):,} |")
    lines += ["", "These totals sum observations across three fields and must not be interpreted as distinct households. "
              "Zero refusal/don't-know/not-applicable classifications means no explicit such label was identified; "
              "it does not establish that these reasons never occurred. Unresolved codes are not classified as missing.",
              "", "## Review work remaining", "",
              "- Review the 2004 lighting missing-code handling as a narrowly scoped future data correction.",
              "- Recover household questionnaire/codebook evidence for 2007, 2013 and 2017 before assigning their unlabeled codes.",
              "- Retain 2014 option-based candidates as provisional until the final questionnaire is available.",
              "- Confirm the untranslated 2021 lighting label against an authoritative bilingual source.",
              "- Investigate the undocumented 2021 tenure code 0 without assigning a missingness reason.",
              "- Review residual Other, compound fuels and skip rules before accepting cross-wave categories.",
              "", f"The complete comparison records {len(report['cross_wave_conflicts'])} field/code groups "
              "with different documented meanings across waves. See [code comparison](code_review.md).", "",
              "No database correction, value mapping, or new alignment release is authorized by this evidence file.", ""]
    return "\n".join(lines)


def review_topology(report: dict) -> str:
    s = report["summary"]
    return f'''flowchart LR
    RAW["{s['source_datasets']} raw housing datasets<br/>full code frequencies"]
    QUEST["5 questionnaire files<br/>{s['questionnaire_options']} located options"]
    CATALOG["Approved variable and question catalog"]
    DB["mda and pinned local release<br/>30 frequency profiles"]
    AUDIT["Read-only value audit<br/>{s['code_rows']} code rows"]
    REVIEW["Proposed category comparison<br/>{s['cross_wave_code_meaning_changes']} field/code conflicts"]
    FUTURE["Future reviewed value-mapping release<br/>currently 0 database value mappings"]
    RAW --> AUDIT
    QUEST --> AUDIT
    CATALOG --> AUDIT
    DB -.->|"validation"| AUDIT
    AUDIT --> REVIEW
    REVIEW -.->|"semantic review required"| FUTURE
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--spec", type=Path, default=Path("rsc/specs/cses_value_audit_v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processing/cses/value_audit_v1"))
    parser.add_argument("--dbname", default="mda")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user")
    args = parser.parse_args()
    root = args.root.resolve()
    spec_path = root / args.spec
    spec = json.loads(spec_path.read_text())
    if spec.get("database_write_allowed") is not False or spec.get("status") != "proposed":
        raise ValueError("This command only supports a proposed, read-only audit")
    if spec.get("schema_version") != 1 or spec["database"] != "mda" or args.dbname != "mda":
        raise ValueError("This preflight is scoped to schema version 1 and mda")
    evidence = read_evidence(root, spec)
    report = build_local_report(root, spec, evidence)
    report["database_audit"] = database_audit(
        connection_arguments(args.dbname, args.host, args.port, args.user), report, spec, evidence, root)
    checks = dict(report["database_audit"]["checks"])
    checks["raw_frequency_totals_match_rows"] = all(
        sum(row["raw_count"] for row in report["code_rows"] if row["profile_id"] == p["profile_id"])
        == p["raw_row_count"] for p in report["profiles"])
    checks["raw_and_published_row_totals_match"] = all(
        p["raw_row_count"] == p["local_published_row_count"] for p in report["profiles"])
    checks["no_row_is_marked_publishable"] = all(not row["publication_ready"] for row in report["code_rows"])
    report.update({
        "schema_version": 1, "preflight_id": spec["preflight_id"], "database_mutated": False,
        "publication_ready": False, "technical_checks_passed": all(checks.values()), "checks": checks,
        "source_data_dvc_revision": spec["source_data_dvc_revision"], "evidence": spec["evidence"],
        "spec_sha256": sha256_file(spec_path),
        "code_git_revision": subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                                            capture_output=True, text=True).stdout.strip(),
        "code_files_sha256": {path: sha256_file(root / path) for path in CODE_PATHS},
        "code_revision_note": "HEAD identifies the base checkout; file SHA-256 values identify the executed implementation.",
        "policies": spec["policies"],
        "summary": {
            "profiles": len(report["profiles"]), "source_datasets": len({dataset_key(p) for p in report["profiles"]}),
            "survey_waves": len({p["survey_wave"] for p in report["profiles"]}),
            "canonical_variables": len(spec["variables"]), "code_rows": len(report["code_rows"]),
            "profiles_with_questionnaire": sum(p["questionnaire"] is not None for p in report["profiles"]),
            "profiles_with_source_labels": sum(bool(p["source_value_labels"]) for p in report["profiles"]),
            "questionnaire_options": sum(r["questionnaire_option"] is not None for r in report["code_rows"]),
            "cross_wave_code_meaning_changes": len(report["cross_wave_conflicts"]),
            "flag_counts": dict(sorted(Counter(flag for row in report["code_rows"] for flag in row["flags"]).items())),
        },
    })
    output = root / args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    (output / "preflight.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    (output / "code_review.md").write_text(markdown_review(report, spec))
    (output / "conflicts.md").write_text(conflict_report(report))
    (output / "overview.mmd").write_text(review_topology(report))
    print(json.dumps({"technical_checks_passed": report["technical_checks_passed"],
                      "database_mutated": False, "publication_ready": False, **report["summary"]}, indent=2))
    if not report["technical_checks_passed"]:
        raise SystemExit(f"Technical checks failed: {[name for name, passed in checks.items() if not passed]}")


if __name__ == "__main__":
    main()
