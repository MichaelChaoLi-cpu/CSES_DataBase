#!/usr/bin/env python3
"""Build isolated, evidence-qualified candidates for five additional CSES waves.

No database connection, historical artifact replacement, Git or DVC operation.
Identifiers are source-native components serialized without lossy padding or casts.
Questionnaire originals are copied byte-for-byte; parsing is a separate operation.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sys
import zipfile
from pathlib import Path, PurePosixPath

import pandas as pd
from build_cses_health import read_stata
from cache_cses_questionnaires import file_sha, put, safe_path

SPEC = "rsc/specs/cses_additional_waves_v1.json"
OUTPUT = "data/processing/cses/additional_waves_v1"
QUESTIONNAIRES = "data/processed/cses_questionnaires/additional_waves_v1"
MODULES = ("HH", "HL", "ED", "EC", "HO", "HEALTH", "SURVEY_DATE", "VL")


def scalar(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                       default=scalar, allow_nan=False) + "\n").encode()


def fields_for(spec, module):
    fields = dict(spec["templates"].get(module.get("template"), {}))
    fields.update(module["fields"])
    return fields


def component(value):
    """Keep string leading zeros; reject missing, fractional or unsafe numeric IDs."""
    if pd.isna(value) or value == "":
        return None
    if isinstance(value, str):
        return value
    number = float(value)
    if not math.isfinite(number) or not number.is_integer() or abs(number) > 2**53:
        raise ValueError(f"Invalid numeric identifier: {value!r}")
    return str(int(number))


def source_keys(frame, columns, wave):
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing key columns: {sorted(missing)}")
    parts = frame[columns].map(component)
    return parts.apply(lambda row: pd.NA if row.isna().any() else
                       json.dumps([wave, *row], ensure_ascii=False, separators=(",", ":")), axis=1).astype("string")


def transform(series, metadata, kind):
    if kind == "native":
        return series.copy(), "native_value_only", 0
    if kind not in {"binary", "sex"}:
        raise ValueError(f"Unknown transform: {kind}")
    words = {"yes": 1, "no": 0} if kind == "binary" else {"male": 1, "female": 2}
    mapping = {r["source_value"]: words[r["label"].strip().lower()]
               for r in metadata["value_labels"] if r["label"].strip().lower() in words}
    if set(mapping.values()) != set(words.values()):
        return pd.Series(pd.NA, index=series.index, dtype="Int64"), "blocked_missing_value_labels", int(series.notna().sum())
    result = series.map(mapping).astype("Int64")
    return result, "label_verified_recode_scope_qualified", int((series.notna() & result.isna()).sum())


def metadata_only(payload):
    with pd.io.stata.StataReader(io.BytesIO(payload), convert_categoricals=False, convert_dates=False) as reader:
        labels = reader.variable_labels()
        dictionaries = reader.value_labels()
        names = list(reader._varlist)
        assignments = dict(zip(names, reader._lbllist, strict=True))
        storage = dict(zip(names, reader._typlist, strict=True))
        variables = [{"name": name, "position": i + 1, "label": labels[name],
                      "storage_type": str(storage[name]), "value_label_set": assignments[name],
                      "value_labels": [{"source_value": scalar(k), "label": v}
                                       for k, v in dictionaries.get(assignments[name], {}).items()]}
                     for i, name in enumerate(names)]
        return int(reader._nobs), variables


def compare_variants(primary, alternate, keys):
    if primary[keys].isna().any().any() or alternate[keys].isna().any().any():
        raise ValueError("Variant comparison requires non-null keys")
    if primary.duplicated(keys).any() or alternate.duplicated(keys).any():
        raise ValueError("Variant comparison requires unique keys")
    a, b = primary.set_index(keys).sort_index(), alternate.set_index(keys).sort_index()
    common = a.index.intersection(b.index)
    differences = []
    for column in sorted(set(a.columns) & set(b.columns)):
        x, y = a.loc[common, column], b.loc[common, column]
        mask = ~(x.eq(y) | (x.isna() & y.isna()))
        for key in common[mask]:
            differences.append({"key": [scalar(v) for v in (key if isinstance(key, tuple) else (key,))],
                                "variable": column, "primary": scalar(x.loc[key]), "alternate": scalar(y.loc[key])})
    return {"common_rows": len(common), "primary_only": len(a.index.difference(b.index)),
            "alternate_only": len(b.index.difference(a.index)), "differences": differences}


def build_table(wave, config, module_name, module, fields, raw, metadata, archive, conflict_keys=()):
    meta = {r["variable_name"]: r for r in metadata}
    key_columns = config["household_key"] + ([config["person_key"]] if module["grain"] == "person" else [])
    result = pd.DataFrame(index=raw.index)
    result["Survey Wave"] = wave
    result["Household Key"] = source_keys(raw, config["household_key"], wave)
    result["Record Key"] = source_keys(raw, key_columns, wave)
    result["Source Archive"] = archive
    result["Source Member"] = module["member"]
    result["Source Row Number"] = range(1, len(raw) + 1)
    for name in key_columns:
        result[f"source__{name}"] = raw[name]
    result["Missing Key"] = result["Record Key"].isna()
    result["Duplicate Key"] = result["Record Key"].notna() & result["Record Key"].duplicated(keep=False)
    result["Source Variant Conflict"] = result["Record Key"].isin(conflict_keys)
    result["Unique Source Record Eligible"] = ~(result["Missing Key"] | result["Duplicate Key"] |
                                                result["Source Variant Conflict"])
    result["Alignment Status"] = "local_candidate_scope_qualified_not_published"
    profiles = []
    for target, (source, kind) in fields.items():
        if source not in raw:
            raise ValueError(f"Missing explicit source: {wave}/{module_name}/{source}")
        result[f"source__{source}"] = raw[source]
        result[target], state, invalid = transform(raw[source], meta[source], kind)
        profile = {"wave": wave, "module": module_name, "target": target, "source_variable": source,
                   "source_member": module["member"], "transform": kind, "state": state,
                   "source_label": meta[source]["variable_label"], "value_labels": meta[source]["value_labels"],
                   "source_non_null": int(raw[source].notna().sum()), "mapped_non_null": int(result[target].notna().sum()),
                   "unmapped_non_null": invalid, "distinct_source_values": int(raw[source].nunique()),
                   "cross_wave_equivalence": "not_certified", "qualification": config["note"]}
        # Only mapped numeric/code fields are profiled, never free-text personal identifiers.
        if pd.api.types.is_numeric_dtype(raw[source]):
            profile["numeric_value_counts"] = [{"value": scalar(v), "rows": int(n)}
                                               for v, n in raw[source].value_counts(dropna=False).sort_index().items()]
        profiles.append(profile)
    if module_name == "HL":
        age = pd.to_numeric(result["Age Source Value"], errors="coerce")
        result["Age Interpretation"] = "source_reported_topcode_not_verified"
        topcode = module.get("age_topcode")
        if topcode:
            result.loc[age.eq(topcode), "Age Interpretation"] = f"{topcode}_or_older_not_exact"
        result.loc[age.isna(), "Age Interpretation"] = "missing"
    return result, profiles


def parquet_bytes(frame):
    buffer = io.BytesIO()
    frame.to_parquet(buffer, index=False)
    return buffer.getvalue()


def combine_tables(frames):
    """Mixed Stata numeric/string codes stay text in the union, never forced numeric.

    Per-wave Parquets retain native dtypes and are the authoritative raw-value
    comparison artifacts. The union reports every text coercion explicitly.
    """
    combined = pd.concat(frames, ignore_index=True, sort=False)
    converted = []
    for column in combined:
        if combined[column].dtype == object:
            types = {type(value) for value in combined[column].dropna()}
            if str in types and len(types) > 1:
                combined[column] = combined[column].astype("string")
                converted.append(column)
    return combined, converted


def build(root, spec_path=None):
    root = root.resolve()
    spec_path = spec_path or root / SPEC
    spec = json.loads(spec_path.read_text())
    output, forms = root / OUTPUT, root / QUESTIONNAIRES
    artifacts, form_artifacts = {}, {}

    def save(relative, payload):
        if not isinstance(payload, bytes):
            payload = encoded(payload)
        artifacts[relative] = put(safe_path(output, relative), payload)

    def save_form(relative, payload):
        form_artifacts[relative] = put(safe_path(forms, relative), payload)

    # Verify every archive before producing any output.
    for config in spec["waves"].values():
        if file_sha(safe_path(root, config["archive"])) != config["sha256"]:
            raise ValueError(f"Archive hash mismatch: {config['archive']}")
    datasets, catalog, questionnaires, profiles, tables, comparisons, wave_summaries = [], [], [], [], {}, [], []
    for wave, config in spec["waves"].items():
        archive_path = safe_path(root, config["archive"])
        selected = {m["member"] for m in config["modules"].values()}
        variants = [c for c in spec["variant_comparisons"] if c["wave"] == wave]
        selected.update(c["alternate"] for c in variants)
        native = {}
        with zipfile.ZipFile(archive_path) as archive:
            names = [i.filename for i in archive.infolist() if not i.is_dir()]
            if len(names) != len(set(names)):
                raise ValueError(f"Duplicate archive member names: {archive_path}")
            for member in sorted(names):
                path = PurePosixPath(member)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError(f"Unsafe member: {member}")
                if any(p.startswith("._") or p == "__MACOSX" for p in path.parts):
                    continue
                suffix = path.suffix.lower()
                if suffix not in {".dta", ".doc", ".docx", ".pdf", ".xls", ".xlsx", ".xlsm"}:
                    continue
                payload = archive.read(member)
                digest = hashlib.sha256(payload).hexdigest()
                # A changed extraction is not silently preferred or discarded.
                extracted = archive_path.with_suffix("").joinpath(*path.parts)
                if extracted.is_file() and file_sha(extracted) != digest:
                    raise ValueError(f"Changed extracted copy needs review: {extracted}")
                if suffix == ".dta":
                    count, variables = metadata_only(payload)
                    datasets.append({"wave": wave, "archive": config["archive"], "member": member,
                                     "sha256": digest, "rows": count, "columns": len(variables),
                                     "selected": member in selected})
                    catalog.extend({"wave": wave, "member": member, **v} for v in variables)
                    if member in selected:
                        frame, metadata, special = read_stata(payload)
                        native[member] = (frame, metadata)
                        save(f"source_missing/{wave}/{path.stem}.json", special)
                else:
                    relative = f"{wave}/forms/{member}"
                    save_form(relative, payload)
                    questionnaires.append({"wave": wave, "source_member": member, "sha256": digest,
                                           "local_path": relative, "status": "original_cached_not_question_verified"})
        missing = selected - set(native)
        if missing:
            raise ValueError(f"Missing selected sources: {wave}: {missing}")
        conflict_by_member = {}
        for comparison in variants:
            report = compare_variants(native[comparison["primary"]][0], native[comparison["alternate"]][0],
                                      comparison["keys"])
            comparisons.append({**comparison, **report})
            primary = native[comparison["primary"]][0]
            diff_keys = {tuple(component(v) for v in row["key"]) for row in report["differences"]}
            flagged = primary[comparison["keys"]].map(component).apply(tuple, axis=1).isin(diff_keys)
            keys = source_keys(primary, config["household_key"] + [config["person_key"]], wave)
            conflict_by_member[comparison["primary"]] = set(keys[flagged])
        for name, module in config["modules"].items():
            raw, meta = native[module["member"]]
            table, p = build_table(wave, config, name, module, fields_for(spec, module), raw, meta,
                                   config["archive"], conflict_by_member.get(module["member"], ()))
            tables[wave, name] = table
            profiles.extend(p)
        hh, hl = tables[wave, "HH"], tables[wave, "HL"]
        if hh["Missing Key"].any() or hh["Duplicate Key"].any() or hl["Missing Key"].any() or hl["Duplicate Key"].any():
            raise ValueError(f"Ambiguous linkage spine: {wave}")
        counts = hl.groupby("Household Key").size()
        hh["Roster Member Count"] = hh["Household Key"].map(counts).astype("Int64")
        for name, module in config["modules"].items():
            table = tables[wave, name]
            table["HH Link Matched"] = table["Household Key"].isin(hh["Household Key"])
            if module["grain"] == "person":
                table["HL Link Matched"] = table["Record Key"].isin(hl["Record Key"])
            save(f"tables/{wave}/{name}.parquet", parquet_bytes(table))
        wave_summaries.append({"wave": wave, "households": len(hh), "roster_records": len(hl),
                               "roster_households": int(hl["Household Key"].nunique()),
                               "note": config["note"]})
        print(f"Built {wave}: {len(hh)} households, {len(hl)} roster records", flush=True)
    table_report = [{"wave": wave, "module": name, "rows": len(table), "columns": len(table.columns),
                     "duplicate_key_rows": int(table["Duplicate Key"].sum()),
                     "missing_key_rows": int(table["Missing Key"].sum()),
                     "variant_conflict_rows": int(table["Source Variant Conflict"].sum()),
                     "unmatched_households": int((~table["HH Link Matched"]).sum()),
                     "unmatched_people": int((~table["HL Link Matched"]).sum()) if "HL Link Matched" in table else None}
                    for (wave, name), table in tables.items()]
    union_text_columns = {}
    for name in MODULES:
        selected = [t for (wave, m), t in tables.items() if m == name]
        if selected:
            combined, union_text_columns[name] = combine_tables(selected)
            save(f"tables/all_{name}.parquet", parquet_bytes(combined))
    coverage = [{"wave": wave, "module": name,
                 "state": "local_partial_field_alignment" if name in config["modules"] else "not_built_source_review_needed"}
                for wave, config in spec["waves"].items() for name in MODULES]
    save("datasets.json", datasets)
    save("variables.json", catalog)
    save("field_alignment.json", profiles)
    save("source_variant_comparison.json", comparisons)
    save("module_coverage.json", coverage)
    save_form("sources.json", encoded(questionnaires))
    form_manifest = {"version": spec["version"], "sources": questionnaires, "artifacts": form_artifacts}
    put(forms / "manifest.json", encoded(form_manifest))
    summary = {"version": spec["version"], "state": spec["status"], "wave_counts": wave_summaries,
               "datasets": len(datasets), "native_variables": len(catalog), "questionnaire_files": len(questionnaires),
               "field_wave_mappings": len(profiles), "label_verified_recodes": sum(
                   p["state"] == "label_verified_recode_scope_qualified" for p in profiles),
               "blocked_recodes": [p for p in profiles if p["state"].startswith("blocked")],
               "unmapped_non_null_cells": sum(p["unmapped_non_null"] for p in profiles),
               "tables": table_report, "union_mixed_type_columns_as_text": union_text_columns,
               "database_modified": False, "historical_outputs_modified": False}
    save("summary.json", summary)
    nodes = [{"id": "archive:" + wave, "type": "archive", "sha256": c["sha256"]}
             for wave, c in spec["waves"].items()]
    edges = []
    for (wave, name), table in tables.items():
        node = f"candidate:{wave}:{name}"
        nodes.append({"id": node, "type": "local_candidate", "rows": len(table)})
        edges.append({"from": "archive:" + wave, "to": node, "role": "source"})
        if name != "HH":
            edges.append({"from": f"candidate:{wave}:HH", "to": node, "role": "household_link"})
        if name not in {"HH", "HL"} and "HL Link Matched" in table:
            edges.append({"from": f"candidate:{wave}:HL", "to": node, "role": "person_link"})
    save("lineage.json", {"scope": "local_candidates_not_database_graph", "nodes": nodes, "edges": edges})
    manifest = {"version": spec["version"], "spec_sha256": file_sha(spec_path),
                "builder_sha256": file_sha(Path(__file__)), "python": sys.version.split()[0], "pandas": pd.__version__,
                "source_archives": {c["archive"]: c["sha256"] for c in spec["waves"].values()},
                "artifacts": artifacts, "questionnaire_manifest_sha256": file_sha(forms / "manifest.json")}
    put(output / "manifest.json", encoded(manifest))
    return summary


def verify(root):
    output = root / OUTPUT
    manifest = json.loads((output / "manifest.json").read_text())
    for relative, expected in manifest["artifacts"].items():
        if file_sha(safe_path(output, relative)) != expected:
            raise ValueError(f"Artifact changed: {relative}")
    if file_sha(root / SPEC) != manifest["spec_sha256"] or file_sha(Path(__file__)) != manifest["builder_sha256"]:
        raise ValueError("Builder/spec changed: use a new output version")
    forms = root / QUESTIONNAIRES
    if file_sha(forms / "manifest.json") != manifest["questionnaire_manifest_sha256"]:
        raise ValueError("Questionnaire manifest changed")
    fm = json.loads((forms / "manifest.json").read_text())
    for relative, expected in fm["artifacts"].items():
        if file_sha(safe_path(forms, relative)) != expected:
            raise ValueError(f"Questionnaire artifact changed: {relative}")
    return {"verified_artifacts": len(manifest["artifacts"]), "verified_questionnaire_artifacts": len(fm["artifacts"]),
            "mode": "cache_only_no_raw_reads", "database_modified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "verify"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    result = build(args.root) if args.command == "build" else verify(args.root)
    print(json.dumps({k: v for k, v in result.items() if k not in {"tables", "blocked_recodes"}}, default=scalar, indent=2))


if __name__ == "__main__":
    main()
