# CSES Functional-Schema Preflight v0.2

## Status

Completed on 2026-09-04 in a forced read-only PostgreSQL transaction. The database was not mutated.

## Result

The preflight reports `migration_ready = true` for the proposed `mda` migration from `public` to
`cses_meta`, `cses_alignment`, `cses_data`, and `cses_analysis`.

- All 22 declared source objects exist as ordinary physical tables in `public`.
- No declared target relation or functional schema currently exists.
- All physical objects are owned by `lichao` and retain `mda_readonly` SELECT grants.
- No PostgreSQL view depends on a declared source object.
- Thirty-one non-migrated `public` relations were fingerprinted as the protected object set.
- The 22 relations contain 1,283,695 rows and occupy 467,206,144 bytes in total at this checkpoint.
- All eight declared natural keys contain zero null-key rows and zero duplicate groups.
- The executor can create schemas and exact-name compatibility views.
- The generated report was byte-identical across two consecutive runs against unchanged database state.

## Object allocation

| Family | Count | Target |
|---|---:|---|
| Final analytical tables | 7 | `cses_data` |
| CSES geography bridge | 1 | `cses_data` |
| Source-variable dictionaries | 7 | `cses_alignment` |
| Alignment summaries | 7 | `cses_analysis` |

## Evidence boundary

The machine-readable evidence is `data/processing/cses/migration_dry_run_v1.json` and is DVC-owned.
The contract, DDL, generated migration SQL, planner, tests, runbook, and this record are Git-owned.

This pass proves that the current database satisfies the declared preconditions. It does not prove that
the generated write transaction has been executed, does not replace a backup, and does not authorize a
database mutation. A fresh preflight is required immediately after the backup and before execution.
