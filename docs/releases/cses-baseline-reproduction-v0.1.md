# CSES Local Baseline Reproduction v0.1

## Status

Completed on 2026-09-04 without a PostgreSQL write, Git commit, Git push, DVC update, or DVC transfer.

## Inputs

- Eleven top-level CSES ZIP archives under `data/raw/`.
- Every archive SHA-256 matched the corresponding archive used by `../../Research/MJ02b`.
- Archive inventory discovered 157 core module sources and 3,633 source-variable records with zero read
  errors.

## Local table results

| Table | Rows | Columns | Local validation | MJ02b value comparison | mda row/column audit |
|---|---:|---:|---|---|---|
| `final_HH_CSES` | 77,904 | 32 local; 35 after date enrichment in mda | Pass | Exact after path normalization | Pass |
| `final_HL_CSES` | 358,920 | 37 | Pass | Exact after path normalization | Pass |
| `final_ED_CSES` | 343,204 | 30 | Pass | Exact after path normalization | Pass |
| `final_HO_CSES` | 77,922 | 50 | Pass | Exact after path normalization | Pass |
| `final_EC_CSES` | 332,903 | 60 | Pass | Exact after path normalization | Pass |
| `final_VL_CSES` | 5,718 | 40 | Pass | Exact after path normalization | Pass |
| `final_SURVEY_DATE_CSES` | 77,904 | 28 | Pass through date build contract | Exact after path normalization | Pass |

The path normalization changes only provenance strings from `data/raw/CSE/` to this repository's
canonical `data/raw/` location.

## Retained exception contract

The validators reproduced the known, intentionally retained linkage exceptions:

- ED to HL: 4 unmatched released education records.
- HO to HH: 19 unmatched released housing records.
- EC to HL: 2 unmatched released employment records.
- HL: 11 missing relationship values, 129 missing absence values, and one household without exactly one
  coded head.
- VL: all 5,718 PSU-wave records link to HH; 120 age-component and 116 sex-component discrepancies remain
  visible rather than being overwritten.

These exceptions are part of the baseline contract and explain why strict cross-module foreign keys
must not be introduced without an exception-preserving design.

## Reproducible evidence

- `data/processing/cses/local_release_manifest.json`: archive and artifact fingerprints.
- `data/processing/cses/reference_comparison.json`: local-versus-MJ02b content comparison.
- `data/processing/cses/mda_baseline_audit.json`: forced read-only database structure comparison.
- `rsc/cses_db/build_local_release.py`: dependency-ordered build and validation runner.
- `rsc/cses_db/audit_mda_baseline.py`: read-only PostgreSQL baseline audit.

All generated evidence is DVC-owned. Code and this release record are Git-owned.

## Boundary reached

The local reproduction gate is complete. The next gate is to implement schema-aware metadata and
migration dry-run tooling. Creating schemas, backing up `mda`, moving relations, changing grants, or
creating compatibility views still requires separate approval.
