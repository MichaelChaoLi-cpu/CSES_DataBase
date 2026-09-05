# CSES Housing Value Mapping Preflight v0.10

- Date: 2026-09-05
- Planned release: `cses-housing-value-mapping-v1`
- Semantic approval: complete for 140 entries (70 manually qualified entries, then 70 candidates)
- Technical status: source review and forced read-only database preflight passed
- Publication status: planned; no database records inserted

The user's second approval accepts the remaining candidate entries and requests careful verification.
This record combines that approval with the preserved earlier manual-decision bundle. The complete
approved scope contains 28 tenure, 58 cooking-fuel, and 54 lighting entries across seven waves, forming
24 field-specific categories. Nine entries are documented options/labels with zero observed source
frequency; they remain legitimate dictionary entries, not fabricated respondent observations.

## Detailed source review

All ten raw housing datasets and 30 wave/field profiles were rebuilt and exactly matched to the pinned
review. All 140 selected entries have a substantive label interpretation, a unique source identity,
and a field-specific category key. The prior 70 manual decisions match exactly, including values and
display labels. The source review and decision bundles remain unchanged.

For 100 entries, the code, label, full option text, cell location, and skip annotation match the retained
questionnaire-cell extraction. The five original questionnaire members still match their archive-member
hashes. This check re-parses the retained cells; it does not claim a new extraction from XLS/XLSX. The
other 40 entries are supported by original Stata labels, which were re-read and then compared to the
database source catalog. No new source-label conflict or category change was identified.

Specific interpretation findings retained in the plan:

- 2016 lighting code 9 is `biogas`, while 2021 lighting code 9 is `other`. The 2004 missing sentinel
  remains excluded under the already accepted lighting correction.
- `kerosene_or_diesel`, `firewood_and_charcoal`, and `gas_and_electricity` retain their distinct meanings.
  Their counts cannot be split into component fuels from the available response alone.
- Public/city supply and private generation/generator are the approved electricity source groupings.
  Category names do not prove grid connection, provider ownership, off-grid status, or generator technology.
- Lighting `none` and cooking `no_cooking` are substantive responses in different fields. Neither is a
  missingness reason. The 2019 source spelling `None/don?t cook` is preserved alongside the approved label.
- All 20 selected 2014 entries retain provisional document provenance, 46 retain skip annotations,
  and 25 retain residual/compound qualifications. Approval does not establish a common analytical denominator.
- `other` remains a wave-specific residual; equal category names do not imply identical residual contents.

The 52 unresolved and 16 missing-only entries remain excluded. This release provides no new clean-fuel,
renewable-energy, access, or household-eligibility indicator.

## Database publication design

The existing schemas can represent the approved dictionary. Since value mappings reference a variable
mapping rather than a release directly, the plan appends 21 release-specific source-rule records and
attaches the 140 value entries to them. This makes the dictionary's release provenance explicit while
preserving all earlier source rules. Each planned rule retains the exact effective transformation.
In particular, the 2004 lighting rule is copied from mapping 1715 in the accepted lighting-correction
release, rather than from the superseded baseline mapping 57.

| Planned action | Records |
|---|---:|
| Alignment release | 1 |
| Versioned variable mappings | 21 |
| Value mappings | 140 |
| Load run | 1 |
| Total appended metadata records | 163 |
| Updates, deletes, or DDL changes | 0 |

The proposed value dictionary is auxiliary metadata describing the numeric source-code fields. It
does not replace physical numeric values with category text. A later consumer must select the desired
dictionary release explicitly; a separate analytical output contract would be needed for category views.
Questionnaire-derived labels stay in the linked evidence, while `source_label` in a value entry is the
original Stata label or NULL when that label was absent.

One forced `REPEATABLE READ, READ ONLY` transaction verified the 35 protected tables, the accepted
correction state, full local/live housing equality after the documented archive-path normalization,
the 21 unique effective source-rule identities, their source labels, an empty value-mapping table,
and the absence of the planned release. The protected baseline snapshot hash remains
`35799d1996e5d75351da2f53feff9565296fc8c09feadb88a370bd6f4731f8b5`.

## Evidence and next execution steps

The source review is pinned at
`aec4d1184e3675ec30b69e79291c41c5838edebc9be45d42f3b0e1bc68fdd81f`;
the earlier manual decisions at
`08fe761b003e737122e90bdf3f936c74cbba59ed16f4659886c67d2fcdfbaa51`.
All 140 approved identities, proposed value rows, 21 live mapping identities, and retained evidence
are in `data/processing/cses/value_mapping_release_v1/plan.json`. The human-readable companion is
`approved_scope.md` in the same directory.

| Output | SHA-256 |
|---|---|
| `plan.json` | `2f6fdca4705af007cdc982c71044adeada9fc54b97a40620d2871d3cc9577209` |
| `approved_scope.md` | `485c152a355dc989121a5a9adff311208c820d49f4779cdd89637ac4035db0e8` |

All 60 tests passed, including approved-subset protection, immutable prior decisions, source identity
validation, exact questionnaire option/skip checks, and effective correction-rule selection. Ruff and
Git whitespace checks passed. A second source/database preflight reproduced both output files exactly.

The plan has `preflight_passed=true`, `semantic_status=approved`, and `execution_ready=false`.
The implementation and accumulated evidence still await Git/DVC synchronization. Subsequent execution
preparation must verify a scoped backup of `cses_alignment_release`, `cses_variable_mapping`,
`cses_value_mapping`, and `cses_load_run`, then bind the transaction to the versioned implementation,
approved decision set, and fresh database state. Independent post-import verification and the next
lineage projection complete that publication workflow. No further semantic approval of these 140
unchanged category decisions is needed.
