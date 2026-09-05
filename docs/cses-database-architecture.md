# CSES Database Architecture

[Documentation index](README.md) · [Processing workflow](cses-processing-workflow.md) · [Topology](cses-topology.md)

## Decision status

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

The questionnaire-provenance v1 design uses these existing relations without a new schema. Its
reviewed scope fingerprints 14 source-archive instruments, catalogs 164 normalized question
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
Questionnaire links and canonical value mappings remain independent later releases. The graph remains
a read-only DVC projection rather than a second source of truth.
