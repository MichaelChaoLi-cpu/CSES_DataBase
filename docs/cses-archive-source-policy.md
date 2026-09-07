# Archive-first discovery for historical CSES code

## Why this adapter exists

The historical scanner discovers both loose DTA files and members of every ZIP below `data/raw/`.
After manual extraction, one original source can appear two or three times; loose macOS `._` files
can also resemble Stata sources. Employment's strict source-count contract correctly rejects this
expanded set. Do not delete user files, relax expected counts or rewrite historical acceptance hashes.

`rsc/cses_db/cses_archive_source_policy.py` adds an explicit, runtime-only discovery policy while
leaving the frozen scanner, builders and published implementation files byte-identical:

- Prefer the outer archive's original member identity.
- Exclude a loose file or separately extracted nested-ZIP member only when its extraction path
  corresponds to that original member and its SHA-256 matches exactly.
- Recognize both extract-here and extract-to-container-folder layouts.
- Retain changed copies and unrelated sources, including identical contents at independent paths.
- Exclude macOS metadata sidecars; never rewrite, remove or move source files.

The adapter is opt-in. Calling the old scripts directly still invokes their frozen behavior; use
the launcher when an original archive and its extracted files coexist. Existing release acceptance
gates remain active. This is input selection for reproducing the same original sources, not a new
database release or permission to rerun old imports against an expanded catalog.

## Read-only audit and execution

```bash
.venv/bin/python rsc/cses_db/cses_archive_source_policy.py --audit
.venv/bin/python rsc/cses_db/cses_archive_source_policy.py review_cses_employment_hours_status.py --help
```

For script arguments, put them after the script basename. The audit never runs a legacy program.
The launcher runs only the explicitly named script under `rsc/cses_db`; it does not select a write
mode or bypass that script's approval/backup checks. A caller can inspect detailed alias metadata
through `resolve_sources`; the audit CLI prints counts, not respondent answers.

The employment regression fixtures explicitly use the same `archive_source_policy()` context used
by the launcher. Assertions and frozen outputs remain unchanged; the adapter restores the legacy
discovery binding on normal and exceptional exits. It is intended for single-threaded execution.

## Git boundaries

Standalone SQL examples and generated SQL projections are ignored. Two required source inputs remain
tracked: `rsc/sql/cses_schema_v1.sql` and `rsc/sql/cses_public_to_functional_v1.sql`. The seasonal query
is reproducible from `projection_sql()`; its test validates the generator when the local SQL output
is absent, and checks the local output too when present. SQL links in older briefs refer to local
artifacts, not files guaranteed to exist in a GitHub-only checkout.

Raw data, questionnaire copies, derived Parquet and release evidence remain DVC-owned. This Git
publication does not update or upload those artifacts. Every newly staged file and every outgoing
Git blob is checked against a conservative **50,000,000-byte** ceiling before commit/push.
