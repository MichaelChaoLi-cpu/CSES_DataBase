# CSES Housing Category Interface v1

This is the preserved v1 interface. For the current additive v3 interface and database validation,
see [recovered 2007/2013 evidence](cses-housing-recovered-evidence.md). The separately qualified
2017 transfer remains documented in [2017 alignment](cses-housing-2017-alignment.md).
The v1 validator remains frozen and intentionally rejects the later expanded catalog.

This implements step 2 of the accepted processing plan. It exposes the approved dictionary without
rewriting housing source-code fields or selecting an analytical sample.

## Interface contract

| View in `cses_analysis` | Grain | Expected rows | Purpose |
|---|---|---:|---|
| `cses_housing_value_dictionary_v1` | Source dataset / field / source code in the exact dictionary release | 140 | Labels, source-rule identity and qualified evidence |
| `cses_housing_categories_v1` | `survey_wave, household_id` | 77,922 | Original housing columns plus matched categories and statuses |

Both are ordinary, non-materialized views with security-barrier enabled. The existing `mda_readonly`
role receives SELECT; no new role, schema, physical table, or `public` compatibility view is created.
All prior physical data and metadata records are preserved. This does not add a seventh alignment
release or load run: it is an additive query-interface delivery over the existing sixth release.
Execution provenance is recorded in view comments, immutable local evidence, and the extended graph.

The category view retains the original 50 columns and adds 16 columns:

- `housing_dictionary_version`, fixed to `cses-housing-value-mapping-v1`;
- for each prefix `tenure`, `cooking_fuel`, and `lighting`: `_category`, `_label`, `_match_status`,
  `_variable_mapping_id`, and `_evidence`.

The three original fields remain `dwelling_tenure_source_code`, `main_cooking_fuel_source_code`, and
`main_lighting_source_code`. These are the existing published source-code columns, including the
previously approved 2004 lighting sentinel correction. The interface does not undo that correction
or replace these fields with categories.

## Matching and interpretation

| Match status | Meaning | Category / label / rule / evidence |
|---|---|---|
| `matched` | An approved entry matches the exact release, wave, source archive/member, field and code | Present |
| `unmapped_nonnull` | Published source code is non-null but no exact approved dictionary entry matches | NULL; original code remains |
| `source_null` | Existing published source-code field is SQL NULL | NULL; raw missingness reason is not inferred |

Three LEFT JOINs preserve every housing row, including all 19 unmatched HH records. The view has no
sample filter or implicit household join. Key uniqueness and row-by-row original-column equality
are verified before commit. Source archive matching recognizes the already accepted anchored
`data/raw/CSE/` → `data/raw/` comparison normalization, but `h.*` preserves database paths unchanged.
Archive-member paths are exact, including nested-member notation; wave/code alone is insufficient.

The dictionary view selects only `cses-housing-value-mapping-v1` and its approved source rules/values.
It combines live normalized dictionary records with immutable approved review qualifications embedded
in the versioned view definition. That evidence contains review identities, exact source keys,
questionnaire provenance/options, historical flags, skip annotations and interpretation notes. It does
not invent a Stata label when the underlying evidence is a questionnaire option.

The 2014 draft stays provisional. Wave-specific residual categories, compound options and eligibility
limitations stay explicit. A matched label does not prove common cross-wave denominators, grid access,
clean fuel or another derived analytical concept. NULL does not establish non-response or inapplicability.

The 2007/2013/2017 values remain non-null but unmatched where no approved entry exists. Six 2021
lighting observations also remain unmatched. The 52 unresolved and 16 missing-only review code entries
are not silently promoted into the dictionary.

## Read-only use

Start with coverage, not pooled percentages:

```sql
BEGIN READ ONLY;
SELECT survey_wave, lighting_match_status, count(*) AS housing_records
FROM cses_analysis.cses_housing_categories_v1
GROUP BY survey_wave, lighting_match_status
ORDER BY survey_wave, lighting_match_status;

SELECT survey_wave, canonical_name, source_value, source_label, category, label,
       variable_mapping_id, dictionary_version, evidence
FROM cses_analysis.cses_housing_value_dictionary_v1
WHERE survey_wave = '2014'
ORDER BY canonical_name, source_value;
ROLLBACK;
```

Select only needed fields for large household queries: evidence JSON is repeated for matching rows.
The compact dictionary view is the preferred place to inspect code-level evidence. Weight choice,
eligible population, unmatched-row treatment and time anchor remain explicit analytical decisions.

## Historical publication and v1-state validation

```bash
uv run python rsc/cses_db/publish_cses_housing_interface.py prepare --root . \
  --backup-dir /Volumes/MikesDataBackup/PG_DB
uv run python rsc/cses_db/publish_cses_housing_interface.py apply --root . \
  --apply --execution-sha256 <literal verified execution SHA-256>
uv run python rsc/cses_db/publish_cses_housing_interface.py validate --root .
```

Preparation requires both names to be absent and checks for DDL event triggers. It opens a forced
read-only transaction, verifies the existing 35-table baseline and dictionary release, then tests both
prospective queries. It compares every category/status/label/rule identity against an independently
keyed approved-plan lookup, every original housing row against the base relation, and all 140 evidence
objects against their approved records. The external schema-only dump covers existing `cses_analysis`
definitions, not respondent data or all of `mda`; full decompression and file hash are verified.

The execution manifest binds query fingerprints, exact code/input hashes, the accepted inventory,
backup and pre-existing protected state. Its recorded base Git revision can precede new code; it is
not a claim that uncommitted files have already been archived. This workflow does not run Git or DVC
synchronization automatically.

Application requires the literal manifest hash, locks protected tables and rechecks the baseline.
Only two CREATE VIEW statements, their comments and SELECT grants are authorized. There is no
CREATE OR REPLACE, DML, new metadata release, or overwrite. All view results are checked against
preflight before commit. The existing physical and structural snapshot must remain identical after
excluding only these two authorized view definitions. The actual `mda_readonly` role must read both
views with the exact expected counts. A validation failure rolls back the DDL transaction.

Independent validation uses a new forced read-only transaction. It checks view OIDs, owner/ACL,
security options, definitions and comments against the import evidence, plus all interface results
and pre-existing protected state. Old dictionary-only validators are historical after these views
exist, because their structural snapshot intentionally excludes no new views. Use the command above
for the new current state; never weaken the old implementation or overwrite its evidence.

All execution, import and validation records live under `data/releases/cses-housing-interface-v1/`.
If a process fails after commit but before writing the local import record, do not retry with replace
or drop: inspect the exact live view definitions and transaction outcome first. An ordinary apply
retry refuses existing target names; a completed delivery is checked with validate instead.

Recovery is additive-scope work: no existing table needs restoration merely to remove an interface.
Dropping views or restoring definitions requires a separately confirmed exact target/dependency check;
never restore the schema dump blindly over newer database state.

## Lineage extension

```bash
uv run python rsc/cses_db/publish_cses_housing_interface.py export --root .
uv run python rsc/cses_db/publish_cses_housing_interface.py export --root . \
  --output-dir .pytest_cache/housing_interface_graph_replay
```

The exporter preserves the exact base graph v6 and adds two analysis-view nodes plus catalog-relation
nodes and dependency edges discovered from PostgreSQL. The new outputs are
`data/lineage/cses_lineage_graph_v7.json` and `data/lineage/cses_housing_interface_topology_v1.json`.
They are immutable, read-only projections; a repeated export must be byte-identical. The legacy
exporter does not discover these unregistered analysis interfaces; use this extension for v7.
