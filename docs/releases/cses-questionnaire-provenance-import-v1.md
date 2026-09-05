# CSES Questionnaire Provenance Import v1

- Date: 2026-09-05
- Database: `mda`
- Release: `cses-questionnaire-provenance-v1`
- Approval: exact phrase `ACCEPT-CSES-QUESTIONNAIRE-PROVENANCE-V1` received

## Outcome

The reviewed questionnaire-provenance plan was applied in one PostgreSQL transaction. The importer
inserted exactly one approved alignment release, 14 instruments, 164 questions, and one load-run
record. It updated exactly 291 previously unlinked source-variable records with deterministic question
links. In-transaction reconciliation then observed all 471 reviewed records as no-ops, with zero
pending inserts, updates, or conflicts.

The independent validator opened a new forced read-only transaction and passed every check. It again
observed 471 no-ops. The seven physical final tables, compatibility views, 4,092 source-variable
identities, 280 canonical variables, 1,714 variable mappings, and empty canonical value-mapping table
were unchanged.

## Versioned evidence

| Evidence | SHA-256 |
|---|---|
| Reviewed plan | `0c07aca1a4a882cf97f584fb5a58fb8129e8a278a2f4545cfbab7935dc17e95c` |
| Import evidence | `a657bb67a8eea0411de195b1592861c8fbfca8792c701a246d56389fd22b838f` |
| Validation evidence | `e9207e1375d7541fffc8ab686b504a60af11a5906d03768a44dccc85c586790c` |
| Post-import graph v4 | `0a94f3ad72435223c475d36a95f9296a712bc7394d0b9949d3ca6f783ee54fda` |
| Post-import overview v4 | `f9cfaa3c8de035e16dd750f26f5281217123254bdf9e18ca9a3324c9493cb51d` |

The final DVC data pointer is `md5:d427da93fcdec9b304ec73362803c420.dir` with 78 files and
472,038,645 bytes. The reviewed implementation revision is
`0aea2ec05e75f472dcf3513b69d5e71b9ea2ac5f`; the preflight pointer and review record were committed at
`cc6dd67`.

Graph v4 was exported twice from the same authoritative database state. Both the 5,761,370-byte JSON
graph and the 695-byte Mermaid overview were byte-identical across exports.

## Resulting questionnaire topology

- registered instruments: 14 across seven survey waves;
- registered questions: 164;
- question-to-source-variable links: 291;
- reviewed links: 240;
- proposed links from the explicitly named 2014 draft: 51;
- exact-question-text claims: 0;
- source variables: 4,092;
- canonical variables: 280;
- source-variable-to-canonical graph edges: 1,770;
- canonical value mappings: 0;
- alignment releases and load runs: 4 each;
- graph v4: 4,800 nodes and 7,489 edges.

The graph now exposes the full managed path
`survey → instrument → question → source variable → canonical variable → storage table` where reviewed
evidence exists.

## Confidence and gap boundary

Question text is a whitespace-normalized spreadsheet-cell transcription and remains explicitly not
exact. Same-wave native variable-code matching produced the links; question semantics alone never
created a link. All 2014 links remain proposed because the only located household questionnaire is a
draft with comments.

Seven documented gaps remain: the 2007 household questionnaire, the 2011-12 village questionnaire,
questionnaires for 2013, 2017, and 2021, a final 2014 household questionnaire, and machine-readable
2019 question text. The 2019 image-only forms bundle is registered as discovered, but OCR is not
treated as authoritative. Response-option and canonical value harmonization require separate reviewed
releases.
