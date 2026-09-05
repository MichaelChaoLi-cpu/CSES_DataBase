# Housing codes: reverse evidence for 2007, 2013 and 2017

This preserves the earlier diagnostic findings, not current semantic approval state. Subsequent
inspection found independent 2007 code tables and a nested 2013 household questionnaire. The user
also approved direct 2016-to-2017 dictionary transfer; see [the 2017 alignment](cses-housing-2017-alignment.md).
The [recovered-evidence release](cses-housing-recovered-evidence.md) now publishes the 2007/2013
definitions from those primary sources. The unconfirmed status below describes the diagnostic's
historical result, not the current 50 observed combinations.
The frozen diagnostic JSON and Markdown remain unchanged as evidence of that earlier analysis.

## Result and status

The data support several interpretations, but do not establish an official codebook.
All **50 observed wave/field/code combinations remain unconfirmed**. This diagnostic does not
connect to PostgreSQL, publish mappings, alter the housing interface, or modify source data.

The check replayed **11,273 housing records** (3,593 in 2007; 3,840 each in 2013 and 2017),
comparing all cells of the three source-code fields and nine expense fields with their raw Stata
members. Values match after the existing negative/sentinel-to-NULL expense cleaning. Source-row
IDs, archive/member identities, and hashes are checked, not just aggregate distributions.

Crucially, the raw target files contain **no value-label sets**, and all 12 inspected variable
labels per wave are blank. Expense meanings therefore depend on the existing wave-aware builder
aliases. Raw replay verifies extraction, not those semantic assumptions. The derived
`Dwelling Tenure Harmonized` column is explicitly excluded as circular evidence.

## Stronger behavioral support

Counts below are positive expense / non-null expense, except the tenure row, whose denominator
is all records with tenure code 3. They are unweighted sample counts, not population estimates.

| Field and candidate interpretation | 2007 | 2013 | 2017 |
| --- | --- | --- | --- |
| Tenure 3: rented; records with positive paid rent | 118/122 | 167/167 | 118/118 |
| Cooking 2: charcoal; positive charcoal expense | 441/462 (95.5%) | 408/410 (99.5%) | 286/296 (96.6%) |
| Cooking 3: gas, consistent with LPG; positive gas expense | 577/583 (99.0%) | 902/907 (99.4%) | 1,348/1,355 (99.5%) |
| Lighting 3: battery; positive battery expense | 1,145/1,161 (98.6%) | 1,034/1,045 (98.9%) | 364/375 (97.1%) |
| Lighting 4: kerosene lamp; positive kerosene expense | 1,067/1,075 (99.3%) | 371/393 (94.4%) | 36/41 (87.8%) |

These patterns are consistent with documented reference-wave categories. They support hypotheses,
not exact questionnaire wording. Gas expense alone does not prove LPG chemistry; households may
use several fuels. Lighting code 1 also strongly supports electricity use (99.1%, 99.5%, 99.4%
positive electricity expense), but expense data cannot establish grid versus generator supply.

Cooking code 1 strongly supports firewood in 2013 (2,458/2,469; 99.6%) and 2017
(2,061/2,128; 96.9%). **2007 is different:** only 600/2,520 (23.8%) report positive firewood
expense, versus 94.1%–99.5% in the documented reference waves. Free collection, survey valuation
differences, or a source-field interpretation problem are possible explanations, not established
facts. Keep this case open.

The 2007 cooking-code-1 group has 1,756/2,520 positive kerosene expenses, but this is not evidence
that code 1 means kerosene cooking: 1,041 of these households have lighting code 4, and 1,035 of
those record kerosene expense. The cooking/lighting joint profiles preserve this confounding.

## What remains ambiguous

- Tenure codes 1 and 2 both predominantly follow the imputed-rent route. This cannot independently
  distinguish ownership from rent-free occupancy. Their same-number reference labels are owned
  and rent-free, respectively; these remain hypotheses.
- Four 2007 tenure-code-3 rows have missing paid rent and positive imputed rent. Their source-row
  IDs are preserved in the JSON evidence. They are routing exceptions to investigate, not errors
  automatically corrected by this diagnostic. The other 118 rows have positive paid rent.
- Cooking code 5 has positive electricity expense in all 18/42/53 records respectively, but also
  positive gas expense in 13/30/43. This does not uniquely identify the main cooking fuel.
- Cooking code 4 has one observation in each of 2007 and 2013; the 2013 observation has zero
  kerosene expense. Cooking code 7 also has one observation in each year. Code 8 has only
  3/10/8 records. These cannot be reliably named from spending alone.
- Lighting 2 has 41/12/6 records and cannot be distinguished as generator power using electricity
  expenses alone. Lighting 5, 6, 7 and 8 lack specific expense measures for candle, no lighting,
  solar and residual sources. Solar is plausible for 2013/2017 code 7, but not independently
  confirmed. In particular, 2009 lighting code 7 means other while 2011-12/2014 code 7 means solar.
- Codes can change across waves: 2004 cooking code 3 means firewood-and-charcoal (35/334 gas
  expenses), while 2009 code 3 is LPG (1,186/1,197 gas expenses). The 2007 pattern supports the
  latter much more strongly. This is an empirical distinction, not a copied same-number label.

NULL is not zero. Neither a missing expense nor a recorded zero proves non-use; consumption may
be free, collected, or outside the expense window. The n < 20 flag in the detailed report is a
descriptive caution, not a significance test. No automatic classifier or calibrated confidence
probability is claimed.

## Reproduction and evidence

```bash
.venv/bin/python rsc/cses_db/profile_cses_housing_reverse_evidence.py --root .
.venv/bin/python -m pytest rsc/tests/test_cses_housing_reverse_evidence.py -q
```

- [All 50 target profiles and 140 documented reference profiles](../data/processing/cses/housing_reverse_evidence_v1/evidence.md)
- [Machine-readable counts, nulls, raw checks, joint profiles and SHA-256 provenance](../data/processing/cses/housing_reverse_evidence_v1/evidence.json)
- [Reproducible diagnostic](../rsc/cses_db/profile_cses_housing_reverse_evidence.py)

The script pins the housing Parquet, frozen review and approved plan. It records code and raw
source hashes, reproduces deterministically, and refuses to overwrite different evidence.

Recommended next decision: if provisional labels are useful for research, define a separate,
explicitly reviewed **inferred** layer with evidence and uncertainty. Do not merge these hypotheses
into the existing approved dictionary. Exact labels still require source documentation or other
independent semantic evidence.
