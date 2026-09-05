# CSES Value Audit Runbook

## Scope

`cses-value-audit-v1` is a read-only pilot for three fields in `cses_data.final_HO_CSES`:
`main_lighting_source_code`, `main_cooking_fuel_source_code`, and `dwelling_tenure_source_code`.
It profiles all ten survey waves using the exact source datasets already linked by the accepted
variable catalog. It is not an importer, a replacement release, or an approval of candidate categories.
The existing `cses_alignment` schema can accommodate a later reviewed value-mapping release.

The pilot reads the entire selected source columns, including Stata system and extended missing codes.
It retains labeled but unobserved codes and questionnaire-only response options. Each code row records
its unweighted frequency, source label, located questionnaire option, proposed semantic category,
missingness classification, and unresolved issues. No respondent identifiers or individual records are
included in the report.

## Evidence and interpretation

- Git owns `rsc/specs/cses_value_audit_v1.json`, the extraction and audit scripts, tests, and these docs.
- DVC owns extracted questionnaire cells and generated reports under `data/processing/cses/`.
- Original archives, accepted evidence, existing Parquet tables, and database records are read-only.
- Archive, questionnaire member, accepted-plan, local-table, specification, and code hashes identify
  the inputs and execution. Before a new Git commit, the recorded HEAD is explicitly only the base
  checkout; file hashes identify the actual implementation. Runtime dependencies remain in `uv.lock`.

Five household questionnaires supply 100 located options for 15 wave/field profiles. The 2004, 2009,
and 2011-12 sources are XLS files; LibreOffice reads them through temporary XLSX conversions. The
2014 draft and 2016 XLSX files are read directly. Original archive-member hashes remain authoritative,
and converted workbook bytes are not treated as original source evidence. Formula cells are excluded.
The option specification selects exact cells so follow-up subquestions cannot leak into the code list.

All transcriptions remain normalized, non-exact text. The source question text is checked against its
previously cataloged cell. Option lines retain their original cell, text, and any skip instruction.
Skip routing is retained for review rather than applied to infer respondent eligibility.

Candidate categories use explicit text aliases, never code equality across years. Mixed categories
such as `firewood_and_charcoal` and `kerosene_or_diesel` remain distinct; `other` is a wave-dependent
residual requiring review. Unknown labels, including untranslated Khmer, remain unresolved. All 2014
option-based candidates retain their provisional status.

A code is classified as refusal, don't know, not applicable, or unspecified missing only when its
same-source label explicitly says so. Stata `.` and `.a`–`.z` remain distinct. A blank or undocumented
code does not establish why an answer is missing. Unresolved codes must not be counted as missing.

## Extract original questionnaire cells

Use the bundled Python executable returned by the workspace dependency loader. This extractor uses
the Python standard library and the installed LibreOffice executable; it does not install packages.
For this workstation:

```bash
/Users/lichao/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  rsc/cses_db/extract_cses_response_option_cells.py \
  --root . \
  --output data/processing/cses/response_option_cells_v1.json \
  --soffice /opt/homebrew/bin/soffice
```

The bundled Python location is a workstation command example, not a portable dependency path. The
script can run under Python 3.12+ elsewhere. LibreOffice uses an isolated temporary profile and deletes
only its own temporary conversion files. The extractor records the converter version and fingerprints.
If cell evidence changes, inspect the differences before updating its pinned hash in the pilot spec.

## Build the read-only report

```bash
uv run python rsc/cses_db/plan_cses_value_audit.py --root . --dbname mda
```

The database session explicitly uses `REPEATABLE READ, READ ONLY`, with a 55-second statement timeout.
It reconciles the accepted questionnaire release as 471 no-ops, checks protected catalog counts, and
compares the 30 selected live source-variable/mapping identities and labels against the pinned source
catalog. It then checks every published code frequency, including SQL NULL, against the pinned local
Parquet release. These are aggregate checks, not a new proof of every row-level mapping.

Outputs under `data/processing/cses/value_audit_v1/`:

| File | Purpose |
|---|---|
| `preflight.json` | Full profiles, per-code evidence, conflicts, checks and hashes |
| `code_review.md` | Complete human-readable cross-wave code comparison with source cell locations |
| `conflicts.md` | Published-code findings, missingness summary and remaining review work |
| `overview.mmd` | Review workflow projection, distinct from the authoritative database lineage graph |

`technical_checks_passed=true` means the evidence and database comparisons succeeded.
`publication_ready=false` remains explicit on the report and every code row. Semantic gaps are findings,
not reasons to hide or discard the report. A failed fingerprint, ambiguous source, changed questionnaire
cell, or failed database check causes a nonzero exit.

For deterministic reproduction, run again with `--output-dir` pointing to a fresh temporary directory
and compare all four output files byte for byte. Re-extract questionnaire cells separately to verify
the legacy conversion path as well. Tests cover missing-code reuse, conflicting evidence, draft and
untranslated labels, composite categories, extended missing values, and changed evidence fingerprints.

## Review before a later release

Prioritize the documented 2004 lighting missing sentinel retained in the current source-code column,
the undocumented 2021 tenure code 0, missing household evidence for 2007/2013/2017, and the untranslated
2021 lighting category. Review compound/residual categories and skip rules. Retain all seven broader
questionnaire gaps from questionnaire-provenance v1.

Any later write needs a concrete mapping or correction specification, its own validated plan, and
authorization for that release. This command has no apply flag or database-write path.
