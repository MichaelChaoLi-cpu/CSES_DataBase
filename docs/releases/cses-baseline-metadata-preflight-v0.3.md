# CSES Baseline Metadata Preflight v0.3

Date: 2026-09-04

## Outcome

The baseline metadata specification, guarded importer, and forced read-only database planner are
implemented. No PostgreSQL mutation was performed.

The plan proposes the following reviewed state:

| Registry group | Proposed records | Existing records | Action |
|---|---:|---:|---|
| Surveys | 10 | 0 | Insert |
| Source archives | 11 | 0 | Insert |
| Physical datasets | 171 | 0 | Insert |
| Alignment releases | 1 | 0 | Insert after explicit approval |
| Storage relations | 22 | 0 | Insert |
| Dataset-output edges | 62 | 0 | Insert |
| Load runs | 1 | 0 | Insert |
| **Total** | **278** | **0** | **278 inserts, 0 conflicts** |

The planner verified all eleven archive files by size and SHA-256, matched all 22 physical relations to
the functional-schema migration evidence, confirmed the v1 metadata table columns, and ran with
`transaction_read_only=on`. Every preflight check passed.

Two consecutive exports of `data/processing/cses/baseline_metadata_plan_v1.json` were byte-identical.
The final cross-recorded plan SHA-256 was
`5d3bad6f959c051eaff4c1b7ecfb73cbb59f387a1b296723ac1d8d8b93e5def2`; it identifies Git revision
`e0fec7e629c467229178fab35aa7f70e46b32cd4` and source DVC revision
`md5:5527d5015fff181a75a2dd6184f4e3db.dir`.

## Interpretation

This record approves neither the baseline alignment release nor a database write. The proposed release
describes adoption of the currently validated state and does not invent earlier load events. The
geography source edge and inherited dictionary/summary dataset edges remain explicit follow-up gaps.

The next gate is a Git commit of the implementation, regeneration of the plan against that code
revision, and DVC/Git cross-recording of the final plan before explicit human approval of the
transactional import.
