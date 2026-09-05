# CSES Housing Value Mapping Review

## Scope and status

`cses-value-mapping-review-v1` is a local, non-publishable review of lighting, cooking fuel, and dwelling
tenure across ten waves. It follows the approved one-cell lighting correction without overwriting the
historical value audit. It does not change `mda`, source archives, published tables, or canonical value
mappings, and it is not a database import plan.

The preserved pre-approval review has 208 code rows in 30 wave/field profiles. Subsequent user decisions
approve both substantive buckets, as recorded below; this historical review file remains unchanged:

| Review bucket | Code rows | Meaning |
|---|---:|---|
| `candidate` | 70 | Documented label interpretation with no outstanding triage flag; still unapproved |
| `manual_review` | 70 | Draft, residual/compound category, skip, or frequency qualification requires judgment |
| `blocked` | 52 | Meaning unresolved or conflicting; no category or missingness reason assigned |
| `missing_only` | 16 | Source missing-code evidence, kept outside substantive categories |

These counts describe code records, including unobserved labeled/options-only codes, not households.
The three substantive buckets plus missing evidence form an exhaustive partition. A candidate is not
a declaration of cross-wave equivalence, eligibility, or analysis-ready data. All 208 rows have
`review_status=proposed` and `publication_ready=false`.

## Build and verify

Historical command, to replay only against the matching pre-publication database snapshot:

```bash
uv run python rsc/cses_db/plan_cses_value_mapping_review.py --root .
uv run pytest -q
```

The planner validates the fingerprints in `rsc/specs/cses_value_mapping_review_v1.json`, including the
immutable value audit, its semantic aliases, the correction specification and before/plan/import/
validation evidence, and the original/corrected local housing artifacts. It also verifies the
implementation hashes bound by the accepted correction plan.

All ten selected raw housing datasets are read again. Archive/member hashes, value labels, row counts,
and full frequencies must match the pinned audit. The planner reuses the already pinned questionnaire
transcriptions; it does not perform a new questionnaire extraction or infer absent documents.
Semantic decisions are rechecked against the original alias rules, not invented from numeric equality.

The complete local housing comparison permits only the already approved 2004 lighting cell change.
Each of the 30 current profiles separately accounts for all numeric observations and SQL NULLs.
Aggregate counts do not attribute each SQL NULL to a raw missing reason. In particular, the existing
exclusion of 2021 tenure code 0 does not prove that 0 means missing.

The database step opens a new forced `REPEATABLE READ, READ ONLY` transaction. It checks all 35 protected
CSES physical tables and the exact correction metadata against the recorded post-correction state,
then compares all local housing cells to the live table after the previously accepted comparison-only
archive-path normalization. An unrelated later database release intentionally invalidates this review
snapshot: create a newly scoped review rather than weakening its gates.

No `--apply`, INSERT/UPDATE/DELETE, migration SQL, or importer path is exposed by this command.
No output is written until the local and live checks pass.

## Outputs and history

Generated artifacts belong under the DVC-owned directory
`data/processing/cses/value_mapping_review_v1/`:

- `review.json`: all 208 proposed records, exact source keys, source hashes, questionnaire cell
  provenance, raw/baseline/current frequencies, bucket/reasons, and validation/code fingerprints.
- `review.md`: human-readable review queue, current per-wave coverage, priority decisions, and the
  full field-by-field code comparison.
- `overview.mmd`: local review flow, distinct from the authoritative database lineage graph v5.

The approved 2004 lighting mapping override is explicit in the corresponding profile and code row.
Historical flags stay under `historical_flags`; `correction_resolution` marks code 9 as corrected to
NULL, without pretending the earlier audit was already based on the corrected state. Missing-code rows
do not become candidate categories. Original reports, plans, manifests, and graphs remain unchanged.

Use `--output-dir` for an independent replay, for example:

```bash
uv run python rsc/cses_db/plan_cses_value_mapping_review.py --root . \
  --output-dir .pytest_cache/cses-value-mapping-review-v1-replay
cmp data/processing/cses/value_mapping_review_v1/review.json \
  .pytest_cache/cses-value-mapping-review-v1-replay/review.json
cmp data/processing/cses/value_mapping_review_v1/review.md \
  .pytest_cache/cses-value-mapping-review-v1-replay/review.md
cmp data/processing/cses/value_mapping_review_v1/overview.mmd \
  .pytest_cache/cses-value-mapping-review-v1-replay/overview.mmd
```

Outputs must be byte-identical with unchanged inputs, implementation, Git base, and database state.
The recorded HEAD is explicitly a base checkout, not proof that newly added code is committed; file
hashes identify the executed implementation. A changed HEAD or implementation requires a fresh output
directory. Existing differing files are rejected before any output is written.

Git owns the planner, spec, tests, and this runbook; DVC owns the three generated outputs. This local
review step does not stage/commit/push Git or update/push DVC. Preserve the exact reviewed outputs when
the user requests version synchronization; do not regenerate them just to replace their base revision.

## Human review and a later publication boundary

On 2026-09-05, the user accepted all 70 rows in the `manual_review` bucket with their proposed
categories unchanged. The exact result is materialized by:

```bash
uv run python rsc/cses_db/record_cses_value_mapping_decisions.py --root .
```

This creates the separate immutable, DVC-owned
`data/processing/cses/value_mapping_manual_decisions_v1/` bundle. It preserves all qualifications and
does not rewrite the source review. See the
[decision record](releases/cses-value-mapping-manual-decisions-v1.md).

The user subsequently approved the remaining 70 candidates and requested careful verification. All
140 substantive entries received semantic approval. The historical combined preflight command is:

```bash
uv run python rsc/cses_db/plan_cses_value_mapping_release.py --root .
```

This replays the raw/local review, matches all 100 available questionnaire options to their retained
cells, checks the previous manual decisions, verifies current database contents, and resolves the
21 effective source rules. Outputs are under `data/processing/cses/value_mapping_release_v1/`.
The [v0.10 preflight](releases/cses-value-mapping-preflight-v0.10.md) records the 140 approved entries
and proposed 163 metadata inserts. The command has no database-write mode.

Skip text describes routing and does not automatically invalidate a label; its effect on analytical
denominators remains a separate analytical question. Keep 2014 draft evidence provisional. Residual
`Other` and compound categories retain their approved distinctions and source-specific context.

The 52 unresolved rows remain unassigned. Priorities include household evidence for 2007/2013/2017,
the untranslated 2021 lighting label, and the single undocumented 2021 tenure code 0. Do not borrow
neighboring waves' meanings or assign a missingness reason based on a raw/published count difference.

No additional schema is needed. The separately authorized publication uses
`cses_alignment.cses_value_mapping`, with exact variable-mapping/release identity, while retaining the
physical numeric source-code fields. Any analytical category view or new field requires an explicit
output contract. See the [publication runbook](cses-value-mapping-publication-runbook.md) and
[execution preflight](releases/cses-value-mapping-execution-v1.md) for its backup, append-only transaction,
and independent validation. The original local review alone is not authority for database writes.

After the 2021 resolution publication, use `publish_cses_housing_2021.py validate --root .`
for current database checks; see the [v4 interface runbook](cses-housing-2021-resolution.md).
The review planner and combined preflight intentionally reject a changed catalog; preserve their
original outputs and replay them only against the matching historical state.
