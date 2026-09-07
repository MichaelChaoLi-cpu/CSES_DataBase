# CSES reviewed questionnaire batch: publication plan

Status: the bounded plan and forced read-only PostgreSQL preflight are complete. This batch has
not been published. The published catalog still has 171 questions and 296 source-variable links.
The [variable brief](cses-variable-brief.md) describes that same pre-batch state.

## Scope and intended changes

The plan uses only the accepted [questionnaire review](cses-questionnaire-review.md). It proposes
15 new question records and 15 links on previously unlinked source variables: nine substantive
questions and six sex questions. Source-variable identities and semantic alignment statuses remain
unchanged. One separate identifier-provenance view would retain seven source identifiers and their
32 original header occurrences. Identifiers are not interview questions.

| Catalog object | Current | Planned after publication |
| --- | ---: | ---: |
| Questions | 171 | 186 |
| Source variables with question links | 296 | 311 |
| Alignment releases | 9 | 10 |
| Load runs | 9 | 10 |
| New identifier-provenance view | Absent | 7 rows / 32 header occurrences |

No new schema, instrument, physical-data update or constraint change is proposed. The existing
housing and age interfaces remain unchanged. These are evidence-registration changes, not 22
new fully comparable analytical variables or 22 additional physical-table columns.

## Exact question-link scope

IDs below identify existing source variables, not future question IDs. Question text is copied
from the accepted source-cell review; the JSON plan preserves literal spelling and whitespace.

| Source variable ID | Wave | Variable | Reviewed question |
| --- | --- | --- | --- |
| 14 | 2004 | q01a03 | Sex |
| 100 | 2004 | q02_11 | Has ..[NAME].. ever attended non-formal class? |
| 101 | 2004 | q02_12 | Is ..[NAME].. currently attending non-formal classes? |
| 206 | 2004 | q04a09 | Do you have a paper to certify your owner-ship or rental agreement? |
| 207 | 2004 | q04a10 | What kind of paper do you have? |
| 313 | 2004 | q13a10 | How many hours does ..[NAME].. want to work per week? |
| 316 | 2004 | q13a12 | How many occupations did.. [NAME].. have in the past 7 days? |
| 412 | 2004 | q05_01 | Does the household have outstanding loans or debts to other households or institutions? |
| 415 | 2004 | q08_01 | Does the household own buildings used for residential, agricultural, commercial or industrial purposes? |
| 890 | 2009 | q01ac03 | Sex |
| 1118 | 2011-12 | q01ac03 | Sex |
| 1857 | 2013 | Q04_01 | How many households reside in the same housing unit as your household? |
| 1947 | 2013 | Q01AC03 | Sex |
| 2298 | 2016 | q01ac03 | Sex |
| 3649 | 2021 | q01ac03 | Sex |

The six sex questions retain checked 1=Male / 2=Female options and source-cell locators.
For the other nine, option dictionaries and skip instructions stay NULL in this batch: reviewed
question correspondence is not approval of every response choice, universe or routing condition.
NULL here means not registered by this batch, not that the questionnaire has no choices or skips.

## Identifier provenance, not question links

Proposed view: `cses_analysis.cses_source_identifier_provenance_v1`.
It would expose source identity, source-file hash, original header locations and retained
qualifications, joined to the live source-variable catalog. It contains no respondent records.

| Source variable ID | Wave | Variable | Header occurrences | Source status |
| --- | --- | --- | ---: | --- |
| 199 | 2004 | q04a03 | 2 | verified |
| 854 | 2009 | q05ac01 | 5 | verified |
| 1186 | 2011-12 | q05ac01 | 5 | verified |
| 1611 | 2014 | q05ac01 | 5 | provisional / draft |
| 1908 | 2013 | Q05AC01 | 5 | documented |
| 2259 | 2016 | q05ac01 | 5 | verified |
| 3896 | 2021 | q05ac01 | 5 | documented |

The 2014 row remains provisional. Its inclusion as provenance does not promote the draft or
authorize a question link. Existing source-variable role constraints are left intact.

## Completed checks and reproducibility

The planner checks the frozen review and its source hashes, exact source-variable identities,
unchanged link state, matching registered instrument hashes, absent question identities and absent
target view. It evaluates the proposed SELECT in a repeatable-read/read-only transaction and
checks all seven identifier rows and the current catalog baseline. It performs no database writes.

```bash
.venv/bin/python rsc/cses_db/plan_cses_questionnaire_batch.py --check-database
.venv/bin/python rsc/cses_db/build_cses_variable_brief.py
```

The [machine-readable plan](../data/processing/cses/questionnaire_batch_v1/plan.json) contains
the proposed rows, executable SELECT, before-state expectations, code/review hashes and successful
preflight result. The report stores aggregate counts only. Both generators refuse to overwrite a
different existing artifact; use a fresh output directory for a changed snapshot.

## Publication boundary and following work

Publication requires approval of this named, exact scope, an immutable versioned execution plan,
a verified recoverable backup and a transactional publisher with rollback testing. Independent
validation must prove the 15 additions, 15 link updates and seven provenance rows, while preserving
all other metadata and physical rows. The next lineage projection must preserve graph v11 and add
the new question/source/view relationships. No publisher has been run for this batch.

After that bounded release, continue ED/EC variable-by-variable review of choices, units, eligible
members, skip logic and reference periods. Do not promote the remaining 1,112 unreviewed candidate
links from text matching alone. Keep the 2007/2017 household-form gaps, 2019 transcription work,
2014 draft status and 2004 age top-code qualifications visible.
