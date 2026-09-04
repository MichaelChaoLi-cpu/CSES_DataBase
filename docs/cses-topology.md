# CSES Database and Lineage Topology

[Documentation index](README.md) · [Architecture](cses-database-architecture.md) · [Processing workflow](cses-processing-workflow.md)

## End-to-end control flow

The diagram separates versioned evidence, transactional state, and downstream read-only use. A solid
arrow changes the next layer; a dashed arrow is validation or projection.

```mermaid
flowchart LR
    subgraph dvc["DVC-owned evidence"]
        RAW["data/raw<br/>11 immutable CSES archives"]
        STAGE["data/processing<br/>staging and validation artifacts"]
        GRAPH["data/lineage<br/>deterministic graph snapshots"]
    end

    subgraph git["Git-owned logic"]
        CODE["rsc/cses_db<br/>inventory, build, load, graph"]
        SPEC["rsc/specs<br/>mapping and value rules"]
        TEST["rsc/tests<br/>contracts and regressions"]
        DOCS["docs<br/>architecture, operations, releases"]
    end

    subgraph postgres["mda PostgreSQL"]
        META["cses_meta<br/>survey, source, release, load"]
        ALIGN["cses_alignment<br/>source, canonical, mappings"]
        DATA["cses_data<br/>approved physical tables"]
        ANALYSIS["cses_analysis<br/>stable views and audits"]
        PUBLIC["public<br/>exact-name compatibility views"]
    end

    RESEARCH["Research repositories<br/>read-only SQL"]
    BACKUP["External verified backup"]

    RAW --> CODE
    SPEC --> CODE
    CODE --> STAGE
    TEST -.-> STAGE
    STAGE -->|"approved transaction"| META
    STAGE -->|"approved transaction"| ALIGN
    META --> DATA
    ALIGN --> DATA
    DATA --> ANALYSIS
    ANALYSIS --> PUBLIC
    ANALYSIS --> RESEARCH
    PUBLIC --> RESEARCH
    META -.-> GRAPH
    ALIGN -.-> GRAPH
    DATA -.-> GRAPH
    GRAPH -.-> DOCS
    BACKUP -.->|"recovery boundary"| postgres
```

## Relational lineage model

A solid arrow is a proposed enforced foreign key. A dashed arrow is a validated relationship that may
retain documented unmatched source records.

```mermaid
flowchart LR
    subgraph management["cses_meta"]
        SURVEY["cses_survey<br/>one wave"]
        ARCHIVE["cses_source_archive<br/>top-level ZIP + SHA-256"]
        DATASET["cses_dataset<br/>physical archive member"]
        RELEASE["cses_alignment_release<br/>approved mapping version"]
        RUN["cses_load_run<br/>fingerprints, status, counts"]
        STORAGE["cses_storage_table<br/>schema, relation, grain"]
        OUTPUT["cses_dataset_output<br/>source-to-output bridge"]
    end

    subgraph evidence["cses_alignment"]
        INSTRUMENT["cses_instrument"]
        QUESTION["cses_question"]
        SOURCE["cses_source_variable"]
        CANONICAL["cses_canonical_variable"]
        MAPPING["cses_variable_mapping"]
        VALUE["cses_value_mapping"]
    end

    subgraph physical["cses_data"]
        HH["final_HH_CSES<br/>household-wave"]
        HL["final_HL_CSES<br/>member-wave"]
        ED["final_ED_CSES<br/>education record"]
        HO["final_HO_CSES<br/>housing record"]
        EC["final_EC_CSES<br/>employment record"]
        VL["final_VL_CSES<br/>PSU-wave"]
        DATE["final_SURVEY_DATE_CSES<br/>household-wave"]
        GEO["dim_geo_CSES<br/>PSU-wave bridge"]
    end

    AUDIT["cses_analysis<br/>coverage and quality views"]

    SURVEY --> ARCHIVE
    ARCHIVE --> DATASET
    SURVEY --> RUN
    RELEASE --> RUN
    SURVEY --> INSTRUMENT
    INSTRUMENT --> QUESTION
    DATASET --> SOURCE
    RELEASE --> MAPPING
    SOURCE -.->|"reviewed source rule"| MAPPING
    MAPPING --> CANONICAL
    MAPPING --> VALUE
    DATASET --> OUTPUT
    STORAGE --> OUTPUT
    OUTPUT -.->|"recorded materialization"| HH
    OUTPUT -.-> HL
    OUTPUT -.-> ED
    OUTPUT -.-> HO
    OUTPUT -.-> EC
    OUTPUT -.-> VL
    OUTPUT -.-> DATE
    OUTPUT -.-> GEO

    HL -.->|"household link"| HH
    ED -.->|"person link; retained exceptions"| HL
    EC -.->|"person link; retained exceptions"| HL
    HO -.->|"household link; retained exceptions"| HH
    VL -.->|"PSU-wave aggregate link"| HH
    DATE -.->|"household timing"| HH
    GEO -.->|"PSU-wave geography"| HH

    RUN -.-> AUDIT
    MAPPING -.-> AUDIT
    OUTPUT -.-> AUDIT
```

## Implemented physical ownership and compatibility

```mermaid
flowchart LR
    DFINAL["cses_data.final_*_CSES<br/>7 physical tables"] -->|"SELECT projection"| PFINAL["public.final_*_CSES<br/>7 compatibility views"]
    DGEO["cses_data.dim_geo_CSES<br/>physical table"] -->|"SELECT projection"| PGEO["public.dim_geo_CSES<br/>compatibility view"]
    ADICT["cses_alignment.ind_que_*_CSES<br/>7 physical tables"] -->|"SELECT projection"| PDICT["public.ind_que_*_CSES<br/>7 compatibility views"]
    ASUM["cses_analysis.align_summary_*_CSES<br/>7 physical tables"] -->|"SELECT projection"| PSUM["public.align_summary_*_CSES<br/>7 compatibility views"]

    EXTERNAL["Climate, MICS/NLSS, generic geography,<br/>monitoring, and research relations"] -.->|"31 identities protected"| STAY["unchanged in public"]
```

This is the validated state after migration v1. Physical OIDs, rows, columns, indexes, constraints,
owners, and grants were preserved; `mda_readonly` can query both the functional schemas and compatibility
views.

## Deterministic database projection v1

The database-backed v1 snapshot is a forced read-only projection of the current authoritative state. It
contains 244 natural-key nodes and 516 sorted edges. Two consecutive exports were byte-identical.

```mermaid
flowchart LR
    SURVEY["10 survey waves"]
    ARCHIVE["11 source archives"]
    DATASET["171 physical datasets"]
    RELEASE["1 alignment release"]
    STORAGE["22 authoritative relations"]
    VIEW["22 public compatibility views"]
    RUN["1 load run"]
    ALIGN["0 source variables<br/>0 canonical variables"]
    GAP["15 relations without<br/>registered dataset edges"]

    SURVEY -->|"11"| ARCHIVE
    ARCHIVE -->|"171"| DATASET
    DATASET -->|"62"| STORAGE
    RELEASE -->|"7 targets"| STORAGE
    RELEASE --> RUN
    STORAGE -->|"22 verified projections"| VIEW
    DATASET -.-> ALIGN
    ALIGN -.-> STORAGE
    STORAGE -.-> GAP
```

The full JSON graph is `data/lineage/cses_lineage_graph_v1.json`; the generated aggregate Mermaid source
is `data/lineage/cses_lineage_overview_v1.mmd`. Both are DVC-owned and are reproducible with the
[lineage export runbook](cses-lineage-export-runbook.md).

Current direct source coverage is deliberately incomplete rather than inferred:

| Storage family | Registered relations | Relations with dataset-output edges | Visible gaps |
|---|---:|---:|---:|
| Final tables | 7 | 7 | 0 |
| Geography | 1 | 0 | 1 |
| Source dictionaries | 7 | 0 | 7 |
| Alignment summaries | 7 | 0 | 7 |

The geography edge and 14 inherited dictionary/summary edges require reviewed evidence. The normalized
instrument, question, source-variable, canonical-variable, and mapping tables are currently empty; the
graph will extend those paths automatically as later reviewed releases populate them.
