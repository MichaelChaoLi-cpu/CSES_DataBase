# CSES 2004 Lighting Missing-Code Correction

Status: applied and independently validated on 2026-09-05. See the
[release record](releases/cses-lighting-correction-v1.md) for the completed result and fingerprints.
The prepare/rebuild/plan steps below describe the reviewed publication sequence, not instructions to
recreate its before state on the corrected database. Current-state checks use the `validate` mode.

## Approved scope

`cses-housing-lighting-missing-v1` implements the workflow approved by the user on 2026-09-05:
archive the value audit, correct the source rule, rebuild and inspect the local difference, synchronize
the verified correction to `mda`, and retain release and topology evidence.

Only `cses_data.final_HO_CSES.main_lighting_source_code` for survey wave 2004 and household `1501320`
changes, from 9 to NULL. The source row is `2004:2004hh_s03_housing.dta:11580`, whose original `q03_08`
value is 9 and Stata label is `missing`. Raw archives and source-variable labels remain immutable.
The source builder excludes 9 only for the 2004 lighting field; all other waves retain the prior rule.

The publication appends one approved alignment release, one revised source-to-canonical mapping, and
one load run. It keeps the earlier mapping intact and records its identity as superseded in the
correction load's validation summary. Consumers of this field should apply this release's override
to the baseline mapping. No canonical category/value mapping is introduced. Dataset-output edges
retain their original ingestion provenance; table identities, compatibility views, and schemas do not
change.

## Prepare and rebuild

```bash
uv run python rsc/cses_db/correct_cses_housing_lighting.py prepare --root .
uv run python rsc/cses_db/correct_cses_housing_lighting.py backup \
  --root . --backup-dir /Volumes/MikesDataBackup/PG_DB
uv run python rsc/cses_db/build_cses_ho.py
uv run python rsc/cses_db/validate_cses_ho.py
uv run pytest -q
```

Preparation verifies the approved source hash, exact raw row and label, and local baseline hash. It
retains the five pre-correction housing artifacts under the new release directory and records content
fingerprints for all 35 CSES physical tables plus structural/permission and compatibility evidence.
The protected housing fingerprint masks only the one approved cell, so changes to other lighting
values remain detectable. Other processing artifacts retain their before hashes.

The backup is a newly named custom-format dump in the existing external backup directory. Its four
table scope is housing, alignment releases, variable mappings, and load runs. It is not a full `mda`
backup. Its table-of-contents, full decompression, size, and SHA-256 are verified before application.
Recovery can restore the old cell from the before image; the dump provides additional scoped recovery
evidence. A recovery operation needs its own exact scope and should preserve append-only history.

The full local rebuild must change exactly one cell among 77,922 rows and 50 columns, preserve all
keys and dtypes, and add only one issue entry. Dictionaries, alignment summary, and housing coverage
audit remain byte-identical. Historical v1 catalog tests use the original Git-owned housing builder
and retained pre-correction artifacts in an isolated read-only fixture rather than accepting new
hashes as if they belonged to the original release.

## Plan and publish

Commit the correction implementation before producing its plan:

```bash
uv run python rsc/cses_db/correct_cses_housing_lighting.py plan --root .
```

The forced read-only plan checks the full local difference and the unchanged database, including
all-cell equality between the original local housing table and its live database counterpart. It pins
the before evidence, corrected artifacts, executable code, specification, prior mapping, and Git
revision. Preserve and review `data/releases/cses-housing-lighting-missing-v1/plan.json`, then pass its
literal SHA-256 as `--plan-sha256` to the following command. The scope was already approved in this
task; the argument binds execution to the concrete verified plan, not a new approval phrase.

For local/database cell comparison only, normalize the legacy database `source_archive` prefix
`data/raw/CSE/` to the local `data/raw/` prefix, as already accepted in baseline reproduction v0.1.
The plan and validation record this exception explicitly. Database source paths remain unchanged,
and before/after database fingerprints compare their original values without normalization.

```text
uv run python rsc/cses_db/correct_cses_housing_lighting.py apply --root . \
  --apply --plan-sha256 <verified plan SHA-256>
uv run python rsc/cses_db/correct_cses_housing_lighting.py validate --root .
```

The apply step verifies every pinned code/data input and the external backup before opening a write
transaction. It takes an advisory lock and consistent CSES table locks, checks the exact before state,
updates the natural-key/source-row/old-value matched row, and appends three metadata records. Any
unexpected content change, count difference, or all-cell local/database mismatch rolls back the whole
transaction. A completed release is validated as an idempotent no-op on retry.

Independent validation opens a new forced read-only transaction, repeats protected-state and all-cell
local/database comparisons, and binds the result to the import and plan hashes. Export graph v5 and
retain graphs v1–v4. Record the resulting DVC pointer and Git commits after publication.

## Historical evidence

Earlier baseline, variable-catalog, and value-audit plans describe the pre-correction release. Their
fingerprint gates intentionally reject the changed current builder/table. Do not rewrite their pinned
hashes or overwrite their evidence. Reproduce those releases with their matching Git/DVC revisions,
or use the isolated test fixture for the historical catalog tests. The correction's before/after
artifacts and validation describe the new current state.
