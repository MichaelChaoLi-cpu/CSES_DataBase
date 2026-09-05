# Housing v4: approved 2021 lighting resolution

Published and independently validated on 2026-09-06 as `cses-housing-2021-resolution-v1`.
The user approved publication, preservation of the tenure anomaly, archival and subsequent
read-only housing-orphan diagnosis. No physical respondent value was changed.

## Interface and evidence contract

`cses_analysis.cses_housing_value_dictionary_v4` contains all 200 v3 entries unchanged plus
one new entry: 2021 `q04_07 = 8` maps to `biogas` / `Biogas`, covering six observations.
`cses_analysis.cses_housing_categories_v4` retains 77,922 rows and 66 columns, including all
50 original physical columns and 19 unmatched HH records. All non-null values of the three
reviewed housing fields across ten waves now match a dictionary entry; this is not whole-module
semantic certification or an analytical population definition.

The Khmer questionnaire and released Stata labels agree: code 8 is `ជីវឧស្ម័ន` (biogas),
code 9 is Other. The English questionnaire instead assigns Other to code 8 and has no code 9.
Both original `.xlsm` instruments are registered, with lighting and tenure questions in each
language (four questions). Raw option lines, exact cell locators, skip text, original-language
wording, both file hashes and the language-source conflict are retained. Macros are not executed.
Two previously empty source-variable links now point to the Khmer questions with `reviewed`
status; the English evidence remains separately queryable. The cause of the document conflict
is not established. Source preference is explicit, not silent overwriting of the English source.

The translation reference and original-cell details are preserved in the
[diagnosis](cses-housing-2021-diagnosis.md), which remains frozen pre-publication evidence.
Existing code 9 remains Other for all 38 corresponding observations. Earlier v1/v2/v3 views,
2017 transfer qualifications and 2014 draft qualifications are unchanged.

## Tenure anomaly remains explicit

One raw `q04_28 = 0` at source ordinal 6458 is outside the four defined tenure choices.
Its intended answer is unknown. Existing processing retains the raw archive but emits NULL in
the analytical source-code and harmonized fields; the existing issues file records that decision.
The new load-run validation summary additionally preserves the source-row identity, original 0,
`undocumented_out_of_range_source_code`, unknown intended response, and no-imputation treatment.
The four published 2021 tenure NULLs comprise three raw system-missing responses and this anomaly.

## Scope and safety

Publication inserted ten metadata records: one release, one source rule, one value definition,
one load run, two instruments and four questions. Only two existing source-question links were
updated, both previously empty. Two views were added with `mda_readonly` SELECT access; no schema,
physical table, compatibility view, original value or old mapping was replaced.

The resulting catalog has 1,746 variable mappings, 201 value mappings, nine releases/runs,
20 instruments, 171 questions and 296 source-question links. The 35 physical CSES tables and their
existing structures are protected by fingerprints; comparison masks only the three authorized
link columns on the two exact source variables, separately validating their new values.
External backups were fully decompressed and fingerprinted before the gated transaction.
Independent read-only validation checks every original housing cell, all dictionary associations,
per-wave coverage, the tenure anomaly, exact new records and view identities/definitions/ACLs.

## Current commands

```bash
uv run python rsc/cses_db/publish_cses_housing_2021.py validate --root .
uv run python rsc/cses_db/publish_cses_housing_2021.py export --root .
uv run python rsc/cses_db/audit_cses_housing_orphans.py --root .
```

The first two use the frozen release under `data/releases/cses-housing-2021-resolution-v1/`.
Graph v10 extends the prior graph with both-language evidence edges and actual v4 dependencies;
old graph files and historical validators remain unchanged. The third command is a read-only
diagnosis, not an automatic repair; see [housing orphan findings](cses-housing-orphan-diagnosis.md).

```sql
BEGIN READ ONLY;
SELECT survey_wave, canonical_name, source_value, source_label, category, evidence
FROM cses_analysis.cses_housing_value_dictionary_v4
WHERE survey_wave = '2021' AND canonical_name = 'main_lighting_source_code'
  AND source_value IN ('8', '9');
ROLLBACK;
```

Publication code and source evidence are bound by exact hashes, not retrospectively attributed
to an earlier Git commit. Git/DVC archival status is recorded separately in the release note.
