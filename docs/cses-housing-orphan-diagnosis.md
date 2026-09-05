# Housing-to-household orphan diagnosis

Read-only diagnosis completed on 2026-09-06. All 19 original records remain unchanged.
Machine-readable per-record identities, source hashes and source-file matches are retained in
`data/processing/cses/housing_orphan_audit_v1/report.json` (DVC-owned), not copied into Git tables.

## Results

| Wave | Housing rows without HH match | Raw evidence | Interpretation |
| --- | ---: | --- | --- |
| 2004 | 16 | Every raw housing question is empty; all 16 appear in the heading-household file with missing household size; none appears in the member roster | Empty housing records without roster coverage; reason for non-completion is not documented |
| 2009 | 1 | 31 populated raw housing question cells; its household key is found only in the housing source among the inspected archive's DTA identifiers | Answered housing record with no matching original member/core/weight record; intended alternative identifier is unknown |
| 2014 | 2 | 42 and 46 populated housing question cells; both appear in household headers with totals of 3 and 4 persons and several other modules, but neither has member-roster rows | Genuine source-module coverage inconsistency; member detail cannot be reconstructed from household totals |

One of the 2014 households has three education records. These are the three already documented
2014 education-to-member orphans, not three newly introduced problems. No current-employment
record was found for either 2014 household or the 2009 household. The other 2014 household has
additional agriculture/construction records; these establish source presence, not roster detail.

## Why the current join behaves this way

The HH builder in `rsc/cses_db/cses_hh_hl_common.py` starts from member-roster households and
adds core/weight sources as context; household-header rows do not independently create HH rows.
The HO builder in `rsc/cses_db/cses_housing.py` starts from the housing source and uses a left
join to HH. Thus housing-only source keys are retained with `HH Link Matched = 0`.

All 19 keys were checked in the raw member files both as normalized household IDs and as
household prefixes derived from person IDs. None matched either way. Therefore the inspected
exceptions are not explained by the existing zero-padding rule or by rows being lost in the
current PostgreSQL join. Whether upstream collection, file assembly or original identifier
entry caused the gaps is not established.

## Checks and limits

The audit inspects 174 raw DTA members in the three source archives (60 for 2004, 61 for 2009,
53 for 2014), recording file fingerprints and the availability of `hhid`/`persid` identifiers.
It searches both identifiers with the existing wave-specific normalization rules, examines each
housing record by original one-based ordinal, and checks HH/HL/ED/EC local matches. Files without
these identifier fields are recorded but cannot establish household presence. This is not a
fuzzy-identifier search or an assertion that no alternative records exist anywhere else.

A forced read-only live transaction confirms the exact 19 keys and source identities and checks
that the physical HO-to-HH join has zero matches for the flagged records. The audit does not
modify database contents, local core artifacts, identifiers, weights or analytical samples.

## Recommended handling, not applied

- Preserve all records and source flags in the reusable database.
- Keep the 16 all-empty raw housing records distinguishable from the three answered records.
- Do not infer refusal, vacancy, ownership, respondent population or survey weights from absence.
- For the three answered records, seek an authoritative corrected source or documented identifier
  correction before linking to another household or synthesizing member/HH records.
- An analysis can define an explicit eligibility filter and report exclusions, but the database
  should not silently delete these records to force referential integrity.

Reproduce with `uv run python rsc/cses_db/audit_cses_housing_orphans.py --root .`.
The output is deterministic and refuses to overwrite a different historical result.
