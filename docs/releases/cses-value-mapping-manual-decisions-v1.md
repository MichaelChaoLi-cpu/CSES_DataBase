# CSES Housing Manual-Review Decisions v1

- Date: 2026-09-05
- Decision: `cses-value-mapping-manual-decisions-v1`
- Status: 70 semantic decisions approved; database publication not authorized
- Source review SHA-256: `aec4d1184e3675ec30b69e79291c41c5838edebc9be45d42f3b0e1bc68fdd81f`
- Source database snapshot SHA-256: `35799d1996e5d75351da2f53feff9565296fc8c09feadb88a370bd6f4731f8b5`

The user accepted the exact proposed categories for all 70 records listed from the `manual_review`
bucket. The scope is fixed by the immutable source-review hash and the 70 unique review-row identities,
not by a broad category or raw-code filter. The accepted decisions comprise 18 dwelling-tenure,
38 cooking-fuel, and 14 lighting records across 2004, 2009, 2011-12, 2014, 2016, 2019, and 2021.

Approval accepts the proposed category names while retaining every qualification. Twenty 2014 records
still identify their questionnaire as provisional; 46 records retain unevaluated skip-routing notes;
25 retain residual or compound comparability notes. `Other`, `firewood_and_charcoal`,
`gas_and_electricity`, and `kerosene_or_diesel` remain distinct declared categories where applicable.
Evidence status is not silently upgraded, and source codes remain tied to their exact wave, dataset,
variable mapping, field, and code kind.

The DVC-owned decision bundle is under
`data/processing/cses/value_mapping_manual_decisions_v1/`. Its JSON records exact source keys,
approved canonical values and labels, current frequencies, original labels/options, qualifications,
and the source review-row identity-set hash. Its Markdown companion provides the complete 70-row table.

| Decision output | SHA-256 |
|---|---|
| `decisions.json` | `08fe761b003e737122e90bdf3f936c74cbba59ed16f4659886c67d2fcdfbaa51` |
| `decisions.md` | `0daed89959a27a61b43fd78d6db82871a18a8e423d8e560a940c548e98624bcd` |

The other 138 review rows are unchanged: 70 remain in the straightforward candidate bucket, 52 are
blocked by unresolved evidence, and 16 remain missing-only evidence. No decision row is marked
publication-ready. This record does not authorize a PostgreSQL transaction, create import SQL, append
an alignment release, populate `cses_value_mapping`, or create graph v6.

All 55 repository tests passed after adding the exact-scope and immutability checks. The decision
recorder uses no database connection and refuses to overwrite differing existing evidence. The source
review already carries the independent read-only database validation; a later publication plan must
repeat current database checks and bind itself to the selected approved decision set.

See the [review runbook](../cses-value-mapping-review-runbook.md) and the DVC-owned full decision table.
The current new code, documentation, review outputs, and decision outputs still require separate
Git/DVC synchronization before a database publication preflight should be prepared.
