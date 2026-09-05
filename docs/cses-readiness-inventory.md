# CSES Core Table Readiness: Inventory and Work Queue

Current update (2026-09-06): [v4](cses-housing-2021-resolution.md) adds the six-observation 2021
biogas mapping; the tenure 0 anomaly is retained explicitly. All non-null values of the three
reviewed housing fields now match. The [orphan diagnosis](cses-housing-orphan-diagnosis.md) explains
the 19 unmatched keys as absent original roster coverage, split into 16 empty and three answered
housing records. No repair or deletion was applied. The inventory below remains historical;
current validation is `publish_cses_housing_2021.py validate --root .`.

This implements step 1 of the accepted processing plan: a read-only table/field/wave inventory.
It is not a new database release, semantic approval, or declaration that all fields are analysis-ready.

The inventory and queue below describe their frozen pre-interface state. Subsequent
[v3 housing publication](cses-housing-recovered-evidence.md) resolves the 2007/2013 meanings from
primary evidence and retains the separately user-approved 2017 transfer. Three housing fields now
have dictionary definitions in all ten waves (200 entries); the six 2021 lighting observations and
raw tenure-code-0 interpretation remain unresolved. Other modules and denominator decisions remain
in the queue. Use `publish_cses_housing_recovered.py validate --root .` for current database checks;
do not rerun this historical inventory against the expanded catalog or overwrite its evidence.

## Current table inventory

| Module | Physical table in `cses_data` | Rows | Fields | Observed waves |
|---|---|---:|---:|---:|
| Household | `final_HH_CSES` | 77,904 | 35 | 10 |
| Member | `final_HL_CSES` | 358,920 | 37 | 10 |
| Education | `final_ED_CSES` | 343,204 | 30 | 10 |
| Housing | `final_HO_CSES` | 77,922 | 50 | 10 |
| Employment | `final_EC_CSES` | 332,903 | 60 | 10 |
| Village/PSU | `final_VL_CSES` | 5,718 | 40 | 8 |
| Survey date | `final_SURVEY_DATE_CSES` | 77,904 | 28 | 10 |

The matrix contains all 280 fields across all ten catalog waves: 2,800 cells. VL lacks 2013 and 2017,
accounting for 80 absent-wave cells; those are not 80 all-null columns. Of the remaining 2,720 cells,
1,574 are fully observed, 813 are partly observed, and 333 are all-null. These describe availability,
not semantic completion; all-null does not establish missingness, inapplicability or non-collection.

The HH Parquet has 32 base fields. The inventory reconstructs its three previously published actual-date
components in memory from SURVEY_DATE using a checked one-to-one household join. It does not rewrite
either artifact. The resulting 35 columns match the database order and catalog types.

## What was actually checked

- All five existing local module validators passed, covering all six non-date core modules.
- All seven live tables have the expected ordered columns, catalog types, row counts, non-null natural
  keys and unique natural keys. Each field's non-null count agrees between local data and PostgreSQL
  in every wave. Local distinct-value counts are reported separately, not claimed as live comparisons.
- Six directional cross-table relationships were checked independently in local data and PostgreSQL.
  No inner join, row deletion or data replacement was performed.
- Actual-date coverage matches the existing explicit-date contract: 14,984 households in 2004,
  10,041 in 2019 and 10,080 in 2021; the other seven waves have no exact household date in this artifact.
- The live metadata projection exactly matches accepted graph v6. All 163 records in the housing
  dictionary release match the approved plan, including their release/version bindings.
- Field rows retain their source labels, question-link evidence, definitions, historical rule IDs and
  versions. A question link can be provisional and does not certify exact wording or comparability.

There are direct source-rule records in 1,459 field-wave cells and question links in 217 cells. These
are neither completion percentages nor counts of source variables: derived/context/provenance fields
can legitimately lack direct source rules, and historical versions are retained. The inventory does
not select an effective transformation merely by taking the highest mapping ID.

The dictionary covers 21 field-wave cells (three housing fields in seven waves). Other fields can
already contain inherited harmonization; absence of a normalized value dictionary is not evidence
that no transformation exists. Their builder definitions and validator results are retained, but their
units, eligibility, missingness and cross-wave meaning are not newly certified by this inventory.

This aggregate inventory does **not** perform a fresh raw-data rebuild or a full seven-table cell-by-cell
comparison. Those guarantees must not be inferred from matching counts. The separate current
publication validator provides the existing protected-table fingerprints and full housing/local check.

## Prioritized work queue

| ID | Scope and observed evidence | Impact / next action | Decision boundary |
|---|---|---|---|
| HO-01 | Housing has 19 records without HH matches: 16 in 2004, one in 2009, two in 2014 | Preserve housing rows and linkage flags in the analysis interface; make denominator effects visible | Do not silently inner-join or discard records |
| HO-02 | Tenure, cooking and lighting lack approved mappings in 2007/2013/2017; six 2021 lighting observations remain unmatched | Retain raw code, explicit unmatched status and source evidence; investigate the unresolved labels separately | No borrowing meanings from nearby waves |
| HO-03 | 140 approved code entries retain draft, skip, compound and residual qualifications | Select the exact release and expose qualifiers alongside categories | No blanket cross-wave comparability assertion |
| HH-01 | General household/person weights are absent from the selected 2004 core sources; later core weights pass positive/complete checks | Document weight availability and confirm the intended estimator and eligible sample before weighted analysis | Do not fill missing weights with 1 or reuse another wave's weights |
| HL-01 | Existing validator retains 11 missing relationship values, 129 missing absence values and one household without exactly one coded head | Review population/household definitions before using head attributes or membership restrictions | No invented head or membership recoding |
| ED-01 | Four education records do not link to HL: one in 2013 and three in 2014 | Retain records; review age/eligibility, education categories and denominators next | No deletion to force referential integrity |
| EC-01 | Two employment records do not link to HL: one each in 2014 and 2016 | Retain records; review reference periods, eligibility, units and classification changes | Do not treat all waves' employment questions as equivalent |
| VL-01 | Village table has eight waves, excluding 2013/2017 | Record module coverage; distinguish absent waves from null values | No fabricated village rows |
| VL-02 | HH is not unique by wave/PSU; VL validator retains 120 age-component and 116 sex-component mismatches | Deduplicate/aggregate household PSU keys before joining; preserve released totals and discrepancies | No direct one-to-one assumption or automatic balancing |
| DATE-01 | Exact household dates exist only in 2004/2019/2021; candidate reference date is not an adopted exposure anchor | Preserve precision and date role; choose an analytical time anchor explicitly if needed | No imputed interview day from nominal year or operational timestamps |

Counts of issues, code entries and field observations are not additive respondent populations.
The 52 unresolved review codes and 16 missing-only codes remain outside the substantive dictionary.
NULL rows are reported separately; the inventory does not infer the raw reason behind each SQL NULL.

## Next module: housing interface contract

Step 2 has subsequently been implemented as two additive views. The contract below remains the
inventory's handoff boundary; see the [interface runbook](cses-housing-interface-runbook.md) and
[publication record](releases/cses-housing-interface-v1.md) for the newer current state.

Step 2 should first define a housing-grain interface with one row per `survey_wave, household_id` and
77,922 input rows. Its proposed contract should retain the raw source codes for the three reviewed
fields and add release-selected category, match state and evidence qualifications. At minimum,
distinguish a matched code, an unmatched non-null code, and a published NULL with no inferred reason.

Keep all ten waves, all housing rows and the HH linkage indicator visible. A category view must not
implicitly choose an analytical population, suppress provisional evidence, or multiply rows through
historical mapping versions. Verify join cardinality and per-wave coverage before publishing any view.
Use the existing `cses_analysis` schema if a view is subsequently approved; no new schema is needed.
No view or new database field is created by this inventory.

After the housing sample, continue with household/member foundations, education/employment, then
village/date semantics. Resolve the work-queue items with evidence and keep genuinely unresolved
states visible; it is not necessary to invent answers to make a module appear complete.

## Reproduce and inspect

```bash
uv run python rsc/cses_db/inventory_cses_readiness.py --root .
uv run python rsc/cses_db/inventory_cses_readiness.py --root . \
  --output-dir .pytest_cache/readiness_inventory_v1_replay
cmp data/processing/cses/readiness_inventory_v1/inventory.json \
  .pytest_cache/readiness_inventory_v1_replay/inventory.json
cmp data/processing/cses/readiness_inventory_v1/inventory.md \
  .pytest_cache/readiness_inventory_v1_replay/inventory.md
```

The live transaction is forced `REPEATABLE READ, READ ONLY`, with a per-statement timeout. The program
runs local validators, reads the existing local release and catalog, and writes only the new report
directory. Both files are immutable when present: differing outputs require a new directory/version.
Identical input hashes, base Git revision, implementation and database state produce identical output.
Changing Git/DVC state can change provenance, so use a fresh output directory for later inventories.

The initial run and independent replay passed and produced byte-identical JSON and Markdown outputs.
All 75 repository tests passed, including ten inventory regression cases; Ruff passed on the new code
and tests. The current publication validator was also rerun successfully in a separate read-only
transaction, checking all 35 protected tables and full housing/local equality against its accepted state.

The machine-readable [inventory](../data/processing/cses/readiness_inventory_v1/inventory.json) records
all 2,800 cells, input/implementation hashes, validator output, live key/profile checks and linkage
counts. The [readable checklist](../data/processing/cses/readiness_inventory_v1/inventory.md) includes
the full field-wave matrix and housing code-coverage summary. The code hash identifies the exact
implementation; its recorded base Git commit is not proof that newly written code was committed.

Git owns the program, tests and this document. Generated inventory files belong to the existing DVC
`data/` unit; this step does not run Git commits/pushes or DVC add/push. Older release evidence and
database graph v6 remain unchanged.
