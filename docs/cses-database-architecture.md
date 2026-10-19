# CSES Database Architecture

[Documentation index](README.md) · [Processing workflow](cses-processing-workflow.md) · [Topology](cses-topology.md)

## Decision status

The [published health screening interface](cses-health-screen-interface.md), release 28,
retains all 571,699 member-wave records in 43 columns and qualifies a bounded eight-wave
30-day subset of 308,955 records. Two new tables and five views have 197 source-output edges
and additive release/storage/load metadata. The source bridge preserves selected native
branch values absent from earlier JSON; old tables and interfaces are not overwritten.
Distinct four-week concepts, 2017's unverified form, 2019's code conflict, 66 missing-health
members and five source orphans remain explicit. The accepted pilot and preflight are
preserved separately rather than re-labelled as production releases.

The [unified fifteen-wave education interface](cses-education-unified-interface.md), release 26
on 2026-10-18, preserves 571,699 member-wave records in one 77-column analysis view with eight
targets. Four additive source/rule/audit tables support three views; 141 source-output edges
reuse existing dataset identities. The 120-row matrix and 360-row coverage view expose field
availability, form scope and denominators. Strict 2017 values remain withheld; the accepted
positive-years conflict guard blocks two people's four inferred values. A native bridge
preserves evidence lost by earlier cleaning without rewriting canonical tables. All prior
relations, privileges and registry prefixes remain unchanged; select the new interface
explicitly to use this contract rather than assuming older views inherit it.

The [five-wave literacy and observed school-years interface](cses-additional-literacy-years.md),
release 24 on 2026-10-18, adds 20 source rules and two analysis views. It preserves all 212,779
members, keeps legacy combined literacy separate from modern component-derived conjunctions,
and qualifies observed completed years without skip or grade imputation. Publisher revision 2
uses the existing `source_dictionary` and `alignment_summary` metadata families; database
constraints, original answers and all previous interfaces remain unchanged.

The [five-wave education-level interface](cses-additional-education-levels.md), release 21
on 2026-10-18, adds a native
level codebook, a member-level analysis view and a field-level coverage view. It keeps
highest attainment and current study separate, preserves all 212,779 members and source codes,
and records source/form numbering differences and field-specific route qualifications.
Existing source data and interfaces remain unchanged; no ISCED equivalence is certified.

The [five-wave school attendance interface](cses-additional-school-attendance.md), release 19
on 2026-10-18, adds a member
view, coverage view and source-rule view. It preserves all 212,779 roster records, uses the
published 2025 age selection, and separates observed, skip-derived, unresolved and out-of-age
records. Source/storage/load metadata is additive. Original education tables and all earlier
interfaces remain unchanged; no unrestricted school-concept equivalence is certified.

The additive [2025 age selection](cses-2025-age-interface.md), release 17 on 2026-10-18, introduces one source bridge,
one person-age view and one field-rule view, with release/storage/source-output/load metadata.
It selects native calculated age for all 51,775 members while preserving original manual ages
and keeping calculation/reference-date/top-code verification flags false. No existing table,
view or public compatibility interface is replaced. Use the new age view explicitly.

Current additional-wave release (2026-10-03): the approved
[qualified publication](cses-additional-waves.md#additional-wave-database-release), release ID 14,
adds seven module tables for 1996/1997/1999/2023/2025, a geography bridge, an original-EC audit table,
two evidence/mapping tables and three geography views. Existing ten-wave tables remain unchanged;
the v2 person-geography interface covers all 15 waves. Native JSON-array keys and qualified fields
are not forced into the older physical contracts. Survey/source/storage/load metadata is additive.

Current additive geography interface (2026-10-03): the approved
[geography release](cses-additional-waves.md#geography-interface-release-approved-scope) adds a
2004 household-level source supplement and household/person/coverage views. Existing physical
tables and public compatibility interfaces remain unchanged. Select the new views explicitly to
use recovered 2004 geography; the five additional-wave candidates are not published by this release.

**Status: Accepted and implemented on 2026-09-04.** The four functional schemas are active in `mda`,
the 22 scoped physical relations have moved, and exact-name `public` compatibility views are validated.

Create four function-oriented schemas in the `mda` database:

| Schema | Authoritative responsibility |
|---|---|
| `cses_meta` | Survey, archive, dataset, storage, output, release, and load-run records |
| `cses_alignment` | Source variables, canonical variables, mapping rules, value mappings, instruments, and questions |
| `cses_data` | Approved physical CSES tables at their declared analytical grain |
| `cses_analysis` | Cross-module views, compatibility interfaces, and coverage or quality audit views |

Use `public` only as the compatibility boundary. Existing CSES relation names remain available as views
while physical tables reside in the authoritative functional schemas. No duplicate physical copies are
maintained.

## Why a new schema layout is warranted

The recommendation follows both the current database evidence and the working DHS precedent:

1. On 2026-09-04, `mda.public` contained 53 ordinary relations across several domains. Twenty-two were
   core CSES relations: seven `final_*` tables, seven `ind_que_*` dictionaries, seven
   `align_summary_*` tables, and `dim_geo_CSES`.
2. The shared `public._catalog` contained five MICS or NLSS records and no CSES records, even though the
   earlier CSES publisher was designed to add CSES rows. The physical tables and the discovery surface
   have therefore diverged.
3. Existing CSES core tables had useful unique and lookup indexes but no declared PostgreSQL primary-key
   or foreign-key constraints. Some cross-table orphans are intentionally retained and flagged, so
   constraint adoption must follow the documented row-retention contract rather than be applied blindly.
4. `public` also contained climate tables and research-specific heat-labor tables. Those products have
   different owners and release cycles from the reusable CSES survey database.
5. The DHS project already demonstrated that functional schemas, transactional loads, an explicit
   storage registry, append-only release evidence, and a deterministic read-only graph can coexist with
   backward-compatible command routing.

A single new `cses` schema would reduce name collisions but would not separate mutable load state,
reviewed alignment evidence, physical data, and stable query interfaces. Four functional schemas make
those ownership boundaries visible and enforceable.

## Scope boundary

The CSES database owns reusable survey content and CSES-specific geography or timing bridges. It does
not own a particular research project's model-ready tables or results.

| Object family | Proposed owner |
|---|---|
| `final_HH_CSES`, `final_HL_CSES`, `final_ED_CSES`, `final_HO_CSES`, `final_EC_CSES`, `final_VL_CSES` | `cses_data` |
| `final_SURVEY_DATE_CSES`, `dim_geo_CSES` | `cses_data` |
| `ind_que_*_CSES` | `cses_alignment` |
| `align_summary_*_CSES` and CSES coverage views | `cses_analysis` |
| Survey, source, load, release, and storage registries | `cses_meta` |
| `final_CLIMATE_*`, general Cambodia boundary dimensions | Separate climate/geography ownership decision |
| `final_HEAT_LABOR_*` | Research-project schema, not the reusable CSES database |

The existing names are retained during the first migration to minimize avoidable downstream changes.
Naming modernization, if desired, is a later interface-version decision.

## Proposed management model

The minimum current-state management relations are:

- `cses_survey`: one row per CSES wave and release identity.
- `cses_source_archive`: one row per retained top-level archive, with size and SHA-256.
- `cses_dataset`: one row per physical Stata member or nested member discovered in an archive.
- `cses_storage_table`: one row per authoritative physical output and declared grain.
- `cses_dataset_output`: the many-to-many bridge from physical inputs to materialized outputs.
- `cses_alignment_release`: one reviewed mapping release.
- `cses_load_run`: immutable load, skip, replacement, or failure history with fingerprints and counts.

The minimum alignment relations are:

- `cses_instrument` and `cses_question` for retained questionnaire provenance when available.
- `cses_source_variable` for every physical source column, label, type, and source position.
- `cses_canonical_variable` for approved analytical fields and their grain.
- `cses_variable_mapping` for source-to-canonical rules, status, transformation, and release.
- `cses_value_mapping` for reviewed category mappings rather than code-number assumptions.

The accepted questionnaire-provenance v1 release uses these existing relations without a new schema.
It fingerprints 14 source-archive instruments, catalogs 164 normalized question
transcriptions, and links 291 existing source variables by deterministic native-code prefixes. Draft
and image-only evidence remains explicitly provisional or discovered rather than being promoted to
verified question text.

Adopt append-only revisions before the first replacement under this repository. A baseline snapshot can
describe the imported current state, but it must not claim to reconstruct earlier states that were never
captured.

## Grain and key contracts

| Family | Grain | Current natural key |
|---|---|---|
| HH | Household-wave | `survey_wave + household_id` |
| HL | Household-member-wave | `survey_wave + person_id` |
| ED | Released education record | `survey_wave + person_id` |
| HO | Released housing record | `survey_wave + household_id` |
| EC | Released current-employment record | `survey_wave + person_id` |
| VL | Village-questionnaire PSU-wave | `survey_wave + psu` |
| SURVEY_DATE | Household-wave timing audit | `survey_wave + household_id` |
| GEO | PSU-wave geography bridge | `survey_wave + psu` |

Primary keys may be promoted from verified unique indexes after null and duplicate checks. Foreign keys
must not erase legitimate source records. The earlier pipeline deliberately retains unmatched ED, HO,
and EC rows with explicit link-status fields; these relationships should remain validated soft links
until their exception contract can be represented without data loss.

## Current baseline

The eleven archives under `data/raw/` are byte-identical by SHA-256 to the archive set used in
`../../Research/MJ02b`. This makes the existing pipeline a reproducible starting point rather than an
unverifiable external prototype.

Exact row counts observed in `mda.public` on 2026-09-04 were:

| Relation | Rows | Waves |
|---|---:|---:|
| `final_HH_CSES` | 77,904 | 10 |
| `final_HL_CSES` | 358,920 | 10 |
| `final_ED_CSES` | 343,204 | 10 |
| `final_HO_CSES` | 77,922 | 10 |
| `final_EC_CSES` | 332,903 | 10 |
| `final_VL_CSES` | 5,718 | 8 |
| `final_SURVEY_DATE_CSES` | 77,904 | Not separately audited here |

The new repository reproduced all seven local Parquet tables value for value against the `MJ02b`
baseline after normalizing the intentional `data/raw/CSE/` to `data/raw/` path change. A forced
read-only database audit also matched relation presence, exact row counts, and ordered columns for all
seven current `mda.public` tables. These are migration invariants, not proof that every mapping is
correct.

## Migration strategy

The structural migration was explicitly approved and completed with the following record:

1. ~~Port the reusable CSES local-build code and tests from `MJ02b`; remove research-project
   dependencies and update the raw archive root.~~ Completed in the local baseline reproduction.
2. ~~Rebuild staging artifacts from the eleven DVC-owned archives and reproduce the current table
   counts, keys, columns, and documented exception counts.~~ Completed and recorded in the v0.1
   reproduction evidence.
3. ~~Implement and test the schema-aware metadata model and migration dry-run without changing `mda`.~~
   Completed in the v0.2 preflight evidence.
4. ~~Create the functional schemas and metadata model inside the backed-up, all-or-nothing migration
   transaction.~~ Completed.
5. ~~Import a baseline alignment release and deterministic load record without inventing missing
   history.~~ Completed after an explicitly approved, deterministic, conflict-free read-only plan.
6. ~~Create and validate a complete custom-format PostgreSQL backup before structural work.~~ Completed;
   full decompression and SHA-256 verification passed.
7. ~~Run a read-only migration preflight that records relation identities, dependencies, owners, indexes,
   row counts, and checksums or aggregate fingerprints.~~ Completed immediately after backup.
8. ~~In one transaction, move CSES physical relations into their authoritative schemas and create
   exact-name `public` compatibility views without moving climate or research-project relations.~~
   Completed.
9. ~~Validate all invariants and roll back the complete transaction on any mismatch.~~ Postflight,
   physical-identity, compatibility-reader, and local-baseline validation passed.
10. ~~Publish the baseline metadata import release after database validation and export the
    deterministic lineage graph as a separate release milestone.~~ Completed.

The preflight found no dependent PostgreSQL views and no declared foreign keys on the migrated CSES
relations. The compatibility layer preserves external SQL using the earlier `public` names.

## Decision gates

The completed schema creation, relation move, compatibility-view creation, grant changes, and baseline
metadata import were covered by recorded execution approvals and the verified-backup gate. Human
approval is still required before:

- promoting physical-table primary or foreign-key constraints;
- publishing new data or replacing a prior CSES release.

The 15 storage-provenance gaps are closed and `cses-variable-catalog-v1` is now imported and validated.
It catalogs all 171 registered source datasets and 4,092 physical variables, registers the exact 280
physical final-table columns as canonicals, and materializes 1,714 builder-supported mappings. The
existing `cses_alignment` schema expresses this model, so no additional schema was required.
Questionnaire links were subsequently imported in `cses-questionnaire-provenance-v1`. Canonical value
mappings were still empty at that stage. The read-only housing value audit covered three classification
fields across ten waves; its proposed categories were not themselves approved database mappings.

The approved `cses-housing-lighting-missing-v1` release subsequently corrected exactly one 2004 housing
lighting cell from the explicitly labeled missing code 9 to NULL. It uses the existing schemas and
appends one revised variable mapping, one release, and one load run. The original mapping remains
immutable; the correction load identifies mapping 57 as superseded for this source/canonical pair.
That stage contained 1,715 mapping records, not 1,715 distinct canonical fields. No category mapping, raw
archive, questionnaire link, table identity, or compatibility interface changed. Graph v5 records the
new release and load provenance; it remains a read-only DVC projection rather than a second source of
truth. See the [correction release](releases/cses-lighting-correction-v1.md).

The subsequent `cses-housing-value-mapping-v1` release uses the existing alignment schema to publish
140 approved values under 21 new release-specific source rules. That stage had 1,736 source-mapping
records, still 280 canonical fields, six releases and six load runs. No new schema, analytical view,
physical column, or rewritten source code is introduced. The 2004 lighting rule copies the accepted
correction (mapping 1715), not the superseded baseline rule. All prior mapping records remain intact.

Consumers must select the dictionary release explicitly; joining all historical rules can duplicate
results. The dictionary retains provisional, compound/residual and routing qualifications, and does
not settle cross-wave analytical denominators. Graph v6 projects the new provenance and value counts.
See the [publication record](releases/cses-value-mapping-import-v1.md) and
[current validator](cses-value-mapping-publication-runbook.md).

The subsequent housing-interface delivery adds only two ordinary views in `cses_analysis`:
`cses_housing_value_dictionary_v1` and `cses_housing_categories_v1`. They expose 140 approved code
entries and 77,922 housing records respectively, with original codes, match states and evidence intact.
All 35 physical tables and the six-release metadata catalog remain unchanged. Graph v7 adds actual
view dependencies. Interface provenance is bound in view comments and the local execution/import
records; it does not create another alignment release. See the
[historical interface runbook](cses-housing-interface-runbook.md).

The subsequent `cses-housing-2017-from-2016-v1` release adds three 2017 source rules and 21 value
entries by explicit user-approved transfer from 2016. That release brought the catalog to 1,739 source mappings,
161 value mappings, seven alignment releases and seven load runs. Two new v2 analysis views combine
the unchanged v1 dictionary with this transfer; all original physical data and v1 views remain intact.
The evidence distinguishes user approval from target-questionnaire verification. No 2007 or 2013
metadata is changed by this release. See [preserved v2 interface](cses-housing-2017-alignment.md).

The subsequent `cses-housing-recovered-evidence-v1` release registers three independent 2007 code
lookups and the nested 2013 household questionnaire, catalogs three housing questions and updates
three formerly empty source-question links. Six source rules and 39 values bring the catalog to
1,745 mappings, 200 value mappings, eight releases/runs, 18 instruments, 167 questions and 294 links.
Its two v3 views retain physical data, prior interfaces and the qualified 2017 transfer. No additional
schema is required; see [preserved v3 interface](cses-housing-recovered-evidence.md).

The 2021 resolution subsequently adds one biogas mapping, two language instruments, four questions,
two reviewed source links and v4 views. Current totals are 1,746 variable mappings, 201 values,
nine releases/runs, 20 instruments, 171 questions and 296 links. Physical data and the tenure anomaly
remain unchanged; see [current validation](cses-housing-2021-resolution.md).
