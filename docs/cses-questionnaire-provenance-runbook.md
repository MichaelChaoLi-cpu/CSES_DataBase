# CSES Questionnaire Provenance Runbook

This is the preserved original v1 publication procedure. Its source counts and gaps describe that
historical release, not current questionnaire availability. For the reorganized ten-wave sources,
current 171-question checks and local candidate crosswalks, start with
[questionnaire organization](cses-questionnaire-organization.md). That workbench does not mutate
PostgreSQL; current published-state validation is in the [age interface runbook](cses-age-topcode.md).
Do not rerun this historical planner/importer against the expanded catalog or weaken its gates.

## Purpose

This release connects the DVC-pinned questionnaire files to the existing functional metadata model. It
uses `cses_alignment.cses_instrument`, `cses_alignment.cses_question`, and the nullable question fields
on `cses_alignment.cses_source_variable`; no new schema or table is required.

The reviewed v1 scope is deliberately conservative:

- fingerprint 14 distributed instrument files across 2004, 2007, 2009, 2011-12, 2014, 2016, and
  2019;
- register 164 whitespace-normalized question transcriptions from selected spreadsheet cells;
- link 291 existing source-variable records by same-wave, longest question-code prefix only;
- retain 2014 as provisional because the only located household questionnaire is explicitly a draft;
- register the 2019 image-only DOCX bundle without treating OCR as authoritative text; and
- preserve seven explicit documentation gaps, including no located questionnaire for 2013, 2017,
  or 2021.

Question text is not marked exact in v1. The database stores the source sheet and cell locator in
`repeat_context`, so a future review can promote individual transcriptions without changing their
identity.

## Ownership and safety boundary

- Git owns the specification, reviewed question subset, implementation, tests, and this runbook.
- DVC owns the generated preflight/import/validation evidence under `data/processing/cses/`.
- PostgreSQL writes are limited to one alignment release, 14 instruments, 164 questions, 291 updates
  to previously unlinked source variables, and one load-run record.
- The seven physical final tables, compatibility views, 4,092 source-variable identities, 280
  canonical variables, 1,714 source-to-canonical mappings, and empty value-mapping table are protected
  by preflight checks.

## Build the read-only plan

Commit the Git-owned implementation first, then run:

```bash
uv run python rsc/cses_db/plan_cses_questionnaire_provenance.py \
  --root . \
  --dbname mda
```

The planner verifies every source member SHA-256, all pinned evidence, the 171-dataset and
4,092-variable catalog, the functional table layout, existing records, and transaction read-only
state. It writes `data/processing/cses/questionnaire_provenance_plan_v1.json` and reports
`database_mutated=False`.

Version and push that plan with DVC, then commit and push the updated `data.dvc` pointer. Review the
plan before considering a database write.

## Explicit write gate

The importer refuses to run unless all of the following remain true:

1. `--apply` is present;
2. `--confirm` exactly equals `ACCEPT-CSES-QUESTIONNAIRE-PROVENANCE-V1`;
3. the reviewed plan is a successful non-mutating preflight;
4. the current desired state is byte-for-byte equivalent to the plan apart from the recorded Git
   revision; and
5. the Git-owned implementation has not changed since that recorded revision.

After a new explicit approval containing that exact phrase, run:

```bash
uv run python rsc/cses_db/import_cses_questionnaire_provenance.py \
  --root . \
  --dbname mda \
  --apply \
  --confirm ACCEPT-CSES-QUESTIONNAIRE-PROVENANCE-V1
```

The importer performs one PostgreSQL transaction under an advisory lock. A conflict, missing source
variable, changed question link, or protected-count difference aborts the transaction.

## Independent validation

After an approved import, open a separate forced read-only transaction:

```bash
uv run python rsc/cses_db/validate_cses_questionnaire_provenance.py \
  --root . \
  --dbname mda
```

Validation requires every planned record to reconcile as a no-op, verifies the exact reviewed plan
hash and code revision, and checks the expected insert/update counts from the import evidence. Version
the import and validation reports with DVC and record the final outcome in `docs/releases/`.

## Interpretation

A `reviewed` link means the released source variable name deterministically encodes the registered
question code; it does not assert that all response options or skip rules have been harmonized. A
`proposed` link is the same deterministic code match against the provisional 2014 draft. No source
value is mapped to a canonical category in this release.

Future releases should prioritize final questionnaire recovery for the documented gaps, exact-text
review, response-option extraction, and then a separately approved canonical value-harmonization
release.
