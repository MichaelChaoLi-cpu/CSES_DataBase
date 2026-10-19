# CSES Database Build Infrastructure

This directory contains the reusable local build inherited from the validated `MJ02b` CSES work.
Its historical baseline uses eleven byte-identical archives from that project. Five additional
archives now have a separate [qualified publication workflow](../../docs/cses-additional-waves.md).
Use `build_cses_additional_waves.py`, not the historical builders, for those new waves.

The [published health screening interface](../../docs/cses-health-screen-interface.md),
release 28, uses `publish_cses_health_screen_v2.py`. Publication adds two tables, five views,
197 source-output edges and release/storage/load metadata. The frozen first formal executor
stopped on a redundant orphan anti-join uniqueness query; revision 2 retains full exact-row
and unique-key validation, uses new-table statistics and preserves all SQL and source values.
Normal operations are read-only: `publish_cses_health_screen_v2.py validate` and
`validate_cses_health_screen_native.py` (fresh native-source and independent scalar checks).
Do not rerun publication or use the superseded first executor's rehearsal/validation actions.

For the [local fifteen-wave health screening pilot](../../docs/cses-health-all-waves-pilot.md),
`pilot_cses_health_all_waves.py` preserves the initial native-source candidate and
`pilot_cses_health_all_waves_v2.py` adds separately checked 2012 questionnaire evidence.
Use `validate_cses_health_all_waves.py --database` for the prerequisite first acceptance,
then `validate_cses_health_all_waves_v2.py --database` for the current candidate. Native-source
and scalar checks are independent of the vector classifier; database transactions are forced
read-only. These scripts have no publication action. Do not mix four-week concepts, adjudicate
the 2019 option conflict, borrow a form for 2017 or turn missing health rows into healthy No.

For the separate [health-screen preflight](../../docs/cses-health-screen-preflight.md),
`rebuild_cses_questionnaire_archive_cache.py` preserves v1 and builds a fully checked cache.
`audit_cses_health_release.py` checks annual native inputs and full negative-screen skip ranges;
`audit_cses_health_database_inputs.py` records missing stored branch inputs with read-only SQL.
`prepare_cses_health_screen_interface.py` supplies `build` and `prepare` for the frozen v2
preflight. Its old `rehearse` action stopped on canonical-JSON object ordering and is retained
only as historical code: use `rehearse_cses_health_screen_v3.py build` then `rehearse` instead.
The revised plan adds a five-wave native-input bridge, and rehearsal unconditionally rolls back.
There is deliberately no production publication or formal registry action in this tool.

For the published [fifteen-wave education interface](../../docs/cses-education-unified-interface.md),
`publish_cses_education_unified.py` has separate `build`, `prepare`, `rehearse`, `publish`
and read-only `validate` actions. It pins the accepted pilot and creates only additive
objects, with a full backup and matching rollback receipt required before publication.
The independent SQL policy lives in `cses_education_all_waves_sql.py`.
`validate_cses_education_unified.py` independently checks fresh native inputs and scalar
decisions; add `--database` for read-only published/source/geography acceptance. Release 26
is already committed: use only the two validation paths, not another publication attempt.
Keep the 2017 withholding, positive-years conflict guard and separate four-record orphan audit.

The [fifteen-wave local education prototype](../../docs/cses-education-all-waves-pilot.md)
uses `pilot_cses_education_all_waves.py` for native verification and the first immutable
candidate, then `pilot_cses_education_all_waves_v2.py` for the current positive-years conflict
guard. Use `validate_cses_education_all_waves.py --database` for the prerequisite first receipt
and `validate_cses_education_all_waves_v2.py --database` for current independent acceptance.
Database transactions are forced read-only under `mda_readonly`; there is no publication action.
Keep the 2017 form gap, raw responses, four ED orphans and all old interfaces intact.

For [literacy and observed school years](../../docs/cses-additional-literacy-years.md),
`align_cses_additional_literacy_years.py` builds 20 field-wave rules and the local projection.
Run `validate_cses_additional_literacy_years.py --local` before the separate publication
preflight/backup/rehearsal actions in `publish_cses_additional_literacy_years_v2.py`. After
publication use only its `validate` action and the independent validator without `--local`.
Do not split legacy combined answers, recode undefined writing 0 to No, or impute skipped
school years from a gate or grade. Existing outputs and source catalogs remain unchanged.
The frozen first publisher remains a shared SQL helper and first-attempt audit record;
its registration path failed rollback rehearsal. Use revision 2, which keeps the existing
`source_dictionary` metadata family and separate execution/rehearsal evidence.

For [highest attainment and current study](../../docs/cses-additional-education-levels.md),
use `align_cses_additional_levels.py` for the 188-entry native dictionary and local qualified
projection, then `publish_cses_additional_levels.py` for separate preflight/backup/rehearsal/
publication actions. After publication use only `validate` and the independent
`validate_cses_additional_levels.py` (or its database-free `--local` acceptance). The selected
1996 source lacks current grade; no synthetic grade or degree equivalence is created.

For the [five-wave school attendance interface](../../docs/cses-additional-school-attendance.md),
`align_cses_additional_school.py` builds the source-verified local projection and rules;
`publish_cses_additional_school.py` provides separate preflight, backup, rollback rehearsal,
publication and read-only validation actions. After publication use only its `validate` action
and `validate_cses_additional_school.py` for independent source/scalar-logic acceptance.
Do not replace historical builders or rewrite original education answers to resolve skips.

The [2025 age interface](../../docs/cses-2025-age-interface.md) has its own additive workflow:
`publish_cses_2025_age_v2.py`. Use its `validate` action and `validate_cses_2025_age.py` for read-only
acceptance. Do not republish an existing target or rerun the original five-wave publication to
fix age selection. The new view selects native `age`; formula/reference-date/top-code flags
remain unverified, and all original columns and values are preserved.
The frozen `publish_cses_2025_age.py` is the transaction engine, not the current entry point;
its standalone source-v1 diagnostic was rolled back and never published.

The approved additive five-wave release is published as alignment release ID 14. For current
read-only verification, use `publish_cses_additional_waves.py validate` and
`validate_cses_additional_analysis.py`. The latter checks per-wave counts and critical scope
qualifications as `mda_readonly`. Do not rerun `prepare`, `rehearse` or `publish` on this existing
release. Preserve its immutable plans, backup and validation evidence under `data/releases/`.

For the read-only sex/age/school comparability pilot, run `experiment_cses_alignment.py`.
Its local aggregate report identifies the sparse published 2025 age field and school-denominator
sensitivity; native calculated age is used only for a local scenario, never a database update.
That pilot and its evidence stay historical; the later age interface is documented separately.

`audit_cses_source_gaps.py` checks supplied archive CRCs/hashes, cached document coverage, all
171 selected-field missingness profiles and focused native routing patterns. It writes local
aggregate evidence only and flags the unresolved 2025 treatment-sought scope.

## Retrieve missing questionnaire materials

The [current materials checklist](../../docs/cses-questionnaire-organization.md) separates
actual missing forms from draft/year qualifications and instruments not used in a given wave.
Open the [questionnaire collection index](../../data/processed/cses_questionnaires/README.md)
for archive-free access to historical caches and additive retrievals.

With Python providing `pypdf`, run from the project root:

```bash
python rsc/cses_db/retrieve_cses_questionnaire_materials.py \
  --plan rsc/specs/cses_questionnaire_retrieval_initial_six_v1.json
```

The plan pins six NIS PDFs for 1997, 1999 and 2011 by SHA-256, page count and cover evidence.
Original bytes are kept in `data/raw/questionnaire_supplements/20261016/`; library copies,
literal per-page text and manifests are under `data/processed/cses_questionnaires/official_retrieval_v1/`.
Existing differing files are not overwritten. Network retrieval is needed only for absent raw files.

`archive_cses_1997_questionnaire_bundle.py` extracts a 12-page village scan from physical pages
5-16 of the NIS-authored IHSN bundle. `archive_cses_2019_village_questionnaire.py` extracts physical
pages 202-211 of the official 2019/20 report (nine image-based form pages and one blank verso).
Each script documents its source URL and expected local input path; originals and separate
extraction manifests are retained. The local QA helper at
`data/processing/cses/materials_retrieval_20261016/archive_followup_qa.py` checks hashes, renders
all 73 form pages and compares both extracts pixel-for-pixel with their source pages.
These operations do not connect to PostgreSQL, alter historical hash-pinned caches, certify
variable mappings, or update Git/DVC versions.

`archive_cses_priority_search_evidence.py` registers the later 2017/2021/2023 follow-up references:
the unchanged 312-page Khmer 2021 report and a third-party paper citing the 2017 household form.
It explicitly records **zero newly recovered missing original forms**. The large report is retained
once under raw and linked from the library index; it must not be committed to Git. The
[priority search ledger](../../data/processing/cses/materials_priority_search_20261016/README.md)
records appendix-screening boundaries, retired/unavailable routes and the eight remaining targets.

## Boundary

- Input: immutable DVC-owned archives under `data/raw/`.
- Output: reproducible DVC-owned artifacts under `data/processing/cses/`.
- Code: Git-owned inventory, harmonization, builders, validators, and release comparison.
- PostgreSQL: schema migration v1 completed; routine audits and research access remain read-only.

The legacy `MJ02b` publishers are intentionally not copied. They write all object families and catalog
records into `public`, which conflicts with the functional-schema architecture. The v1 migration
contract, metadata model, deterministic SQL renderer, forced read-only preflight, external backup
verification, transactional migration, and postflight validation are implemented. New data publication
remains a separate reviewed operation; the approved baseline metadata import and its read-only
validation are complete.

Climate acquisition, general Cambodia boundary publication, heat-labor analytical tables, figures, and
research results remain outside this reusable core.

## Diagnose unlabeled housing codes

`profile_cses_housing_reverse_evidence.py --root .` replays the 2007, 2013 and 2017 raw housing
codes and expense fields against the pinned local release, then produces unweighted target and
documented-reference profiles. It neither connects to PostgreSQL nor approves inferred meanings.
See [interpretations and limitations](../../docs/cses-housing-reverse-inference.md).

## Reproduce the local release

The command below reproduces the historical baseline when run with its matching Git/DVC revisions.
The current housing builder includes the approved one-cell lighting correction, so an exact comparison
against the unchanged `MJ02b` baseline is expected to find that difference. Do not overwrite the old
baseline manifest or comparison evidence with the new release. Use the correction workflow below
for historical housing validation, and the value-publication validator for current database checks.

Historical command, from the project root:

```bash
uv run python rsc/cses_db/build_local_release.py \
  --root . \
  --reference-root ../../Research/MJ02b
```

This runs archive inventory, the dependency-ordered builders, all local validators, an optional
content comparison against the earlier release, and a machine-readable local release manifest. It does
not connect to PostgreSQL or update DVC.

After the local build passes, compare its structure with the current database in a forced read-only
transaction:

```bash
uv run python rsc/cses_db/audit_mda_baseline.py --root . --dbname mda --schema public
```

This checks relation presence, exact row counts, ordered columns, comments, and indexes. It does not
compare every cell and does not authorize migration.

## Plan the functional-schema migration

Render and verify the SQL from the Git-owned contract:

```bash
uv run python rsc/cses_db/render_cses_migration_sql.py --root .
uv run python rsc/cses_db/render_cses_migration_sql.py --root . --check
```

Run the forced read-only database preflight:

```bash
uv run python rsc/cses_db/plan_cses_schema_migration.py --root . --dbname mda
```

The preflight writes `data/processing/cses/migration_dry_run_v1.json` and exits unsuccessfully if the
source/target layout, roles, grants, dependencies, ownership, or declared natural keys violate the v1
contract. See the project migration runbook before any write operation.

## Plan the baseline metadata import

Run the forced read-only registry preflight:

```bash
uv run python rsc/cses_db/plan_cses_baseline_metadata.py --root . --dbname mda
```

This writes `data/processing/cses/baseline_metadata_plan_v1.json`. It verifies the Git-owned baseline
specification, DVC evidence, source archives, physical relations, metadata-table layout, and existing
records. The separate importer requires `--apply` and the exact approval phrase documented in the
[baseline metadata runbook](../../docs/cses-baseline-metadata-runbook.md); do not use it without a
reviewed plan and explicit database-write approval.

After an approved import, validate the exact reviewed plan in a separate forced read-only transaction:

```bash
uv run python rsc/cses_db/validate_cses_baseline_metadata.py --root . --dbname mda
```

## Plan the variable catalog

Catalog all registered Stata columns and build the conservative source-to-canonical proposal in a
forced read-only database transaction:

```bash
uv run python rsc/cses_db/plan_cses_variable_catalog.py --root . --dbname mda
```

The imported and independently validated v1 release covers 171 registered source datasets, 4,092
physical source variables, and the 280 columns in the seven accepted final tables. It does not
synthesize questionnaires or canonical value mappings. Any future import still requires `--apply`
plus the exact phrase documented in the
[variable catalog runbook](../../docs/cses-variable-catalog-runbook.md).

## Plan questionnaire provenance

Fingerprint the selected source-archive instruments and build deterministic question links in a
forced read-only transaction:

```bash
uv run python rsc/cses_db/plan_cses_questionnaire_provenance.py --root . --dbname mda
```

The imported and independently validated questionnaire-provenance v1 release uses the existing
alignment schema. It contains 14 instrument files, 164 question transcriptions, and 291 same-wave
source-variable links. The 2014 draft remains provisional, and image-only/OCR material is not promoted
to authoritative question text. Any later database write still requires `--apply` plus the exact
phrase documented in the
[questionnaire provenance runbook](../../docs/cses-questionnaire-provenance-runbook.md).

## Audit housing codes and missingness

The following is the historical pre-correction pilot command. Its pinned builder/table/catalog
fingerprints intentionally reject the newer correction release. Reproduce it only with the matching
Git/DVC revisions and database snapshot, keeping the accepted v1 reports immutable:

```bash
uv run python rsc/cses_db/plan_cses_value_audit.py --root . --dbname mda
```

The pilot checks archive and evidence hashes, profiles complete raw columns with Stata missing codes
preserved, reads 100 explicitly located questionnaire options, and verifies the current database's
code frequencies against the pinned local release. It writes a JSON preflight, code comparison,
conflict report, and Mermaid review overview under `data/processing/cses/value_audit_v1/`.
See the [value audit runbook](../../docs/cses-value-audit-runbook.md) for the separate questionnaire
cell-extraction command, confidence boundaries, and deterministic reproduction procedure. Candidate
categories remain proposed; this command has no database-write mode.

## Build the correction-aware value mapping review

The following planners describe the pre-publication catalog. Their database fingerprint gates
intentionally reject later releases; replay only against matching historical snapshots.

```bash
uv run python rsc/cses_db/plan_cses_value_mapping_review.py --root .
```

This separate read-only planner uses the preserved audit and accepted lighting correction rather than
repinning historical evidence. It replays the ten raw housing datasets, checks the full corrected
local/database housing table, and verifies 35 protected CSES tables. The new local review partitions
208 code rows into candidate, manual-review, unresolved, and missing-only evidence buckets. Every row
remains proposed; there is no apply or SQL-generation mode. See the
[review runbook](../../docs/cses-value-mapping-review-runbook.md) for output files, exact bucket meanings,
immutable output/replay rules, and publication boundaries.

After an exact user decision on a review bucket, materialize it separately rather than rewriting the
source review:

```bash
uv run python rsc/cses_db/record_cses_value_mapping_decisions.py --root .
```

The current decision specification selects the 70 user-approved `manual_review` identities from the
pinned review hash. It retains provisional/skip/comparability qualifications and has no database
connection or publication path. See the
[decision record](../../docs/releases/cses-value-mapping-manual-decisions-v1.md).

Both substantive buckets were approved (140 entries). The historical combined preflight command is:

```bash
uv run python rsc/cses_db/plan_cses_value_mapping_release.py --root .
```

This retains the original review and manual-decision bundles. It writes the combined approved scope
and proposed 21 versioned source rules plus 140 value mappings under
`data/processing/cses/value_mapping_release_v1/`. See the
[v0.10 preflight](../../docs/releases/cses-value-mapping-preflight-v0.10.md) for detailed checks,
interpretation boundaries, and the execution preparation required at that historical stage.

## Historical lighting correction validation

The approved `cses-housing-lighting-missing-v1` release excludes source code 9 only from the 2004
lighting field. Exactly one housing cell changed in the local artifact and `mda`; all other cells,
keys, and dtypes are preserved. One revised variable mapping, one release, and one load run were
appended without replacing the historical mapping or adding canonical value mappings.

```bash
uv run python rsc/cses_db/validate_cses_ho.py
uv run python rsc/cses_db/correct_cses_housing_lighting.py validate --root .
```

The second command uses a forced read-only database transaction and the immutable correction evidence.
It is pinned to the correction-only catalog and must not be used as the current validator after
the value dictionary release. The current validator below retains the full housing checks.
See the [correction runbook](../../docs/cses-lighting-correction-runbook.md) and
[release record](../../docs/releases/cses-lighting-correction-v1.md) for source checks, scoped backup,
before/after comparisons, and version pins. Older catalog and release plans remain historical; their
fingerprint gates must not be weakened to accept the corrected state.

## Historical value dictionary publication and validation

The `publish_cses_value_mappings.py` workflow separates external scoped backup, read-only execution
preparation, an exact-hash-gated transaction, and independent read-only validation. It appends one
release, 21 versioned source rules, 140 value mappings and one load run without changing physical
data. See the [publication runbook](../../docs/cses-value-mapping-publication-runbook.md).

Dictionary-only historical validation command (before the housing interface views):

```bash
uv run python rsc/cses_db/publish_cses_value_mappings.py validate --root .
```

This checks every published record, all 35 protected CSES tables, and full housing/local equality.
The original review, decisions, preflight and correction evidence remain immutable.

## Housing interface and current validation

The current `cses_analysis.cses_housing_value_dictionary_v4` and `cses_housing_categories_v4` views
retain all v3 entries and add the six-observation 2021 biogas definition with bilingual conflict
provenance. Original columns, all records and all earlier interface versions remain unchanged. Use:

```bash
uv run python rsc/cses_db/publish_cses_housing_2021.py validate --root .
```

This verifies the new biogas definition, two instruments, four questions, two source links, the
retained tenure anomaly, every category association and protected pre-existing state. The evidence
module `cses_housing_2021_evidence.py` reads both original XLSM files without executing macros. Do not alter historical validators to ignore new structure. See the
[current runbook](../../docs/cses-housing-2021-resolution.md).

## Inventory core-table readiness

For a separate read-only inventory of all seven core tables by field and wave, run:

```bash
uv run python rsc/cses_db/inventory_cses_readiness.py --root .
```

This preserves existing artifacts and writes a new immutable readiness report. It checks local
validators, live natural keys, ordered columns/catalog types, per-wave row and non-null counts,
linkage exceptions and approved dictionary coverage. It does not certify cross-wave comparability
or full seven-table cell equality. See the [inventory and work queue](../../docs/cses-readiness-inventory.md).

## Export the lineage graph

Export the authoritative database state through one forced read-only transaction:

```bash
uv run python rsc/cses_db/publish_cses_housing_2021.py export --root .
```

The extended v10 JSON graph and interface dependency JSON are DVC-owned under `data/lineage/`. See the
[lineage export runbook](../../docs/cses-lineage-export-runbook.md) for its validation, interpretation,
and versioning contract. Always specify a new version for a changed database state; the CLI's legacy
default points to v1 and must not overwrite accepted historical evidence. The legacy exporter covers
the v1–v6 catalog model, not the two additive interface views.

## Build order

```text
HL -> ED -> HH -> HO
 |          |
 +-> EC     +-> VL
            +-> SURVEY_DATE
```

HH follows ED because household-head education is linked from the education release. VL requires both
HH and HL. Every output preserves its documented native grain and retained-link exceptions.
