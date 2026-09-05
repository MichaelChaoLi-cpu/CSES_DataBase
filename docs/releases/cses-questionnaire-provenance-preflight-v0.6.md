# CSES Questionnaire Provenance Preflight v0.6

- Date: 2026-09-05
- Database: `mda`
- Planned release: `cses-questionnaire-provenance-v1`
- Reviewed implementation revision: `0aea2ec`
- Database mutation: none

## Outcome

The deterministic questionnaire-provenance planner completed in a forced read-only PostgreSQL
transaction. All local and database checks passed. The plan proposes 180 inserts and 291 updates with
zero conflicts:

- one approved alignment-release record;
- 14 fingerprinted questionnaire, diary, listing, village, or forms-bundle instruments;
- 164 normalized question transcriptions;
- 291 existing source-variable links;
- one immutable load-run record.

The existing functional schema already represents this topology, so no new schema or table migration
is proposed. The plan protects the seven final tables and compatibility views, 4,092 source-variable
identities, 280 canonical variables, 1,714 source-to-canonical mappings, and the empty canonical
value-mapping table.

## Evidence

| Evidence | SHA-256 |
|---|---|
| Reviewed plan | `0c07aca1a4a882cf97f584fb5a58fb8129e8a278a2f4545cfbab7935dc17e95c` |
| Question catalog | `2cab89dcbdaa4378d9bc4dc60607d13a34e9e2870faed4cb3bc50a2b7e2b7c65` |
| Source variable-catalog plan | `0d9563ff820073baa420b98e1c722b32cfdad77d2c27ce6df7fbdb307a4fa8c1` |

The resulting DVC data pointer is `md5:91e06b6a9b5a3820ba98ab5e430b07df.dir`, containing 74 files and
466,120,486 bytes. The new objects were pushed to the configured `storage` remote.

## Coverage and confidence boundary

Question text and deterministic links cover:

- housing: 2004, 2009, 2011-12, 2014, and 2016;
- village demographic section 1: 2007, 2009, and 2016.

All 51 links derived from the explicitly named 2014 draft remain `proposed`. The other 240 links are
`reviewed`, meaning the same-wave source variable has the longest unambiguous registered question-code
prefix. No text is marked exact, response options are not harmonized, and no canonical value mapping
is inferred.

The plan retains seven explicit gaps: no located 2007 household questionnaire, no located 2011-12
village questionnaire, no questionnaire files located for 2013, 2017, or 2021, only a draft household
questionnaire for 2014, and an image-only 66-page DOCX forms bundle for 2019. OCR output is not treated
as authoritative evidence.

## Write gate

No database write is authorized by this preflight. The importer requires a new explicit approval with
the exact phrase:

`ACCEPT-CSES-QUESTIONNAIRE-PROVENANCE-V1`

After import, a separate forced read-only validator must reconcile every planned record as a no-op
before import evidence is accepted.
