# CSES 1996 1997 1999 2023 and 2025 alignment

## Current scope

**Analysis warning from the subsequent read-only pilot:** the published 2025 age projection
contains only 165 non-null values because it selects `q01ac05a`, not the complete native calculated
`age` field. Do not use it to define 2025 age-specific denominators. School attendance also requires
explicit handling of never-attended skips. See the [pilot findings](#read-only-alignment-pilot).
Publication integrity checks remain valid; they verified the selected projection, not completeness
of the source-field choice for a particular analysis.

A subsequent [source-gap audit](#source-completeness-and-missingness-audit) also found that the
2025 treatment-sought item is answered only for injured members, not the 14,695 illness cases.
Do not interpret those nulls as No or use this item as a complete all-illness treatment indicator.

The five additional Cambodia survey waves are now published in an additive, qualified
[database release](#additional-wave-database-release). Their immutable local alignment candidates
and review supplements remain the source evidence.
The build inventories all 173 Stata datasets and 5,427 physical variable occurrences, caches
10 questionnaire/reference files, and materializes 33 wave/module tables plus seven combined
module tables. It implements 171 explicit field-wave mappings across 74 distinct module/target
pairs. Of these mappings, 51 perform value-label-verified binary or sex recodes; 120 retain
native values. These are not counts of fully harmonized variables.

PostgreSQL now holds the historical ten waves plus these five waves in separate versioned tables. No database relation,
approved dictionary, existing questionnaire library v1, historical release, or DVC pointer was
replaced. These projections are not a drop-in append to the historical 280-column catalog. Use
the explicit new interfaces and their qualified target names; not all native fields are materialized.

## Record denominators

| Release wave | Source datasets | Native variables | Household records | Roster member records | Field-wave mappings |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1996 | 13 | 566 | 9,000 | 46,811 | 25 |
| 1997 | 25 | 462 | 6,010 | 29,931 | 25 |
| 1999 | 46 | 1,111 | 6,000 | 32,348 | 30 |
| 2023 | 42 | 1,203 | 12,096 | 51,914 | 47 |
| 2025 | 47 | 2,085 | 12,338 | 51,775 | 44 |
| Total | 173 | 5,427 | 45,444 | 212,779 | 171 |

These are released household and roster member records, not verified direct respondents or unique
people across waves. Proxy response and module eligibility vary. In particular, the 1996 combined
person file contributes its entire roster to the ED, EC and HEALTH candidates; that does not mean
all members answered those modules. Preserve each field's non-null denominator and eligibility.

Original candidate counts below retain the three extra 2023 EC rows. The qualified database
module has 51,914 rows for that wave; all 51,917 candidate rows remain in the separate audit table.

| Wave | ED candidate rows | EC candidate rows | HO candidate rows | HEALTH candidate rows |
| --- | ---: | ---: | ---: | ---: |
| 1996 | 46,811 | 46,811 | 9,000 | 46,811 |
| 1997 | 26,675 | 22,349 | 6,010 | 29,931 |
| 1999 | 29,002 | 29,002 | 6,000 | 32,348 |
| 2023 | 49,475 | 51,917 | 12,096 | 51,914 |
| 2025 | 51,775 | 51,775 | 12,338 | 51,775 |

HH, HL, ED, EC, HO and HEALTH candidates exist for every added wave. SURVEY_DATE contains
native visit/date components for 1996, 2023 and 2025, not inferred timestamps. No new village
table is built; area-information files are not treated as village questionnaire responses.
The 1997/1999 date and all five village module slots remain explicitly unbuilt.

## Identifiers and source choices

- **1996:** `province + district + commune + village + round + srn` identifies a household;
  append `c01` for a member. `srn` alone has only 305 distinct values among 9,000 households.
  Neither a sample reference nor a village number alone is a household key.
- **1997 and 1999:** retain native `hid` and `pid`. The 1999 `C01_Person1.dta` roster is selected
  explicitly; comparison with `C01_C02Person.dta` found no common-field value discrepancies.
  The combined file is inventoried, not appended as another set of people.
- **2023:** use `hhid` and `persid`. Both original and augmented HEALTH variants remain inventoried.
  The chosen `S13_PersonIllness.dta` values are candidates, not a declaration that this version
  resolves all conflicts.
- **2025:** use interview UUID `interview__id` plus `hh_members__id`. Do not cast UUIDs to numeric
  IDs or infer old-width person IDs. The household HEALTH access file `S13A` is not the person
  illness file; this build selects `S13B_PersonIllness.dta` for the latter.

Normalized keys are JSON arrays of the release wave and source components. String leading zeros
are preserved; missing, fractional and unsafe numeric identifiers are not silently coerced.
The five HH/HL spines have no missing or duplicate keys. All selected module records link to HH,
and all selected person records link to HL. No row is removed to obtain those results.

## Actual transformations and qualifications

Every selected field includes a `source__<native_name>` column next to its target value. The
field-level ledger records source labels, attached dictionaries, source/mapped non-null counts,
distinct values, numeric frequencies, transformation status and qualifications. Label-verified
binary recodes use the attached Yes/No definitions rather than assuming code 1 always means Yes.
Missing Stata values remain null, with extended missing codes retained in source-position sidecars.

The 45 observed non-null cells not recognized by the binary dictionaries remain in source columns
and become null only in the recoded output:

| Wave | Module and field | Cells |
| --- | --- | ---: |
| 1997 | ED ever attended school | 2 |
| 1997 | ED currently attending school | 9 |
| 1997 | HEALTH treatment sought | 1 |
| 2023 | ED ever attended school | 1 |
| 2023 | HEALTH treatment sought | 1 |
| 2023 | HEALTH hospitalized | 2 |
| 2025 | ED can write | 29 |

The 2025 writing exceptions are native code 0; they are not interpreted as No. In the combined EC
table only, occupation and industry source-code targets become text because the releases mix numeric
and string storage. Per-wave tables preserve native types and remain the basis for exact source
comparisons. No occupational or industry classification crosswalk is claimed.

Important semantic limits:

- The 1996/1997/1999 literacy item combines reading and writing. It stays a combined indicator,
  not two independently observed answers.
- Age stays `Age Source Value`. The two 1999 age-98 records are explicitly marked 98 or older.
  Follow-up questionnaire review also confirms the four 1996 age-98 records mean 98 or older
  (see below); the immutable v1 outputs have not been rewritten. Other waves' top-code
  interpretations remain unverified. No exact age is imputed for a topcoded observation.
- The 1996 HEALTH fields concern disability and under-five diarrhoea over two weeks, not the
  modern all-person recent-illness measure. The 1997 screen refers to major illness/injury/health
  problems; 1999 includes other health-care needs. These screens remain distinct.
- Education levels, relationship codes, marital status, ethnicity, housing categories and weights
  are not assigned the historical harmonized dictionaries simply because numbers coincide.
- The 2025 employment screen separates work for someone else for pay, platform income activity,
  family business/farm assistance, absence and other routes. It is not the old screening algorithm.
- The 2025 `s15q31` is usual hours per day, not actual hours during the past seven days. Earnings
  retain their time-unit code. No multiplication or monthly conversion is applied.
- The 2025 cooking-fuel question concerns the primary cookstove over the past 12 months; drinking
  water is not explicitly wet-season water. Both have separate qualified target names.
- The 2025 weight label refers to 2025/26. `Survey Wave=2025` identifies the supplied archive;
  it is not confirmation that all fieldwork occurred in calendar year 2025.

## Unresolved source conflicts

The 2023 EC file has 51,917 rows for 51,914 member keys. Its three duplicate keys involve six
retained rows. `Duplicate Key=True` prevents treating those rows as unique source records.

Comparing the 2023 illness variants finds four differing cells across four people: one treatment
response (`q13bc06`) and three first-provider codes (`q13bc09a`). All four people are marked
`Source Variant Conflict=True`. The exact primary/alternate values and keys are in the DVC-owned
variant report, not copied into Git documentation. No preferred answer is imputed.

`Unique Source Record Eligible` means only that a source record has a complete, unique key and
no detected variant conflict. It is **not** a questionnaire eligibility flag, permission to pool
waves, or analysis certification. Field-specific missingness and scope still apply.

## Questionnaires without reopening archives

Originals are under `data/processed/cses_questionnaires/additional_waves_v1/<wave>/forms/`.
This separate extension leaves the fingerprinted historical `v1` library untouched.

| Wave | Cached originals | Searchable extraction |
| --- | --- | --- |
| 1996 | `QuestENG_Form2.DOC` | Literal text cached in `legacy_word_text_v1/1996/` |
| 1997 | `QuestENG_Form3.pdf`, `QuestENG_Form4.pdf` | 16 and 15 pages respectively |
| 1999 | `QuestENG_Form3Cover.doc`, `QuestENG_Form3Page.doc`, `QuestENG_Form4.doc`, `ManualENG_Editing.doc` | Literal text cached in `legacy_word_text_v1/1999/` |
| 2023 | `CSES2023 HH Quest ENG.pdf`, `Household FormCSES2023_KHM.pdf` | English cover only, 1 page; Khmer form, 68 pages |
| 2025 | `CSES2025_Household_Questionnaire_ENG.xlsm` | 64 sheets, 8,011 literal non-formula cells |

Ten is a file count including one editing manual and a separate cover, not ten complete instruments.
PDF page text and Excel cell coordinates are cached in `text/` as JSON and Markdown. Text extraction
is not semantic verification or OCR, and no macro is executed.

The 2025 workbook contains both revised and older sheets. For example, revised `Labor (2)!F6:F7`
identifies question 2 as paid work for someone else, while `G6:G7` identifies question 3 as
web/app income activity. `AP6:AP7` is question 30, usual days per week; `AQ6:AQ7` is question 31,
usual hours per day. Older `15 Current Eco-1` and related pages must not override those locators.
`02 Education (2)!L10` and `O10` separately ask reading and writing. These located cells support
the noted distinctions, but are not a complete set of approved source-question links.

## Reproduction and verification

The Git-owned specification is `rsc/specs/cses_additional_waves_v1.json`. It pins all five archive
hashes, exact source members, native keys, candidate field rules and variant comparisons.

```bash
.venv/bin/python rsc/cses_db/build_cses_additional_waves.py build
.venv/bin/python rsc/cses_db/build_cses_additional_waves.py verify
```

The build refuses a different archive hash, changed manually extracted copy, missing mapped column,
ambiguous HH/HL spine or differing pre-existing output. Verification reads cached outputs only.
Use the bundled document Python runtime for the optional searchable questionnaire extraction:

```bash
python rsc/cses_db/extract_cses_additional_questionnaires.py --root .
```

That runtime needs `pypdf`; the project build itself uses the existing project dependencies.
No install or environment modification is performed by these commands.

Outputs under `data/processing/cses/additional_waves_v1/`:

- `datasets.json` and `variables.json`: complete native inventory and Stata dictionaries.
- `field_alignment.json`: 171 field-wave rules with counts and retained limitations.
- `tables/<wave>/<module>.parquet`: source-preserving, qualified per-wave candidates.
- `tables/all_<module>.parquet`: combined additional-wave candidates, not historical table replacements.
- `summary.json`, `module_coverage.json`, `source_variant_comparison.json`: coverage and exceptions.
- `source_missing/`: extended Stata missing-value positions.
- `manifest.json` and `lineage.json`: artifact hashes and local dependencies, not a new database graph.

The lineage runs from five pinned archives to the explicit source members and local module candidates,
with HH and HL linkage checks. The stored graph covers archive-to-candidate and spine dependencies;
member/field detail resides in the inventory and mapping ledger.

## Follow-up review: 2023 conflicts and legacy Word evidence

An additive local review is stored at `data/processing/cses/additional_wave_review_v1/`.
It does not replace the original v1 candidates or publish database tables.

- Employment: 51,917 source rows become 51,914 unique-person candidate rows. Of the three
  duplicate pairs, two contain a completely blank question row; the third contains only
  monthly wage (`q15_c20 = 1120000`), identical to the more complete row. Every non-null
  answer in the sparse row agrees, and all non-question context agrees. Only strict,
  conflict-free subsets qualify; answer count alone is insufficient. All six source-row
  references survive in `All Source Row Numbers`, and historical duplicate flags remain.
- Health: one treatment discrepancy (0 versus null) yields missing under the existing
  dictionary validation. Three first-provider discrepancies (98 versus 18) remain
  unresolved: both dictionaries define 98 as "Don't know" and 18 as "Other (Specify)
  Overseas Medical Service:". The qualified provider field is null for those three rows;
  both native versions remain available. No unsupported unknown-to-other recode is adopted.
- Legacy Word: all five DOC files now have hash-verified literal TXT and line-indexed JSON
  caches under `data/processed/cses_questionnaires/additional_waves_v1/legacy_word_text_v1/`.
  These comprise questionnaires, a cover and an editing manual, not five complete instruments.
  Embedded objects and full document layout are not certified by text extraction.
- Age evidence: visual inspection of the 1996 form's printed page 3 of 21, Part II column 8,
  and the 1999 form's printed page 2 of 15, column 9, confirms that 98 means **98 or older**.
  There are four such source records in 1996 and two in 1999. The additive age qualification
  described below now encodes this evidence; the existing HL outputs remain unchanged. Exact-age analyses must
  not treat these six observations as known exact ages of 98. Only these relevant pages,
  not every page of the legacy documents, received visual verification.
- 2025 writing: 29 zero codes remain unrecognized. Of these, 28 report no reading and one
  reports reading; this does not establish that writing code 0 means "No".

Reproduce the additive review and legacy extraction without overwriting differing artifacts:

```bash
.venv/bin/python rsc/cses_db/extract_cses_legacy_word.py
.venv/bin/python rsc/cses_db/review_cses_2023_conflicts.py
.venv/bin/pytest -q rsc/tests/test_cses_additional_review.py
```

The Word extractor requires macOS `textutil`. Its manifest pins the converter, script,
originals and generated text. The conflict-review manifest pins its script, original
candidate manifest, archive and outputs. The review's uniqueness qualification is structural,
not a claim of full cross-wave comparability or database publication readiness.

## Additive age qualification and 1999 schooling routes

`data/processing/cses/additional_age_review_v1/` contains separate qualified HL tables
for 1996 (46,811 records) and 1999 (32,348 records), plus an evidence summary and hash manifest.
All original fields and rows remain unchanged. New fields are:

- `Age Exact Years Qualified`: reported completed years 0–97; null for topcoded, missing or invalid ages.
- `Age Lower Bound Years Qualified`: reported age for 0–97 and 98 for the topcoded group.
- `Age Topcoded Qualified`: true for 98+, false for valid non-topcoded ages, null for missing/invalid ages.
- `Age Qualification Status` and `Age Evidence ID`: interpretation and questionnaire provenance.

The four 1996 and two 1999 topcoded observations therefore do not become exact ages of 98.
There are no missing or invalid source ages in these two roster candidates. “Exact” here means
an uncensored reported completed-year value, not independent verification of a person's true age.
Other waves are not assigned this topcode rule without their own evidence.

The 1999 questionnaire explicitly limits schooling and economic activity to household members
aged 5 or older (cached JSON lines 553 and 837). Each module contains exactly all 29,002 roster
members satisfying that age threshold: no eligible member is absent, no under-five member is
included, and no module key is unmatched. This checks age coverage, not usual-residence status
or every question's eligibility. The remaining 3,346 roster members are under five.

`data/processing/cses/education_1999_route_review_v1/` preserves the complete ED table and adds
`Route Review Status`, with these results:

| Route audit status | Records |
| --- | ---: |
| No detected anomaly in the reviewed routes | 20,735 |
| Never attended school; downstream fields skipped | 8,255 |
| Ever attended; current attendance missing, current grade also missing | 11 |
| Ever attended; current attendance missing but current grade supplied | 1 |

The 12 missing current-attendance answers are retained as missing. A supplied current grade
does not authorize inferring attendance; neither is missing attendance recoded as No. The two
“No → column 9” instructions are retained with the extracted schooling section in the report.
This is a candidate route audit, not certification of all schooling items or new visual
verification of table alignment. Employment item-level routes remain to be reviewed separately.

```bash
.venv/bin/python rsc/cses_db/qualify_cses_legacy_age.py
.venv/bin/python rsc/cses_db/audit_cses_1999_school_routes.py
.venv/bin/pytest -q rsc/tests/test_cses_legacy_qualification.py
```

Both supplements refuse to overwrite differing existing output. Their manifests record code
and input hashes; reruns reproduce the same output. No database, Git or DVC publication occurs.

## Local geography feasibility test (2026-10-03)

The initial test writes only to `data/processing/cses/geography_feasibility_v1/`. Database queries use
a read-only, repeatable-read transaction. The 2004–2021 denominator comes from the database HL
table; the five added waves come from pinned original rosters. Counts represent roster members,
not individually interviewed respondents or people tracked between waves. The corrected 2004
supplement at `data/processing/cses/geography_feasibility_2004_supplement_v1/` supersedes only
the initial 2004 result. It uses original roster/cover records and the same pinned references,
opens no database connection, and retains the other 14 waves unchanged. The table below includes
this correction; the original v1 artifacts are preserved for audit.

The [official 2025 village directory](https://data.mef.gov.kh/datasets/pd_66a8603a00604c000123e147)
contains 14,576 rows and no coordinates or polygons. Its original CSV is retained unchanged.
String parsing preserves leading zeros. The test excludes 105 rows: the union of 80 rows with
26 duplicated village codes, 9 malformed codes, and 43 inconsistent parent-code rows. These
categories overlap. The remaining 14,471 records are eligible for unique code matching.
Excluded reference records are not repaired or selected by first-match logic.

| Wave | Roster members | Unique village codes matched / available | Members matching 2025 village directory | Members matching commune polygons | Members matching district polygons |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1996 | 46,811 | 597 / 740 | 82.12% | 89.11% | 97.95% |
| 1997 | 29,931 | 363 / 473 | 77.67% | 86.91% | 95.44% |
| 1999 | 32,348 | 471 / 600 | 78.88% | 88.15% | 97.11% |
| 2004 | 74,719 | 707 / 867 | 80.59% | 87.72% | 94.01% |
| 2007 | 17,439 | 282 / 349 | 81.20% | 88.85% | 95.72% |
| 2009 | 57,105 | 566 / 715 | 80.16% | 86.85% | 94.13% |
| 2011–12 | 16,327 | 273 / 355 | 75.60% | 85.66% | 95.90% |
| 2013 | 17,225 | 312 / 383 | 81.36% | 92.10% | 94.98% |
| 2014 | 53,968 | 819 / 1,000 | 81.47% | 92.64% | 95.54% |
| 2016 | 16,985 | 315 / 383 | 82.95% | 93.94% | 97.23% |
| 2017 | 16,909 | 309 / 384 | 80.51% | 92.18% | 95.80% |
| 2019 | 44,548 | 874 / 1,008 | 86.87% | 95.80% | 100.00% |
| 2021 | 43,695 | 887 / 1,007 | 88.19% | 95.84% | 100.00% |
| 2023 | 51,914 | 890 / 1,007 | 88.48% | 93.51% | 97.03% |
| 2025 | 51,775 | 885 / 1,022 | 86.50% | 94.10% | 98.34% |

All percentages use roster members, not village counts or sampling weights. The reference
polygons are the existing 197 district and 1,633 commune entities in `mda`, with boundary date
2014-10-14 and `valid_on` 2018-10-04. Presence of nonempty polygon coordinates is checked;
topological validity and historical boundary equivalence are not certified. Village-directory
and polygon matches refer to different reference vintages and must not be combined as a
validated hierarchical crosswalk.

**No village geometry match rate is established for any wave.** The available verified spatial
references stop at commune level. A same-code entry in the 2025 directory does not prove that
an older village retained its name, extent or identity. No fuzzy-name mapping, village centroid
substitution, historical code repair or database publication was performed.

### 2004 correction: omitted cover fields, not absent original geography

The initial test consumed the existing database roster, which lacked district/commune/village
columns' values. Inspection of `CSES 2004/Stata 2004/2004hh_s99_singlequestions.dta` recovered
`q40_prov`, `q40_dist`, `q40_comm`, `q40_vill` and `q40_psu`. The prior claim that original 2004
geography was unavailable was incorrect: the existing processing path had not joined these fields.

Of 15,000 household source rows, 14,984 contain complete geography. An exact, many-to-one `hhid`
join supplies all 74,719 roster members with geography, with no imputation. Cover PSU/province
agree with roster PSU/province; all 900 PSUs have internally consistent geography. These PSUs
represent 867 distinct composite village codes, not 900 distinct administrative villages.

- Village directory: 60,218 members, 707 of 867 source village codes matched (80.59% of members).
- Commune polygons: 65,544 members (87.72%).
- District polygons: 70,247 members (94.01%).
- The excluded/ambiguous reference-code group affects 132 members; they are not counted as matched.

The supplement stores a code-level aggregate and updated all-wave summary, with source archive,
prior snapshot and script hashes. Reproduce offline with
`.venv/bin/python rsc/cses_db/retest_cses_2004_geography.py`. Production tables and the first test
are unchanged. Complete source-code coverage does not certify historical village identity or
village geometry.

The script `rsc/cses_db/test_cses_geography_local.py` saves the reference snapshots, aggregated
legacy input, source hashes and per-wave summary. Unmatched and ambiguous codes require a
separate historical/name review before any analytical geographic release.

## Remaining alignment work after qualified publication

The original geography-interface release below covers only the older ten waves and recovered
2004 fields. The later [additional-wave release](#additional-wave-database-release) publishes
the selected new modules and a geography v2 interface without replacing the older release.

1. Preserve the adopted 2023 employment projection and retain the three HEALTH
   provider disagreements as unknown unless authoritative correction evidence becomes available.
2. Review remaining questionnaire scopes, routes, missing codes and category crosswalks. Complete
   source-question links for the extracted legacy Word text and the relevant Khmer question review;
   retain all alternate sheet versions. Continue other waves' age qualifications and item-level
   employment routes; retain the 12 unresolved 1999 schooling responses without imputation.
3. Expand candidate coverage beyond these 74 module/target pairs, including deferred source modules,
   classification dictionaries and survey-design variables. Not every one of the 5,427 native fields
   has a canonical mapping.
4. Keep future expanded mappings or modules in separately reviewed releases. Do not rerun the
   historical builders over the expanded wave set to overwrite accepted outputs. The named
   qualified release below has its own approval, plan, backup, protected-data checks and load record.

Git owns only code, specifications and documentation. Raw archives, questionnaire copies and derived
data stay under DVC ownership. No Git commit, push or DVC add/push accompanies this publication;
the existing 50,000,000-byte Git file limit remains in force.

## Geography interface release: approved scope

**Published on 2026-10-03**, alignment release ID 12. The household interface contains 77,904
records and the person interface 358,920 records across the ten existing database waves.
All person records link to household geography, all have complete composite source geography,
and the checked PSU/province context has zero conflicts. Nineteen pre-existing physical data
and analysis tables retained identical row counts and ordered row-hash fingerprints across
the publication transaction. This is source-code coverage, not 100% map matching.
Independent postflight passed, and all ten waves' county/commune match counts agree with the
frozen feasibility results. The full regression suite passed 507 tests; Ruff and whitespace
checks passed. The backup was fully decompressed successfully before publication.

The user approved the first optimization batch: recover 2004 geography and expose unified
household/person geography without replacing legacy tables or compatibility interfaces.
The publisher is `rsc/cses_db/publish_cses_geography_interface.py`; execution and validation
evidence is stored under `data/releases/cses-geography-interface-v1/`.

| New relation | Purpose |
| --- | --- |
| `cses_data.cses_geography_2004_source_v1` | 14,984 exact household-level q40 source records, archive/member/row provenance, unique household key |
| `cses_analysis.cses_household_geography_v1` | One record per existing HH key; legacy codes retained separately from qualified local components and composite administrative codes |
| `cses_analysis.cses_person_geography_v1` | One record per existing HL key; left join to household geography, explicit household-link status |
| `cses_analysis.cses_geography_coverage_v1` | Per-wave roster denominators, source-code coverage, county/commune polygon-code matches and context conflicts |

The new source table joins on **wave and household ID**, not guessed village/PSU equivalence.
The interface does not alter `final_HH_CSES`, `final_HL_CSES`, `dim_geo_CSES` or public compatibility
views. Consumers must explicitly select the new views to obtain recovered geography. Old geographic
fields remain unchanged for reproducibility. This original release did not publish the five added
waves; their later publication is described below.

`admin1_code` through `admin4_code` are full composite source codes. `province_component` through
`village_component` retain the two-digit local components. Source codes can identify a survey-era
village but do not certify its historical identity or shape against a later reference.
County and commune matches are live joins to the existing `public.dim_admin2_cambodia` and
`public.dim_admin3_cambodia` references, with their dates exposed. The reference objects are not
modified. The village-directory feasibility test is deliberately not promoted into this interface:
`village_directory_status` is `not_evaluated_in_this_interface`, village geometry is explicitly
unverified, and `historical_identity_verified` is false.

```sql
SELECT * FROM cses_analysis.cses_geography_coverage_v1 ORDER BY survey_wave;

SELECT survey_wave, person_id, household_id, psu,
       admin1_code, admin2_code, admin3_code, admin4_code,
       geography_source_status, boundary_match_status, village_geometry_status
FROM cses_analysis.cses_person_geography_v1
WHERE survey_wave = '2004';
```

Before publication the four CSES schemas are backed up with `pg_dump -Fc`; the complete archive
is decompressed with `pg_restore --file=/dev/null` and hashed. This verifies readability, not a
restore into a separate server. The backup is local at
`data/backups/cses_geo_v1/cses_before_geography.dump`, under Git-ignore/DVC ownership; no Git or
DVC push is implied. No shared public boundary relation needs restoration because it is read-only
throughout this release.

Publication uses an advisory transaction lock, protects the three core geographic inputs with
share locks, rejects existing target objects, and validates exact source rows and interface keys.
Existing physical `cses_data` and `cses_analysis` tables have row counts and ordered row-hash
fingerprints compared before/after; changed legacy data aborts the transaction. Metadata receives
an additive release, load run, storage registration and original-dataset edge.

Do not rerun publication after an ambiguous connection failure. Inspect the release and target
objects first. The publisher refuses existing targets instead of replacing them. Normal postflight:

```bash
.venv/bin/python rsc/cses_db/publish_cses_geography_interface.py validate
```

This release does not promote primary/foreign-key constraints on legacy tables, infer village
coordinates from commune centroids, or make older immutable pipeline validators aware of the new
objects. Historical validators with a fixed relation-count contract need their own version update.

## Additional-wave database release

**Published and independently validated on 2026-10-03 as alignment release ID 14.** The user authorized
publication of the five new waves, with alignment qualifications retained. The additive release is
`cses-additional-waves-qualified-v1`; it does not append incompatible columns or identifiers into
the historical `final_*` tables and does not replace any public compatibility interface.

| New physical module table in `cses_data` | Records | Coverage |
| --- | ---: | --- |
| `cses_additional_hh_v1` | 45,444 | All five waves; household-wave key |
| `cses_additional_hl_v1` | 212,779 | All five waves; member-wave key |
| `cses_additional_ed_v1` | 203,738 | Released education records; eligibility differs by wave |
| `cses_additional_ec_v1` | 201,851 | Includes the reviewed 2023 duplicate fold |
| `cses_additional_ho_v1` | 45,444 | All five waves; household-wave key |
| `cses_additional_health_v1` | 212,779 | Different screening concepts and question universes retained |
| `cses_additional_survey_date_v1` | 33,434 | Native timing fields for 1996, 2023 and 2025 only |

Columns use snake_case. `survey_wave`, `household_key` and `record_key` are explicit identifiers;
the latter two retain the candidate's native-component JSON-array strings. In particular, the
2025 interview UUID is never coerced to a number. These are within-wave identifiers, not longitudinal
person identities. New module keys are unique, and exact household/person links are enforced with
foreign keys on the new tables only. The historical retained-orphan policy is unchanged.

`source_values` is a JSONB object containing the selected native key/response fields with their
original per-wave scalar types. It is not a copy of every column in every native dataset. The
typed analytical columns preserve source-code, unit and scope qualifications. Mixed string/numeric
occupation or industry targets use text; the native scalar remains in `source_values`. Original
candidate flags such as `duplicate_key`, `unique_source_record_eligible`, `alignment_status` and
`age_interpretation` are retained, not silently rewritten to claim complete alignment. Consult
the corresponding qualified status fields. Supplemental qualified columns apply only to their
reviewed waves: for example, `qualified_unique_record_eligible` is populated for 2023 EC, and
`first_provider_qualified_source_code` for 2023 HEALTH. Do not filter all years by a supplement-only
flag or globally replace source fields with supplement-only columns; that would remove valid
records or manufacture missing values in the other waves. The EC table's primary key establishes
record uniqueness for all five published waves.

Important retained restrictions:

- The 1996 and 1999 age-98 cases mean **98 or older**: six records retain the source age and lower
  bound, with null exact age. Other waves are not automatically assigned that age rule.
- The 1999 education projection preserves all 12 unresolved current-attendance responses and
  exposes `route_review_status`; it does not impute answers from adjacent questions.
- The 2023 EC analysis table has 51,914 unique records and retains all contributing row numbers.
  `cses_additional_ec_2023_source_v1` separately preserves all 51,917 original candidate rows.
- The 2023 HEALTH provider conflicts keep both versions and null qualified provider values where
  the evidence does not support choosing a version. Native unknown values are not reassigned to
  substantive provider categories.
- Combined literacy in 1996/1997/1999 is not separate reading and writing. The 2025 writing-code-0
  cases remain unclassified. Daily/weekly work hours, mixed-period earnings, health screening and
  source classification codes are not given blanket cross-wave equivalence.
- No new VL records or 1997/1999 timing records are fabricated. The catalog of 173 source datasets
  and 5,427 variables is broader than the selected modules actually materialized here.

### Geography and provenance access

`cses_data.cses_additional_geo_v1` contains 45,444 household geography records derived from the
original rosters, retaining archive hash, member and contributing row numbers. Every household's
members must agree on their administrative codes. `cses_analysis.cses_additional_person_geography_v1`
links the five new rosters; `cses_person_geography_v2` unions this interface with the unchanged v1
interface for the older ten waves. The independently validated total is 571,699 member-wave records across 15 waves.
`key_namespace` distinguishes legacy IDs from the new native-component keys.

The county/commune polygon joins expose reference dates. Complete village codes are not verified
historical village identities or village geometry. The reference boundary tables remain read-only;
the local village-directory feasibility results are not promoted to a spatial identity claim.

```sql
SELECT * FROM cses_analysis.cses_geography_coverage_v2 ORDER BY survey_wave;

SELECT p.survey_wave, p.record_key, p.sex, p.age_source_value,
       p.age_exact_years_qualified, p.age_qualification_status,
       g.admin1_code, g.admin2_code, g.admin3_code, g.admin4_code
FROM cses_data.cses_additional_hl_v1 AS p
JOIN cses_data.cses_additional_geo_v1 AS g USING (survey_wave, household_key);

SELECT survey_wave, module_code, target_field, cross_wave_equivalence, evidence
FROM cses_alignment.cses_additional_field_mapping_v1
ORDER BY survey_wave, module_code, target_field;
```

The existing survey/archive/dataset/source-variable catalogs receive additive registrations.
Source-variable option dictionaries follow the existing code-to-label JSON-object contract.
The 171 native-field correspondences live in `cses_alignment.cses_additional_field_mapping_v1`;
they are not promoted to universally certified canonical mappings. The 45 provenance documents in
`cses_meta.cses_additional_evidence_v1` retain inventories, mappings, source-missing ledgers, review
summaries and manifests. Questionnaire files/text remain in their existing processed cache.
Storage registrations and dataset-output edges include the HH roster-count input and alternate
2023 HEALTH input, rather than attributing those derived fields only to the primary table.

### Execution and safety

Publisher: `rsc/cses_db/publish_cses_additional_waves.py`. Evidence directory:
`data/releases/cses-additional-waves-qualified-v1/`. The operative plan is `execution-v2.json`;
the earlier plan is retained. The first rollback rehearsal exposed a locale-dependent path-order
checksum issue, not a payload difference. The revised validator uses explicit PostgreSQL C collation
for text-key ordering, matching deterministic local order. Dictionary representation was also
normalized before publication; the revised full rehearsal passed and was rolled back before
the separate publication transaction committed. Sequence gaps from rollback are expected.

The fresh four-schema backup is `data/backups/cses_additional_v1/before_additional_waves.dump`
(SHA-256 `ae56b223fad42b708a239f321efa96a0aa0659db3542cd6f52c9475a9dda45e6`). Full decompression
passed; this is not a separate-server restore test. Publication creates eleven physical relations
and three views, plus catalog/release/load records, in one transaction. It refuses existing targets,
locks and fingerprints all 20 pre-existing physical data/analysis tables, and protects both shared
boundary references. Every new table is compared with its source projection by row count and ordered
full-row digest before commit, followed by a separate read-only postflight.

Both postflight checks passed. The independent `mda_readonly` acceptance test verifies all
33 wave/module counts and 11 key/semantic checks: six age-98+ cases, 12 unresolved school responses,
the three EC folds with original rows retained, three provider conflicts, 29 unclassified writing
zeros, and no invented combined-literacy split or daily-to-weekly hours conversion. The 20 older
physical tables and both shared boundary references are unchanged. The full regression suite
passed 514 tests; Ruff and whitespace checks passed. Evidence files are `rehearsal-v2.json`,
`published.json`, `validated.json` and `analysis-checks.json` alongside the operative plan.

```bash
.venv/bin/python rsc/cses_db/publish_cses_additional_waves.py validate
.venv/bin/python rsc/cses_db/validate_cses_additional_analysis.py
```

Do not retry publication blindly after an uncertain connection outcome. Inspect the targets and
load registry first. Old graph exports and fixed-scope validators remain historical snapshots;
this release does not overwrite them. No Git/DVC commit or push is implied by database publication.

## Read-only alignment pilot

The user requested an experiment, not a database correction. The pilot inspected all 212,779
new-wave roster records through a repeatable-read, read-only transaction under `mda_readonly`.
It tested sex, age and current school attendance, their native-code transformations, exact
education joins, 6–17 and 10–14 age bands, and single ages 6 through 17. Database data, mappings
and views were **not changed**. Only local aggregate evidence and experiment code were added.

### Verdict

| Concept | Result | Boundary |
| --- | --- | --- |
| Sex | Passed the five-wave coding/completeness pilot | 212,779 valid 1/2 responses; no missing values, invalid codes or source/recode discrepancies; this does not validate survey weights or representativeness |
| Age | Five-wave published interface fails the completeness needed for age-specific analysis | Four waves have complete source ages; 2025 has only 165/51,775 non-null published ages; upper-age qualifications remain wave-specific |
| Current school attendance | Coding passes, but naive cross-wave rates fail the common-denominator test | Never-attended skips must be distinguished from unanswered items, with explicit eligibility and contradiction handling |

Female shares in the unweighted samples are 52.15%, 52.46%, 51.56%, 51.56% and 51.82%
for 1996, 1997, 1999, 2023 and 2025 respectively. These are descriptive checks, not national
estimates or proof of comparability from distribution similarity.

### 2025 age field-selection problem

**Later correction:** the [2025 age interface](cses-2025-age-interface.md) now exposes native
`age` for all 51,775 members with source hashes and first-visit diagnostic flags. Original
v1 fields and the local pilot below remain unchanged. Query the new interface explicitly;
formula/reference-date/top-code semantics are still unverified.

The published `age_source_value` uses `q01ac05a` and has 51,610 missing values (99.68%).
The original `S01A_HHmember.dta` also contains `age`, labeled **Calculated age**, which has
51,775 non-null integer values from 0 to 105. Its UUID/member keys match the published roster
exactly, and all 165 overlapping `q01ac05a` values agree. This is a source-field selection gap,
not evidence that 99.68% of respondents lack an age in the original data.

For a local sensitivity test only, the pilot joins that native `age` field without overwriting
the published field. It identifies 11,753 members aged 6–17, compared with only 40 using the
current published age. The native age-calculation formula, date dependence and full upper-age
interpretation are not independently certified by this test. A separately approved correction
should preserve both fields and identify the provenance of the analysis age.

### School denominator sensitivity: ages 6–17

**Later qualified interface:** [school attendance and denominators](cses-additional-school-attendance.md)
now separates source answers from documented skip-derived No, excludes unresolved route/code
conflicts from the qualified denominator, and uses the published 2025 age selection. The
1997 qualified 6–17 denominator is 10,023 with 29 unresolved records; its result therefore
differs from the historical sensitivity scenario below. Original answers and this pilot
remain unchanged.

All percentages below are **unweighted sample diagnostics**, not national attendance rates.
The 2025 row uses the local native-calculated-age join, which has not been published.

| Wave | Members aged 6–17 | Yes / non-null attendance responses | Sensitivity: never-attended skips counted as No | Other unresolved attendance cells |
| --- | ---: | ---: | ---: | ---: |
| 1996 | 16,408 | 63.41% | 63.41% | 0 |
| 1997 | 10,052 | 86.05% | 64.45% | 15 |
| 1999 | 10,881 | 88.08% | 66.54% | 1 |
| 2023 | 11,992 | 88.81% | 86.81% | 0 |
| 2025, local age candidate | 11,753 | 89.14% | 87.47% | 0 |

For 1999, the 2,661 missing attendance values within this age band include 2,660 records marked
never attended and one other unresolved answer. The cached form explicitly routes never-attenders
past the current-attendance item. Simply dropping all nulls changes the denominator substantially.
The 2025 cached form similarly directs No on ever-attended to column 11; the 1996 attendance label
also explicitly includes university/training/vocational institutions, so common age alone does
not certify identical schooling concepts.

The sensitivity formula is `yes / (yes + no + missing_current_and_ever_no)`; remaining unknowns
are not imputed. The report also includes arithmetic all-member bounds `yes / n` to
`(yes + missing) / n`, not confidence intervals. These bounds reflect missing answers only,
not sampling uncertainty or possible response error. No database value is changed by either scenario.

The 1997 data also contain **four** ever-attended=No/currently-attending=Yes contradictions,
including three among ages 6–17. These original answers remain visible; neither the pilot nor
the published database silently resolves them. The 1997 sensitivity figures retain the reported
current attendance, so they are not a final approved harmonized indicator.

Cached evidence locations: the 1999 `legacy_word_text_v1/1999/QuestENG_Form3Page.txt` schooling
section (around lines 552–583), the 2025 extracted questionnaire sheet cells R10/R16, AH10/AH17
and BJ10/BJ12, and the field-alignment ledger's native labels. Text/cell extraction is not a new
visual certification of the full questionnaire or a reconstruction of electronic-form logic.

### Reproduction and implications

```bash
.venv/bin/python rsc/cses_db/experiment_cses_alignment.py
```

Aggregate evidence: `data/processing/cses/alignment_pilot_v1/summary.json`. It records source/code
hashes, the read-only query, snapshot digest, per-wave checks, age-band denominators, per-age
diagnostics and limitations. Re-running against changed inputs must not overwrite this artifact.
Three unit tests verify missingness, sensitivity denominators and empty-band behavior.

The earlier count of 12 indicators with mappings in at least two waves identifies **candidates
for comparability review**, not 12 analysis-ready harmonized outcomes. This pilot does not validate
the other nine concepts. Next priorities are a versioned 2025 analysis-age correction and explicit
school-route/eligibility rules, including the 1997 contradictions, before publishing pooled rates.

## Source completeness and missingness audit

This follow-up is diagnostic only: it reads the supplied archives and immutable caches, audits
all 171 selected field-wave profiles, and checks selected native routing patterns. It does not
change database records, infer missing responses, or replace earlier release evidence.

### What is and is not missing

**Update 2026-10-16:** the full 2023 English household form is now
[archived locally](../data/processed/cses_questionnaires/additional_waves_v1/2023/README.md).
The supplied-archive audit below remains historical; its one-page-cover finding does not describe
the complete current collection. See the updated [missing-materials checklist](cses-questionnaire-organization.md#remaining-local-collection-gaps-english-summary-updated-2026-10-16).

All five archive SHA-256 fingerprints and full ZIP CRC checks passed. Their 173 Stata members
match the registered source inventory (13/25/46/42/47 by wave). All ten document members with
Word/PDF/Excel extensions are present in the processed questionnaire cache and match their hashes.
There is no detected loss or corruption relative to the supplied bundles. This does **not** establish
that the supplied bundles contain every file in the original official survey distribution.

| Wave | Supplied questionnaire/reference material | Evidence limitation |
| --- | --- | --- |
| 1996 | English `QuestENG_Form2.DOC` | A retained household form is not proof that every possible instrument was supplied |
| 1997 | Form 3 and Form 4 PDFs, 16 and 15 pages | Form 4 is a social-sector household module, not a village form inferred from its number |
| 1999 | Main form, separate cover, income/employment Form 4, editing manual | Four files, not four independent complete household questionnaires |
| 2023 | One-page English cover and 68-page Khmer form | The English questionnaire body is missing from the supplied bundle; Khmer content is present but not fully semantically verified |
| 2025 | English household XLSM, 64 cached sheets | Multiple/older sheet versions coexist; electronic-form enablement and calculated-field logic were not found in the supplied bundle |

The absence of a separately built village module or 1997/1999 timing module is a **pipeline coverage
gap**, not proof that all village/timing source information is absent. Area-information datasets
are retained in four archives, and geography components exist in the fifth year's roster. These
are not automatically village questionnaire responses or verified village geometries.

### Four different causes of apparent missingness

1. **Selected-field omission:** 2025 `q01ac05a` has 165 values while the native `age` field has
   all 51,775 values. All 165 overlaps agree. Of the 165 manual-age values, 158 have an unknown
   birth year and seven have a known birth year, consistent with a restricted fill-in path but
   not sufficient to reconstruct the electronic calculation rule. Missingness of the selected
   field is not missing age information in the source dataset.
2. **Eligibility/routing nulls:** all 12,364 members younger than 13 in 2025 have blank marital
   status; all 39,411 aged 13+ have answers. The cached form labels the marital-status block
   "Only for members aged 13 and above". In 1996, all 1,299 disability-screen positives have a
   disability type; all 45,512 screen negatives have a blank type. These observed patterns support
   structural rather than indiscriminate item-nonresponse interpretations.
3. **Unresolved or invalid answers:** the earlier school pilot retains 12 unresolved 1999
   current-attendance answers and four contradictory 1997 ever/current-school combinations.
   Across all selected binary recodes, 45 non-null source cells lack recognized dictionary codes,
   including 29 writing-code-0 values in 2025. They remain raw values plus null standardized outputs,
   not silently assigned No. Those counts describe distinct checks and must not be summed as a
   count of unique people with missing data.
4. **Unresolved source/form routing discrepancy:** the 2025 treatment-sought pattern below cannot
   be classified as ordinary nonresponse or a proven valid skip from the supplied evidence alone.

### New priority: 2025 treatment sought

| Native recent-health screen | Members | Treatment-sought answers (`q13bc06`) | First-provider answers | Healthcare-frequency answers |
| --- | ---: | ---: | ---: | ---: |
| Illness, code 1 | 14,695 | **0** | 14,324 | 14,695 |
| Injury, code 2 | 262 | **262** | 182 | 262 |
| Neither, code 3 | 36,818 | 0 | 0 | 0 |

The raw dataset itself has this pattern; it is not introduced by database loading. The cached
2025 health sheets contain question AD7 asking whether consultation/treatment was sought for
the illness/injury, and C18 routes injury to column 4 and No to column 7. Multiple sheet versions
and the absence of electronic routing definitions prevent treating the paper wording as proof
of the actual electronic field universe. The data nevertheless clearly rule out interpreting
all missing `q13bc06` values as no treatment: most illness cases have a provider recorded.

Do not pool this field with older treatment-sought indicators without a qualified reconstruction
and source/route review. Healthcare-frequency and provider fields are promising corroborating
evidence, not authorization to overwrite the missing source answers automatically.

The selected-field coverage scan also flags 2025 `s15q20` (availability last week): only 421
answers among 51,775 roster rows. All 40 job-search Yes records answer it; 381 of 17,596 job-search
No records answer it, and none of the 34,139 records without a job-search response do. This is a
conditional branch requiring its complete routing review, not evidence by itself that 99% of
respondents failed to answer a universally applicable question.

### Reproduction and scope limit

```bash
.venv/bin/python rsc/cses_db/audit_cses_source_gaps.py
```

`data/processing/cses/source_gap_audit_v1/summary.json` stores archive/cache checks and the focused
cross-tabs. `field_profiles.json` retains source rows, source-null counts, recoded non-null counts
and unrecognized-code counts for all 171 mappings. These profiles describe the preserved initial
candidate ledger, not a replacement of later duplicate/age/route qualifications. Source dataset
rows are not automatically eligible denominators.

This is not an exhaustive item-by-item missingness audit of all 5,427 native fields. The database
remains unchanged. Highest-priority follow-up is the 2025 analysis-age selection, then the
treatment-sought scope and school-route rules; questionnaire retrieval priorities include the
2023 English body and the 2025 electronic-form routing/calculation definition if available.

## Cross-wave follow-up: other years

**Materials-status correction:** the later [current materials audit](cses-questionnaire-organization.md#current-materials-audit-2026-10-03)
found additional loose 2007/2012/2013 forms and the 2014 published-report questionnaire appendices.
The questionnaire-absence statements below describe the earlier registered cache, not the complete
current filesystem. This correction does not retroactively certify variable mappings.

A read-only follow-up covers all 15 published rosters (571,699 member-wave records), selected
school indicators, and native health-screen/treatment/provider fields. It does not certify all
variables or change any database table. Reproduce with
`.venv/bin/python rsc/cses_db/audit_cses_cross_wave_gaps.py`; aggregate results, SQL, field selections,
script hash and cached questionnaire evidence are saved in
`data/processing/cses/cross_wave_gap_audit_v1/summary.json`.

| Check | Finding | Interpretation |
| --- | --- | --- |
| Age outside 2025 | Only one null, in 2004; its native age code is 99 (missing) | No second mass selected-age omission found; numeric completeness does not certify top-code comparability |
| 2009 treatment routing | Of 8,344 illness/injury positives, 1,031 answer treatment sought and 7,313 skip it | The cached questionnaire explicitly skips question 6 when question 4 says no activity restriction (5,896) or no usual activities (1,417); all observed blanks follow this route |
| School contradictions | Ever attended = No but currently attending = Yes: 1997: 4; 2014: 9; 2016: 7; 2021: 1 | Existing source-answer conflicts, not new loading losses; retain flags rather than silently choosing an answer |
| Health-source coverage | Roster members without a health row: 2007: 38; 2009: 23; 2014: 2; 2016: 3 | 66 record-level coverage gaps; not evidence of missing entire questionnaires |
| Health linkage | Health records outside the roster: 2014: 2; 2016: 3 | Five unmatched source records remain preserved and flagged |
| 2021 treatment sought | Ten nulls among 6,797 illness/injury positives: two illness and eight injury | Unresolved item/route gaps; two illness records have provider answers despite null treatment sought |
| 2023 treatment sought | Two of 141 injury positives have no treatment-sought answer; all 10,139 illness positives answer it | Small unresolved item/route gap, unlike the 2025 illness-wide blank pattern |
| 2021 illness type | 1,053 records have unresolved native codes 22–73 | Values exist, but their meanings are not sufficiently documented for harmonization |

The 2009 route is supported by cached sheet `Health Care Seeking _ Expen `: BD17 routes activity
codes 2/3 to question 7, bypassing treatment sought (question 6, BP7/BP25). Its treatment field is
therefore `q13bc06`, not a same-position field borrowed from another wave. A pooled treatment rate
must account for this restricted universe. Screening No plus a provider answer is not inherently
contradictory: the questionnaire also permits care for other reasons.

Questionnaire evidence still has important qualifications: 2007 has a village form but no located
household form; no 2017 form has been located; 2011–12 uses the distributed 2011 form without a
separately verified 2012 form; 2014 uses a draft; the 2019 image-based bundle exists but its relevant
wording/routing still needs transcription. Raw 2007 candidate fields and 2017 numerical patterns
are not promoted to questionnaire-certified concepts by this audit.

School blanks can also follow age eligibility or never-attended routing. Missing module rows,
structural skips, unknown codes, contradictory answers and missing questionnaire evidence are
different statuses; their counts must not be summed as unique respondents with missing data.
Priority remains the 2025 age selection and treatment scope, followed by explicit wave-specific
eligibility rules and the small unresolved record/answer anomalies above.
