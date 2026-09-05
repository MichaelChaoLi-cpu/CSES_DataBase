# CSES 2021 housing code diagnosis

Date: 2026-09-06. Read-only diagnosis of lighting code 8 and dwelling tenure code 0.
No database records, mapping specifications, source archives or published artifacts were changed.

## Findings

| Issue | Primary evidence | Diagnosis | Proposed treatment, not applied |
| --- | --- | --- | --- |
| `q04_07 = 8`, six observations | Khmer questionnaire and embedded Stata label both say `ជីវឧស្ម័ន`; the Khmer questionnaire assigns Other to 9 | Biogas meaning supported; English questionnaire conflicts with the released data | Add a separately reviewed `biogas` definition, preserving both language sources and their conflict |
| `q04_28 = 0`, one observation | Both questionnaires and embedded Stata labels define only 1–4 | Undocumented out-of-range source value; intended response and cause remain unknown | Retain the current analytical NULL and explicit source-invalid-code provenance; do not infer a tenure category |

## Sources and exact locators

All local sources are original members of `data/raw/Data of CSES2021.zip`:

| Member | SHA-256 |
| --- | --- |
| `Data of CSES2021/CSES2021 HH Quest ENG.xlsm` | `b95c135e6d42357d0b3da8e7faf073bd2494b61562c9f6126b2cc6b73635c804` |
| `Data of CSES2021/CSES2021 HH Quest KHM.xlsm` | `162c3c5217dcd454fa509b695f7eca7ba476a42682ab002fadf9a59814bfcfda` |

The archive hash is `99d631255933d8f13eef19ce15de5075f2db21d862745496d86edbae9c1face2`.
Both workbooks were read directly in memory with bundled Python/openpyxl in read-only mode;
macros were not executed and no workbook was converted or exported.
The raw data member is `Data of CSES2021/S04_HHhousing.dta` (10,080 rows).

Both workbooks use sheet `04 Housing_Revised-1`:

| Evidence | English workbook | Khmer workbook |
| --- | --- | --- |
| Lighting question | `A29`, `B29` | `B27`, `C27` |
| Lighting options | `C31`, `N31`, `U31`, `AC31`: codes 1–8; `AC31` says 7 Solar, 8 Other | `D29:D30`, `M29:M30`, `T29:T30`, `AA28:AA30`: codes 1–9; `AA29` says 8 `ជីវឧស្ម័ន`, `AA30` says 9 Other |
| Tenure question | `A155`, `B155` | `B151`, `D151` |
| Tenure options | `D157`: 1 Owned, 2 Rent free, 3 Rented, 4 Other | `E153:E156`: the same four numbered options; no 0 |

Cambodia's Ministry of Environment bilingual glossary independently identifies
`ជីវឧស្ម័ន` as **Biogas**: [Lexicon of Climate Change, March 2017](https://www.moe.gov.kh/wp-content/uploads/2017/05/Lexicon-of-Climate-Change_Mar-2017-FINAL.pdf),
PDF pages 58 and 144 (one-based). This verifies the translation, not the survey code assignment;
the latter comes from the original Khmer questionnaire and released Stata labels.

## Lighting: source-document conflict, not a lost numeric value

The raw `q04_07` value-label set contains nine codes. Code 8 has the same Khmer text as the Khmer
questionnaire; code 9 is explicitly labeled `Other (specify)`. Raw counts are six for code 8 and
38 for code 9. The local published lighting field was compared against all 10,080 raw rows using
one-based source-row identities and matches exactly.

Live read-only SQL confirmed that v3 retains all six code-8 values as `unmapped_nonnull`, with no
category. All 38 code-9 observations already match `other`. Therefore no numeric correction or
change to the existing code-9 definition is warranted by these findings.

The English questionnaire has only eight lighting options and assigns Other to 8. It must not be
used to overwrite the data-compatible Khmer coding. A version mismatch or editing omission is a
possible explanation, not a proven cause; no evidence here establishes which document was issued
later. Any new mapping should explicitly retain this conflict and explain the evidence preference.

The earlier frozen questionnaire specification incorrectly reported no 2021 questionnaire found.
It omitted these two `.xlsm` sources. That discovery statement is not reliable evidence of absence.
This diagnosis supersedes that statement without changing the historical specification or imports.

## Tenure: preserved raw anomaly and existing cleaning rule

The raw tenure frequencies are: 1 = 9,270; 2 = 408; 3 = 388; 4 = 10; 0 = 1; system missing = 3.
The out-of-range response is source row `2021:S04_HHhousing.dta:6458`.

`rsc/cses_db/cses_housing.py` supplies `{1, 2, 3, 4}` to `clean_source_code` for tenure
(lines 618–622). That function uses membership testing and converts out-of-range numeric values
to NULL (lines 414–437), recording `unresolved_code_set_null` in the existing issues artifact.
The issue file has exactly one affected 2021 tenure row. This was inherited processing, not a
change introduced by the 2007/2013 recovery.

The target row's local and live database tenure source-code and harmonized fields are NULL;
the v3 category is NULL with `source_null`. Thus the four published 2021 tenure NULLs consist of
three raw system-missing values and one undocumented raw 0. `source_null` is a match status, not
an assertion that all four raw missingness reasons are the same.

The raw zero-code record reports no paid rent and positive estimated rent. That pattern cannot
distinguish ownership from rent-free occupancy or other arrangements, and is not authority for
replacing 0 with 1 or 2. No inspected questionnaire defines 0 as refusal, don't know, non-response,
or a substantive category. Its intended answer remains unrecoverable from this evidence.

## Next authorized-change boundary

A future separately approved release can register both questionnaires and their lighting/tenure
evidence, add the six-observation biogas mapping with a documented language-source conflict, and
retain the tenure anomaly as an explicit quality exception without changing its data value.
No such release was applied in this diagnosis. Earlier v3 results and historical evidence remain intact.
