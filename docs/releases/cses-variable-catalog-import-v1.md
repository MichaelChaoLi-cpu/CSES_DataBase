# CSES Variable Catalog Import v1

- Date: 2026-09-05
- Database: `mda`
- Release: `cses-variable-catalog-v1`
- Approval: exact phrase `ACCEPT-CSES-VARIABLE-CATALOG-V1` received

## Outcome

The reviewed variable-catalog plan was applied in one transaction. The importer inserted exactly one
approved alignment release, 4,092 source-variable records, 280 canonical-variable records, 1,714
tested variable-mapping records, and one load-run record. Its in-transaction reconciliation observed
all 6,088 reviewed records as no-ops after insertion, with zero pending inserts and zero conflicts.

The independent validator then opened a new forced read-only transaction and passed every check. It
again observed all 6,088 records as no-ops. The seven physical final tables, compatibility views,
source datasets, and prior metadata releases were not updated or replaced.

## Versioned evidence

| Evidence | SHA-256 |
|---|---|
| Reviewed plan | `0d9563ff820073baa420b98e1c722b32cfdad77d2c27ce6df7fbdb307a4fa8c1` |
| Import evidence | `b5a881a3f185393690417e055f93a6b01904c71bcdb300a1975f29a0b3a9bc2f` |
| Validation evidence | `4bd50e872db990a2969eac416cfd35832ca38e245bcc2ce66c5d79fec18ccf5e` |
| Post-import graph v3 | `7ed93033ba00f19a9e0e0e78e7d111673b1311d5df73887867b466764ab6b570` |
| Post-import overview v3 | `ea93d3d76500cd33c0d8918a06077ac996136813afe90b15df6ee9f2a40c5eaf` |

The final DVC data pointer is `md5:ce349471ab5bc4022c4c6ca847de84ca.dir` with 73 files and
465,655,718 bytes. The reviewed implementation revision is
`1229f1b3d3a8f377245cfa22fa7f40e158f3c128`; the preflight pointer and review record were committed at
`daed739`.

Graph v3 was exported twice from the same authoritative database state. Both the 5,417,100-byte JSON
graph and the 695-byte Mermaid overview were byte-identical across exports.

## Resulting variable topology

- registered source datasets: 171;
- source variables: 4,092;
- canonical variables: 280 across seven final tables;
- variable-mapping records: 1,714;
- source-variable-to-canonical graph edges: 1,770;
- canonicals with at least one mapping in this release: 194;
- instruments and questions: 0;
- canonical value mappings: 0;
- alignment releases and load runs: 3 each;
- storage relations with dataset-output coverage: 22 of 22.

The difference between 1,714 mapping records and 1,770 graph edges is expected: a mapping record may
name more than one raw source field. The 86 canonical-only fields are retained rather than assigned
fictional raw inputs; they include constants, identifiers synthesized from release context, provenance
fields, aggregates, and other reviewed derivations.

## Provenance boundary

All 4,092 physical variables retain their native position, Stata storage type, variable label, and
released Stata value labels. No authoritative questionnaire files were present in the versioned
evidence, so no instrument, question, or question-link row was inferred. Stata value labels were not
treated as approved cross-wave category mappings, leaving `cses_value_mapping` empty.

The next independent metadata release may discover and fingerprint authoritative questionnaires,
register exact or provisional question text, and review question-to-source-variable links. A separate
value-harmonization release is required before canonical category mappings are created.
