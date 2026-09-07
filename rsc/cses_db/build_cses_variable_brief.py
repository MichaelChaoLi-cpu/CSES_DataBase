#!/usr/bin/env python3
"""Generate an aggregate-only variable brief with explicit units and review boundaries."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd
from cses_baseline_metadata import connect_database
from inventory_cses_readiness import availability, link_inventory, local_frames, profile_database
from organize_cses_questionnaires import WAVES, digest, write_once
from plan_cses_age_topcode import checked_review, require
from psycopg import sql

SELF = "rsc/cses_db/build_cses_variable_brief.py"
OUTPUT = "data/processing/cses/variable_brief_v1"
TABLES = {"HH": ("household_id", "household-wave"), "HL": ("person_id", "member-wave"),
          "ED": ("person_id", "education-record-wave"), "HO": ("household_id", "housing-record-wave"),
          "EC": ("person_id", "employment-record-wave"), "VL": ("psu", "village/PSU-wave"),
          "SURVEY_DATE": ("household_id", "household-date-record-wave")}
HO_FIELDS = {"dwelling_tenure_source_code", "main_cooking_fuel_source_code", "main_lighting_source_code"}
MEMBER_FIELDS = {"sex", "age", "relationship_to_household_head", "absent_from_household"}


def assessment(table, field):
    if table == "final_HO_CSES" and field in HO_FIELDS:
        return "published_code_definitions_all_10_waves_with_qualifications"
    if table == "final_HL_CSES" and field in MEMBER_FIELDS:
        return "reviewed_member_foundations_scope_limited"
    if field in {"age", "household_head_age"} and table in {"final_ED_CSES", "final_EC_CSES", "final_HH_CSES"}:
        return "published_2004_age_qualification_other_waves_not_certified"
    return "baseline_standardization_present_semantic_reaudit_pending"


def keyed_union(frames, modules, key):
    parts = [frames[f"final_{m}_CSES"][["survey_wave", key]] for m in modules]
    return pd.concat(parts, ignore_index=True).dropna().drop_duplicates().reset_index(drop=True)


def make_report(root):
    checked_review(root)
    tables = [f"final_{m}_CSES" for m in TABLES]
    frames = local_frames(root, tables)
    registry = json.loads((root / "data/processing/cses/questionnaire_alignment_v1/registry.json").read_text())
    canonicals = {(r["target_table"], r["canonical_name"]): r for r in registry["canonical_variables"]}
    field_waves, summaries, links = [], [], []
    with connect_database({"dbname": "mda"}) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        conn.execute("SET LOCAL statement_timeout='55s'")
        require(conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on", "Read-only required")
        for module, (key, unit) in TABLES.items():
            table = f"final_{module}_CSES"
            frame = frames[table]
            columns = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='cses_data' AND table_name=%s ORDER BY ordinal_position", (table,)).fetchall()
            require([r["column_name"] for r in columns] == list(frame.columns), f"Column order changed: {table}")
            profiles, integrity = profile_database(conn, table, list(frame.columns), ["survey_wave", key])
            require(integrity["rows"] == len(frame), "Local/database row count differs")
            for field in frame.columns:
                require((table, field) in canonicals, f"Missing canonical field: {table}/{field}")
                for wave in WAVES:
                    values = frame.loc[frame.survey_wave.eq(wave), field]
                    total, nonnull = len(values), int(values.notna().sum())
                    live = profiles.get(wave, {})
                    require(live.get("_rows", 0) == total and live.get("_survey_wave_nonnull" if field == "survey_wave" else field, 0) == nonnull, "Field-wave nonnull mismatch")
                    field_waves.append({"table": table, "field": field, "wave": wave, "unit": unit,
                        "rows": total, "nonnull": nonnull, "null": total - nonnull,
                        "distinct_nonnull": int(values.nunique()), "availability": availability(total, nonnull),
                        "review_status": assessment(table, field), "full_cross_wave_semantic_certification": False})
            summaries.append({"table": table, "module": module, "unit": unit, "rows": len(frame),
                "fields": len(frame.columns), "observed_waves": int(frame.survey_wave.nunique()), "natural_key": ["survey_wave", key],
                "unique_keys": len(frame.drop_duplicates(["survey_wave", key])),
                "wave_rows": {w: int(frame.survey_wave.eq(w).sum()) for w in WAVES},
                "actual_interview_respondent_count": None,
                "note": "Released records; not certified counts of directly interviewed people or eligible analytic respondents."})
        links = link_inventory(conn, frames)
        people = keyed_union(frames, ["HL", "ED", "EC"], "person_id")
        households = keyed_union(frames, ["HH", "HO", "SURVEY_DATE"], "household_id")
        unions = {}
        for name, modules, key, local in [("person_wave_union", ["HL", "ED", "EC"], "person_id", people),
                                         ("household_wave_union", ["HH", "HO", "SURVEY_DATE"], "household_id", households)]:
            union = sql.SQL(" UNION ").join(sql.SQL("SELECT survey_wave,{} FROM {}").format(sql.Identifier(key), sql.Identifier("cses_data", f"final_{m}_CSES")) for m in modules)
            live = conn.execute(sql.SQL("SELECT survey_wave,count(*) AS n FROM ({}) u GROUP BY survey_wave ORDER BY survey_wave").format(union)).fetchall()
            counts = {w: int(local.survey_wave.eq(w).sum()) for w in WAVES}
            require({r["survey_wave"]: r["n"] for r in live} == counts, "Composite-key union mismatch")
            unions[name] = {"rows": len(local), "wave_rows": counts, "key": ["survey_wave", key],
                           "longitudinal_unique_people": None, "actual_interview_respondents": None}
        dictionary = conn.execute("SELECT survey_wave,canonical_name,count(*) AS entries FROM cses_analysis.cses_housing_value_dictionary_v4 GROUP BY survey_wave,canonical_name ORDER BY survey_wave,canonical_name").fetchall()
        coverage = conn.execute("""SELECT survey_wave,count(*) AS rows,
          count(*) FILTER (WHERE tenure_match_status='unmapped_nonnull') AS tenure_unmatched,
          count(*) FILTER (WHERE cooking_fuel_match_status='unmapped_nonnull') AS cooking_unmatched,
          count(*) FILTER (WHERE lighting_match_status='unmapped_nonnull') AS lighting_unmatched
          FROM cses_analysis.cses_housing_categories_v4 GROUP BY survey_wave ORDER BY survey_wave""").fetchall()
        require(sum(r["entries"] for r in dictionary) == 201 and len(dictionary) == 30, "Housing dictionary scope changed")
        require(all(r["tenure_unmatched"] == r["cooking_unmatched"] == r["lighting_unmatched"] == 0 for r in coverage), "Unmatched substantive housing code")
        age = conn.execute("SELECT survey_wave,age_2004_status,count(*) AS n FROM cses_analysis.cses_hl_age_v1 GROUP BY survey_wave,age_2004_status ORDER BY survey_wave,age_2004_status").fetchall()
        catalog = conn.execute("""SELECT (SELECT count(*) FROM cses_alignment.cses_canonical_variable) AS canonical_fields,
          (SELECT count(*) FROM cses_alignment.cses_source_variable) AS source_variables,
          (SELECT count(*) FROM cses_alignment.cses_question) AS questions,
          (SELECT count(*) FROM cses_alignment.cses_source_variable WHERE question_id IS NOT NULL) AS question_links""").fetchone()
        require(catalog == {"canonical_fields": 280, "source_variables": 4092, "questions": 171, "question_links": 296}, "Catalog changed since current release")
    fields = []
    for (table, field), canonical in sorted(canonicals.items()):
        values = frames[table][field]
        rows = [r for r in field_waves if r["table"] == table and r["field"] == field]
        fields.append({"table": table, "field": field, "definition": canonical["canonical_definition"],
            "measure_type": canonical["measure_type"], "catalog_status": canonical["status"],
            "unit": TABLES[table.removeprefix("final_").removesuffix("_CSES")][1],
            "nonnull": int(values.notna().sum()), "null": int(values.isna().sum()), "rows": len(values),
            "distinct_nonnull_local": int(values.nunique()),
            "waves_with_nonnull": [r["wave"] for r in rows if r["nonnull"]],
            "review_status": assessment(table, field), "full_cross_wave_semantic_certification": False})
    require(len(fields) == 280 and len(field_waves) == 2800, "Complete 280-field/2800-cell inventory required")
    return {"brief_id": "cses-variable-brief-v1", "snapshot_scope": "Post age-interface v1, before reviewed questionnaire-batch publication",
        "implementation_sha256": digest((root / SELF).read_bytes()), "review_sha256": digest((root / "data/processing/cses/questionnaire_review_v1/review.json").read_bytes()),
        "parquet_sha256": {t: digest((root / f"data/processing/cses/{t}.parquet").read_bytes()) for t in tables},
        "tables": summaries, "fields": fields, "field_waves": field_waves, "links": links,
        "union_counts": unions, "catalog_counts": catalog, "housing_dictionary": dictionary, "housing_coverage": coverage,
        "age_status_counts": age, "availability_counts": dict(Counter(r["availability"] for r in field_waves)),
        "strict_global_certified_variables": 0, "certification_note": "No unrestricted all-ten-wave analytic certification is asserted. This is not a claim that inherited transformations are incorrect or unusable.",
        "transaction_read_only": True, "database_mutated": False, "individual_records_in_report": False}


def md(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def documents(report):
    lines = ["# CSES variable brief", "", "Snapshot: after publication of the 2004 age-96+ interface, before the proposed 15-question-link batch.", "",
        "## What is aligned?", "",
        "All 280 physical-table fields have inherited standardized definitions and pass current key/availability checks. "
        "That is technical alignment, not proof that choices, units, eligibility, reference periods and denominators are identical across years.", "",
        "**No variable is claimed here to have unrestricted, fully certified analytical comparability across all ten waves.** "
        "The completed scopes below are useful and explicitly bounded; zero blanket certifications does not mean zero usable data.", "",
        "| Variable / scope | Completed work | Remaining interpretation boundary |", "| --- | --- | --- |",
        "| HO dwelling_tenure_source_code, main_cooking_fuel_source_code, main_lighting_source_code | Published definitions in all ten waves: 201 dictionary entries; all non-null source codes matched | Draft/skip/compound categories, 2017 approved transfer, 2021 language conflict, raw tenure-0 anomaly and housing orphans retained; no common denominator certified |",
        "| HL sex | Question and 1=Male / 2=Female correspondence checked in 2004, 2009, 2011-12, 2013, 2016, 2021 | New question links planned, not published. 2014 draft; 2007/2017 household form gaps; 2019 transcription pending |",
        "| HL age; ED/EC age; HH household_head_age | Published 2004 age-96+ qualification in four additive views | 3 distinct people are lower-bounded at 96, not exact age; other years outside that rule |",
        "| HL relationship_to_household_head | Full 15-choice source lists checked in seven English forms | Literal Great/grand-child note differs; 2014 draft and three untranscribed/unavailable waves remain |",
        "| HL absent_from_household | Coding polarity and questionnaire routing checked | 2004 current absence differs from later last-week presence; reference periods must remain separate |",
        "| Other ED, EC, VL, date and derived/context fields | Existing transformations, definitions and availability inventoried | Variable-specific semantic re-audit remains pending; date/identifier fields need contracts rather than response options |", "",
        "The proposed 9 substantive question links, 6 sex question links and 7 identifier provenance rows are evidence-registration work, not 22 newly fully aligned analytical variables.", "",
        "## Population and respondent counts", "",
        "Counts below are unweighted released record counts. A member can be reported by a household proxy. "
        "A record is not proof that this person answered a questionnaire or every question. Actual unique interview-respondent counts "
        "are not established. Cross-wave person/household identifiers are not validated longitudinal identities.", "",
        "| Table | Statistical unit | Records / unique within-wave keys | Fields | Waves |", "| --- | --- | ---: | ---: | ---: |"]
    for t in report["tables"]:
        lines.append(f"| {t['table']} | {t['unit']} | {t['rows']:,} | {t['fields']} | {t['observed_waves']} |")
    unions = report["union_counts"]
    lines += ["", f"HL/ED/EC composite-key union: **{unions['person_wave_union']['rows']:,} person-wave records**. "
        f"HH/HO/date union: **{unions['household_wave_union']['rows']:,} household-wave records**. "
        "These are deduplicated across the stated tables within a wave, not unique humans/households followed across years. "
        "Do not sum the seven table totals or include village rows in a person count.", "",
        "| Wave | HH | HL | ED | HO | EC | VL | Date | Person-wave union |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    by_module = {t["module"]: t for t in report["tables"]}
    for w in WAVES:
        lines.append("| " + " | ".join([w, *[f"{by_module[m]['wave_rows'][w]:,}" for m in TABLES], f"{unions['person_wave_union']['wave_rows'][w]:,}"]) + " |")
    lines += ["", "## Key variables: available records", "",
        "Non-null counts describe stored observations, not substantive choices or eligible respondents. Distinct values are local observed values, "
        "not questionnaire option counts (IDs and numeric ages have no finite-choice interpretation).", "",
        "| Table | Field | Non-null / records | Null | Known questionnaire choices / rule |", "| --- | --- | ---: | ---: | --- |"]
    for f in report["fields"]:
        if (f["table"] == "final_HO_CSES" and f["field"] in HO_FIELDS) or (f["table"] == "final_HL_CSES" and f["field"] in MEMBER_FIELDS):
            choices = {"sex": "2 in inspected forms", "age": "Numeric; 2004 top-code 96+", "relationship_to_household_head": "15 in inspected forms", "absent_from_household": "2; polarity and period differ"}.get(f["field"], "Wave-specific dictionary; no pooled option count")
            lines.append(f"| {f['table']} | {f['field']} | {f['nonnull']:,} / {f['rows']:,} | {f['null']:,} | {choices} |")
    sex = next(f for f in report["fields"] if f["table"] == "final_HL_CSES" and f["field"] == "sex")
    sex_waves = [r for r in report["field_waves"] if r["table"] == sex["table"] and r["field"] == "sex" and r["wave"] in {"2004", "2009", "2011-12", "2013", "2016", "2021"}]
    lines += ["", f"The six ready-for-link sex waves contain {sum(r['rows'] for r in sex_waves):,} member records and "
        f"{sum(r['nonnull'] for r in sex_waves):,} non-null sex values; this is a bounded evidence scope, not all-wave certification.", "",
        "## Important analytical constraints", "",
        "- 2004 general household/person weights are absent in the selected core sources. Do not substitute 1 or borrow weights.",
        "- Household membership includes usually residing members and absences under 12 months; it is not the number present last week.",
        "- ED/EC table sizes are not automatically the eligible analysis denominators. Review wave-specific age gates, skips and reference periods before calculating rates.",
        "- Housing preserves unmatched households; do not silently inner-join them away. Village joins to households require deduplicated PSU keys.",
        "- Exact household dates are available only for 2004, 2019 and 2021 in the accepted date contract. Do not turn survey year into an exact interview day.",
        "- Missing cells, absent modules, structural skips and unanswered questions are distinct. The report does not infer a missingness reason from NULL.", "",
        "| Retained unmatched relationship | Wave | Unmatched records |", "| --- | --- | ---: |"]
    for link in report["links"]:
        for w in link["waves"]:
            if w["unmatched_rows"]:
                lines.append(f"| {link['child_table']} → {link['parent_table']} | {w['survey_wave']} | {w['unmatched_rows']} |")
    lines += ["", "## Full variable inventory and reproducibility", "",
        "- [All 280 fields with definitions, counts and review status](cses-variable-inventory.md)",
        "- [Machine-readable 2,800 field-wave cells, unit counts and live checks](../data/processing/cses/variable_brief_v1/brief.json)",
        "- [Questionnaire batch publication plan](cses-questionnaire-batch-plan.md)",
        "- [Housing interface](cses-housing-2021-resolution.md) and [age interface](cses-age-topcode.md)", "",
        "The report uses a forced repeatable-read/read-only database transaction. Every field-wave row/non-null count and table key is compared "
        "with local artifacts; person/household union counts and linkage exceptions are checked independently in PostgreSQL. "
        "It does not claim a new full raw-data rebuild or row-level validation of every skip. Original questionnaire/age review hashes and inputs "
        "are pinned. No individual respondent rows are saved in the report. Physical-field count excludes additive view columns.", ""]
    appendix = ["# CSES complete variable inventory", "", "Companion to the [variable brief](cses-variable-brief.md). "
        "All counts are unweighted records at the table's grain. Catalog approval of an inherited mapping does not equal a new unrestricted semantic certification. "
        "Detailed wave-specific denominators and NULL counts are in [brief.json](../data/processing/cses/variable_brief_v1/brief.json).", "",
        "Review codes: `housing-qualified` = all-ten-wave source code coverage with retained limits; `member-reviewed` = seven-form foundation review; "
        "`age-2004` = published bounded top-code qualification; `baseline/pending` = inherited standardization, variable-specific re-audit pending.", ""]
    labels = {"published_code_definitions_all_10_waves_with_qualifications": "housing-qualified", "reviewed_member_foundations_scope_limited": "member-reviewed",
              "published_2004_age_qualification_other_waves_not_certified": "age-2004", "baseline_standardization_present_semantic_reaudit_pending": "baseline/pending"}
    for t in report["tables"]:
        appendix += [f"## {t['table']}", "", f"Unit: {t['unit']}. {t['rows']:,} records; {t['fields']} fields.", "",
            "| Field | Non-null / total | Observed distinct | Non-null waves | Review | Existing definition |", "| --- | ---: | ---: | --- | --- | --- |"]
        for f in report["fields"]:
            if f["table"] == t["table"]:
                appendix.append(f"| {f['field']} | {f['nonnull']:,} / {f['rows']:,} | {f['distinct_nonnull_local']:,} | {', '.join(f['waves_with_nonnull']) or 'None'} | {labels[f['review_status']]} | {md(f['definition'])} |")
        appendix.append("")
    return "\n".join(lines), "\n".join(appendix)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, default=Path(OUTPUT))
    parser.add_argument("--docs-dir", type=Path, default=Path("docs"))
    args = parser.parse_args()
    report = make_report(args.root)
    brief, appendix = documents(report)
    write_once(args.root / args.output / "brief.json", report)
    write_once(args.root / args.docs_dir / "cses-variable-brief.md", brief)
    write_once(args.root / args.docs_dir / "cses-variable-inventory.md", appendix)
    print(json.dumps({"fields": len(report["fields"]), "field_waves": len(report["field_waves"]), "union_counts": report["union_counts"]}))


if __name__ == "__main__":
    main()
