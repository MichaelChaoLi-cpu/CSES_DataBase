# CSES Housing Value Audit Preflight v0.7

- Date: 2026-09-05
- Audit: `cses-value-audit-v1`
- Database: `mda`, forced repeatable-read/read-only transaction
- Outcome: technical checks passed; proposed categories remain unpublished

## Scope and result

The user accepted a read-only response-option and missing-code review, with a code comparison,
conflict report, and updated project topology. This pilot covers lighting source, main cooking fuel,
and dwelling tenure in `final_HO_CSES` across all ten survey waves.

| Measure | Result |
|---|---:|
| Selected raw housing datasets | 10 |
| Wave/field profiles | 30 |
| Questionnaire files used | 5 |
| Profiles with located questionnaire options | 15 |
| Located response options | 100 |
| Profiles with Stata value labels | 9 |
| Code rows, including unobserved documented codes and Stata missing | 208 |
| Field/code groups with different documented meanings across waves | 10 |
| Code rows whose meaning remains unresolved | 52 |
| Option-based code rows supported only by the 2014 draft | 20 |

The database remains unchanged: 4,092 source variables, 280 canonical variables, 1,714 variable
mappings, and zero canonical value mappings. The accepted questionnaire release reconciles as 471
no-ops. All 49 technical checks passed, including exact selected metadata and aggregate code-frequency
comparisons against the pinned Parquet release. The broader database lineage remains graph v4.

## Concrete findings

1. **2004 lighting, code 9:** one raw record is explicitly labeled `missing`; the same code remains
   present once in both the local and database source-code column. The existing builder accepts
   lighting codes 1–10 without a wave-specific exclusion of this sentinel. This finding calls for a
   narrowly reviewed correction, not a global exclusion of code 9.
2. **Code reuse:** lighting code 9 denotes `Biogas` in the 2016 questionnaire (zero observed records)
   and `Other` in 2021 source labels (38 observed records). Lighting code 7 changes from `Other` in
   2009 to `Solar` in later documented waves. Cooking fuel code 3 changes from a wood/charcoal mixture
   in 2004 to LPG in later documented waves.
3. **Existing null conversions:** one 2004 fuel code 99, labeled `missing`, is already absent from
   the published code distribution; one undocumented 2021 tenure code 0 is also absent. These are
   separately reported frequency differences. The reason for the tenure code is not inferred.
4. **Translation and documentation gaps:** the 2021 lighting code 8 has a Khmer label and six
   observations; its candidate category is withheld pending authoritative translation. The 2007,
   2013 and 2017 pilot sources have neither source value labels nor cataloged household option cells.
5. **Comparability boundaries:** compound fuel labels and residual `Other` are flagged rather than
   silently merged. The 2014 draft remains provisional. Skip instructions are retained at their
   original cells but are not used to infer respondent eligibility or missingness causes.

Across the three fields there are 129 Stata-missing variable observations, two observations with
explicit unspecified-missing labels, and 33,815 observations whose code meanings remain unresolved.
These totals sum field observations, not distinct households. No refusal, don't-know, or
not-applicable class was inferred without an explicit label. All seven broader questionnaire gaps
from questionnaire-provenance v1 remain visible in the machine-readable preflight.

## Evidence and reproducibility

| Artifact | SHA-256 |
|---|---|
| Questionnaire cells | `a6e2d004b4dd59b142f37eb27fda96c21b12bd8af01ceb98f11e6372b413d6f2` |
| Preflight | `e46fbd6d78322afdce885bd326253ebad9f4bc1e7940dc6f9943098ac87c24ca` |
| Complete code comparison | `1bffae4d6fd9240b8e7e73baa979930a960fe635f541d2b34319d66b4bca253e` |
| Conflict report | `9e21bda94d89ce685444c1489830e40dc548ced66ea3937a260d8e82e631f731` |
| Review topology | `fbe295dc302ebcb0f1d705718ea8bff771da0ab9e7489c43cd49e9b7382d5ed7` |

The extractor was independently rerun from the original archives, and the audit was rerun in a fresh
database transaction with a separate output directory. The cell evidence and all four audit outputs
were byte-identical. The source archive and accepted-evidence hashes were checked on both audit runs.
All 33 tests passed, including seven new regressions for missing-code reuse, conflicting evidence,
option parsing, provisional/untranslated labels, composite fuels, extended missing values, and
fingerprint tampering. Ruff and Git whitespace checks passed.

The preflight records base Git revision `a2bd573` and the SHA-256 of each executed code/dependency file;
it does not claim that new implementation files were already committed at that base revision.
The source data revision remains `md5:d427da93fcdec9b304ec73362803c420.dir`.
The resulting local DVC pointer is `md5:a24546010057cb38153543cfdf0d7490.dir`, with 83 files and
472,402,626 bytes. Only `data/` changed; `etc/` and its pointer were not updated. The local DVC workspace
and cache reconcile. No DVC transfer or Git commit/push was performed in this preflight task.

## Review entry points

- [Conflict report](../../data/processing/cses/value_audit_v1/conflicts.md)
- [Complete code comparison](../../data/processing/cses/value_audit_v1/code_review.md)
- [Read-only runbook](../cses-value-audit-runbook.md)
- [Updated topology](../cses-topology.md)

The next database release must define the exact corrected or mapped values and review any remaining
semantic choices. This preflight does not contain an importer or an executable recode release.
