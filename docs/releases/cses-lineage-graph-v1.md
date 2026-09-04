# CSES Lineage Graph v1

Date: 2026-09-05

## Outcome

The first deterministic CSES lineage snapshot was exported from `mda` through a forced read-only
PostgreSQL transaction. No database relation was mutated. Two consecutive formal exports produced
byte-identical JSON and Mermaid files.

The full graph contains 244 nodes and 516 edges:

| Node type | Count |
|---|---:|
| Database | 1 |
| Schemas, including `public` | 5 |
| Surveys | 10 |
| Source archives | 11 |
| Physical datasets | 171 |
| Alignment releases | 1 |
| Load runs | 1 |
| Storage relations | 22 |
| Compatibility views | 22 |

The 516 edges include 171 archive-to-dataset links, 171 survey-to-dataset links, 62
dataset-to-storage materializations, 22 physical-to-compatibility projections, and their schema,
release, survey, and load-run control edges.

## Validation

All exporter gates passed:

- the database identity was `mda` and `transaction_read_only=on`;
- all four functional schemas and `public` were present;
- all 22 registered storage relations had same-name `public` compatibility views;
- PostgreSQL dependency metadata verified every compatibility view's physical target;
- natural-key node IDs, canonical edge sorting, dangling-edge rejection, and atomic replacement were
  covered by tests;
- 16 repository tests and Ruff passed.

## Cross-recorded identities

| Identity | Value |
|---|---|
| Exporter code Git revision | `3e815137c9ad886666f6ed160cf77d397df0c661` |
| Baseline metadata release Git revision | `47f28f0e83d016586002d225d99847347a37bf46` |
| Baseline metadata validation SHA-256 | `77a4632976a9b3c12fbbf8daa4fa0a8d826624ffaa118c3f2bff622992a8662b` |
| Graph SHA-256 | `30601a0c051bae843921442bcfbad401662b7cdee94aaa8b525a364c54d0c71e` |
| Mermaid overview SHA-256 | `a330479a092bf27d8e286867f39f31348b82665b3018d823a87605d56e8486d8` |
| Graph DVC pointer | `md5:d453ebafc501a3a33b6f2a95368760f4.dir` |
| Graph DVC-pointer Git revision | `5ee407cfc0599ac348975177872eb963189aae9a` |

The DVC remote `storage` was synchronized before the graph pointer was committed.

## Visible work queue

All seven final-table storage relations have direct dataset-output evidence. Fifteen relations do not:
`dim_geo_CSES`, seven inherited `ind_que_*_CSES` dictionaries, and seven inherited
`align_summary_*_CSES` tables. The graph reports these as visible gaps and does not infer their sources.

The normalized instrument, question, source-variable, canonical-variable, variable-mapping, and
value-mapping records are also currently empty. The next standardized processing phase is to fill the
15 storage edges with reviewed evidence, then populate variable-level lineage through a new alignment
release rather than modifying the baseline history.
