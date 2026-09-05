#!/usr/bin/env python3
"""Trace the 19 retained housing/HH orphans back to immutable source members."""

from __future__ import annotations

import argparse
import hashlib
import io
from collections import Counter
from pathlib import Path

import pandas as pd
from correct_cses_housing_lighting import write_json
from cses_baseline_metadata import connect_database, sha256_file
from cses_hh_hl_common import ID_WIDTHS, clean_code
from inventory_cses_archives import DataSource, discover_archive, modules_for_source
from publish_cses_housing_interface import source_archive
from record_cses_value_mapping_decisions import require

OUTPUT = "data/processing/cses/housing_orphan_audit_v1/report.json"


def identifier_matches(frame, wave, wanted):
    """Test both household IDs and person-ID household prefixes, with existing padding rules."""
    result = {key: set() for key in wanted}
    for column in frame:
        if column.lower() not in ("hhid", "persid"):
            continue
        person = column.lower() == "persid"
        keys = clean_code(frame[column], ID_WIDTHS[wave]["Person ID" if person else "Household ID"])[0]
        if person:
            keys = keys.str[:-2]
        for key in wanted:
            result[key].update(int(i) for i in frame.index[keys.eq(key).fillna(False)])
    return result


def audit(root, live=True):
    inputs = {}
    frames = {}
    for module in ("HO", "HH", "HL", "ED", "EC"):
        path = f"data/processing/cses/final_{module}_CSES.parquet"
        inputs[path] = sha256_file(root / path)
        frames[module] = pd.read_parquet(root / path)
    ho = frames["HO"]
    orphan = ho.loc[ho["HH Link Matched"].eq(0)].sort_values(["Survey Wave", "Household ID"])
    require(len(orphan) == 19 and orphan.groupby("Survey Wave").size().to_dict() == {"2004": 16, "2009": 1, "2014": 2},
            "Expected retained orphan set changed")
    rows = []
    scanned = []
    for wave in ("2004", "2009", "2014"):
        selected = orphan.loc[orphan["Survey Wave"].eq(wave)]
        wanted = set(selected["Household ID"])
        archive = str(selected["Source Archive"].iloc[0])
        inputs[archive] = sha256_file(root / archive)
        hits = {key: [] for key in wanted}
        roster_sources = []
        for source in discover_archive(root / archive):
            payload = source.read_bytes()
            modules = modules_for_source(source, root)
            with pd.io.stata.StataReader(io.BytesIO(payload), convert_categoricals=False) as reader:
                identifiers = [c for c in reader.variable_labels() if c.lower() in ("hhid", "persid")]
                frame = reader.read(columns=identifiers) if identifiers else pd.DataFrame()
            matches = identifier_matches(frame, wave, wanted)
            descriptor = {"source_file": source.display_name(root), "sha256": hashlib.sha256(payload).hexdigest(),
                          "modules": modules, "identifier_columns": identifiers}
            scanned.append(descriptor)
            if "household_members" in modules:
                roster_sources.append(descriptor)
                require(all(not indices for indices in matches.values()), "An original member match needs new investigation")
            for key, indices in matches.items():
                if indices:
                    hit = {**descriptor, "matching_rows": len(indices)}
                    if source.archive_members[-1].endswith("/households.dta"):
                        header = pd.read_stata(io.BytesIO(payload), convert_categoricals=False).iloc[sorted(indices)]
                        hit["header_counts"] = header[[c for c in ("males", "females", "total") if c in header]].to_dict("records")
                    hits[key].append(hit)
        require(len(roster_sources) == 1, "Ambiguous original roster source")
        housing_source = DataSource(root / archive, tuple(selected["Source Submodule"].iloc[0].split("::")))
        raw = pd.read_stata(io.BytesIO(housing_source.read_bytes()), convert_categoricals=False)
        questions = [c for c in raw if c.lower().startswith("q")]
        for _, target in selected.iterrows():
            key = target["Household ID"]
            ordinal = int(target["Source Row ID"].rsplit(":", 1)[1])
            original = raw.iloc[[ordinal - 1]]
            require(identifier_matches(original, wave, {key})[key] == {ordinal - 1}, "Housing source-row identity differs")
            nonnull = int(original[questions].notna().sum().sum())
            local_matches = {}
            for module in ("HH", "HL", "ED", "EC"):
                f = frames[module]
                local_matches[module] = int((f["Survey Wave"].eq(wave) & f["Household ID"].eq(key)).sum())
            require(local_matches["HH"] == local_matches["HL"] == 0, "Local roster/household match unexpectedly present")
            rows.append({"survey_wave": wave, "household_id": key, "source_row_id": target["Source Row ID"],
                         "source_archive": archive, "source_submodule": target["Source Submodule"],
                         "raw_question_columns": len(questions), "raw_nonnull_question_cells": nonnull,
                         "classification": "empty_housing_record_without_roster" if nonnull == 0 else "answered_housing_record_without_roster",
                         "original_roster_sources_checked": roster_sources, "original_roster_matches": 0,
                         "local_module_matches": local_matches, "raw_source_matches": hits[key],
                         "record_retained": True, "upstream_reason": "not_established"})
    require(Counter(r["classification"] for r in rows) == {
        "empty_housing_record_without_roster": 16, "answered_housing_record_without_roster": 3}, "Classification changed")
    if live:
        with connect_database({"dbname": "mda"}) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            connection.execute("SET LOCAL statement_timeout='30s'")
            actual = connection.execute('SELECT survey_wave,household_id,source_row_id,source_archive,source_submodule '
                'FROM cses_data."final_HO_CSES" WHERE hh_link_matched=0 ORDER BY survey_wave,household_id').fetchall()
            for row in actual:
                row["source_archive"] = source_archive(row["source_archive"])
            require(actual == [{k: r[k] for k in ("survey_wave", "household_id", "source_row_id", "source_archive", "source_submodule")}
                               for r in rows], "Live orphan identities differ from local evidence")
            count = connection.execute('SELECT count(*) AS n FROM cses_data."final_HO_CSES" h '
                'JOIN cses_data."final_HH_CSES" hh USING(survey_wave,household_id) WHERE h.hh_link_matched=0').fetchone()["n"]
            require(count == 0, "Link flag disagrees with actual live join")
    return {"audit_id": "cses-housing-orphan-audit-v1", "database_mutated": False, "live_read_only_verified": live,
            "input_sha256": inputs, "implementation_sha256": sha256_file(Path(__file__)),
            "scanned_sources": scanned, "rows": rows,
            "summary": {"orphan_rows": 19, "empty_housing_rows": 16, "answered_housing_rows": 3,
                        "original_roster_matches": 0, "automatic_repair_applied": False},
            "interpretation": "HH is roster-derived; source-key coverage differences predate this publication. No refusal, vacancy, typo or deletion cause is inferred."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    report = audit(root)
    write_json(root / OUTPUT, report)
    print(report["summary"], flush=True)


if __name__ == "__main__":
    main()
