#!/usr/bin/env python3
"""Reproduce diagnostic evidence for unlabeled housing codes; never publish mappings."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import pandas as pd
from cses_housing import MONEY_SENTINELS, wave_aliases
from inventory_cses_archives import DataSource

TARGETS = ("2007", "2013", "2017")
FIELDS = {
    "dwelling_tenure_source_code": "Dwelling Tenure Source Code",
    "main_cooking_fuel_source_code": "Main Cooking Fuel Source Code",
    "main_lighting_source_code": "Main Lighting Source Code",
}
ENERGY = {
    name: f"Monthly {label} Expense Riel"
    for name, label in (
        ("electricity", "Electricity"), ("gas", "Gas"), ("kerosene", "Kerosene"),
        ("firewood", "Firewood"), ("charcoal", "Charcoal"), ("battery", "Battery"),
        ("other_energy", "Other Energy"),
    )
}
RENT = {"paid_rent": "Monthly Rent Paid Riel", "imputed_rent": "Monthly Imputed Rent Riel"}
PINS = {
    "data/processing/cses/final_HO_CSES.parquet":
        "e0dae1a43267250b22fd8e18070b4a9243cd8f451fd40511ac4f7666e4b4826d",
    "data/processing/cses/value_mapping_review_v1/review.json":
        "aec4d1184e3675ec30b69e79291c41c5838edebc9be45d42f3b0e1bc68fdd81f",
    "data/processing/cses/value_mapping_release_v1/plan.json":
        "2f6fdca4705af007cdc982c71044adeada9fc54b97a40620d2871d3cc9577209",
}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stats(series: pd.Series) -> dict:
    """Keep NULL distinct from a recorded zero; use observed-value denominators."""
    observed = series.dropna()
    positive = int(observed.gt(0).sum())
    return {
        "rows": len(series), "observed": len(observed), "missing": int(series.isna().sum()),
        "positive": positive, "zero": int(observed.eq(0).sum()),
        "positive_fraction_of_observed": positive / len(observed) if len(observed) else None,
    }


def profile(frame: pd.DataFrame, field: str, code: int) -> dict:
    group = frame.loc[frame[FIELDS[field]].eq(code).fillna(False)]
    features = RENT if field == "dwelling_tenure_source_code" else ENERGY
    return {
        "rows": len(group), "sparse_under_20": len(group) < 20,
        "expenses": {key: stats(group[column]) for key, column in features.items()},
    }


def align_raw(raw: pd.DataFrame, local: pd.DataFrame) -> pd.DataFrame:
    row_numbers = local["Source Row ID"].str.rsplit(":", n=1).str[-1].astype(int)
    if len(raw) != len(local) or sorted(row_numbers) != list(range(1, len(raw) + 1)):
        raise ValueError("Source row IDs must form an exact one-to-one raw-row permutation")
    return raw.iloc[row_numbers.to_numpy() - 1].reset_index(drop=True)


def replay_raw(root: Path, frame: pd.DataFrame, review: dict, wave: str) -> dict:
    profiles = [p for p in review["profiles"] if p["survey_wave"] == wave]
    p = profiles[0]
    chain = tuple(v for v in (p["member_path"], p["nested_member_path"]) if v)
    if len({(q["archive_relative_path"], q["member_path"], q["nested_member_path"])
            for q in profiles}) != 1:
        raise ValueError("Expected the three variables in one raw housing member")
    archive = root / p["archive_relative_path"]
    expected = next(r["evidence"]["archive_sha256"] for r in review["code_rows"]
                    if r["source_key"]["survey_wave"] == wave)
    if sha256(archive) != expected:
        raise ValueError("Raw archive digest changed")
    payload = DataSource(archive, chain).read_bytes()
    if any(hashlib.sha256(payload).hexdigest() != q["member_sha256"] for q in profiles):
        raise ValueError("Raw member digest changed")
    with pd.io.stata.StataReader(io.BytesIO(payload), convert_categoricals=False) as reader:
        labels = reader.variable_labels()
        label_sets = reader.value_labels()
        raw = reader.read()
    local = frame.loc[frame["Survey Wave"].eq(wave)].reset_index(drop=True)
    if not local["Source Archive"].eq(p["archive_relative_path"]).all():
        raise ValueError("Local source archive differs")
    if not local["Source Submodule"].eq("::".join(chain)).all():
        raise ValueError("Local source member differs")
    raw = align_raw(raw, local)
    lookup = {column.lower(): column for column in raw.columns}
    aliases = wave_aliases(wave)
    pairs = {FIELDS[q["canonical_name"]]: [q["source_variable"]] for q in profiles}
    pairs.update({column: aliases[column] for column in (ENERGY | RENT).values()})
    checks = []
    for column, candidates in pairs.items():
        source = next(lookup[name.lower()] for name in candidates if name.lower() in lookup)
        values = pd.to_numeric(raw[source], errors="coerce")
        if column in (ENERGY | RENT).values():
            values = values.mask(values.lt(0) | values.isin(MONEY_SENTINELS))
        pd.testing.assert_series_equal(values.astype("Float64"), local[column].astype("Float64"),
                                       check_names=False)
        checks.append({"local_column": column, "source_variable": source,
                       "source_variable_label": labels.get(source), "all_cells_equal": True})
    return {"survey_wave": wave, "rows": len(local), "archive": p["archive_relative_path"],
            "archive_sha256": expected, "member_chain": list(chain),
            "member_sha256": p["member_sha256"], "file_value_label_set_count": len(label_sets),
            "checks": checks}


def build(root: Path) -> dict:
    for path, expected in PINS.items():
        if sha256(root / path) != expected:
            raise ValueError(f"Pinned input changed: {path}")
    frame = pd.read_parquet(root / next(iter(PINS)))
    review = json.loads((root / "data/processing/cses/value_mapping_review_v1/review.json").read_text())
    plan = json.loads((root / "data/processing/cses/value_mapping_release_v1/plan.json").read_text())
    replays = [replay_raw(root, frame, review, wave) for wave in TARGETS]
    references = []
    for row in plan["approved_rows"]:
        wave, field, code = row["survey_wave"], row["canonical_name"], int(row["source_code"])
        if wave in TARGETS:
            raise ValueError("Target-wave semantic status unexpectedly changed")
        references.append({"survey_wave": wave, "field": field, "code": code,
                           "documented_category": row["approved_canonical_value"],
                           "review_row_id": row["review_row_id"],
                           **profile(frame.loc[frame["Survey Wave"].eq(wave)], field, code)})
    targets = []
    for wave in TARGETS:
        local = frame.loc[frame["Survey Wave"].eq(wave)]
        for field, column in FIELDS.items():
            p = next(p for p in review["profiles"] if p["survey_wave"] == wave
                     and p["canonical_name"] == field)
            expected = {int(r["source_code"]): r["count"]
                        for r in p["local_published_frequencies"] if r["code_kind"] == "numeric"}
            if local[column].dropna().astype(int).value_counts().to_dict() != expected:
                raise ValueError("Observed codes differ from frozen review")
            for code in sorted(expected):
                # A chronological same-number comparison is a hypothesis, not independent evidence.
                matches = [r for r in references if r["field"] == field and r["code"] == code]
                before = [r for r in matches if int(r["survey_wave"][:4]) < int(wave)]
                after = [r for r in matches if int(r["survey_wave"][:4]) > int(wave)]
                neighbors = ([max(before, key=lambda r: r["survey_wave"])] if before else [])
                neighbors += [min(after, key=lambda r: r["survey_wave"])] if after else []
                targets.append({"survey_wave": wave, "field": field, "code": code,
                                "semantic_status": "unconfirmed", "publication_ready": False,
                                "wave_field_null_rows": int(local[column].isna().sum()),
                                "same_number_neighbor_hypotheses": [
                                    {k: r[k] for k in ("survey_wave", "documented_category", "rows")}
                                    for r in neighbors], **profile(local, field, code)})
    if len(targets) != 50:
        raise ValueError("Expected exactly 50 observed wave/field/code combinations")
    cooking_lighting = []
    for wave in TARGETS:
        local = frame.loc[frame["Survey Wave"].eq(wave)]
        for (cooking, lighting), group in local.groupby(
            [FIELDS["main_cooking_fuel_source_code"], FIELDS["main_lighting_source_code"]],
            dropna=False,
        ):
            cooking_lighting.append({"survey_wave": wave,
                                     "cooking_code": None if pd.isna(cooking) else int(cooking),
                                     "lighting_code": None if pd.isna(lighting) else int(lighting),
                                     "rows": len(group),
                                     "kerosene": stats(group[ENERGY["kerosene"]])})
    rent_exceptions = frame.loc[
        frame["Survey Wave"].isin(TARGETS)
        & frame[FIELDS["dwelling_tenure_source_code"]].eq(3)
        & frame[RENT["paid_rent"]].isna()
        & frame[RENT["imputed_rent"]].gt(0), "Source Row ID"
    ].sort_values().tolist()
    code_paths = [Path(__file__).resolve(), root / "rsc/cses_db/cses_housing.py",
                  root / "rsc/cses_db/cses_hh_hl_common.py",
                  root / "rsc/cses_db/inventory_cses_archives.py"]
    # Recheck after reading; no time stamp so repeated runs are byte-identical.
    for path, expected in PINS.items():
        if sha256(root / path) != expected:
            raise ValueError(f"Input mutated during analysis: {path}")
    return {
        "report_id": "cses-housing-reverse-evidence-v1", "database_connected": False,
        "database_mutated": False, "mappings_changed": False, "publication_ready": False,
        "input_sha256": PINS, "code_sha256": {str(p.relative_to(root)): sha256(p) for p in code_paths},
        "method": {
            "unit": "unweighted housing records; not population estimates",
            "rate": "positive / non-null; NULL is never converted to zero",
            "sparse_threshold": "n < 20 is a descriptive warning, not a significance test",
            "feature_semantics": "Inherited wave-aware builder aliases; raw target labels are absent. "
                "Raw replay verifies values and linkage, not the meanings of the aliases.",
            "excluded": ["Dwelling Tenure Harmonized", "code-number-based automatic assignment"],
            "limitations": ["Households can use multiple fuels.", "No spending does not imply no use.",
                            "Electricity expense cannot distinguish grid from generator.",
                            "Other-energy expense cannot distinguish candle, solar, none, and other.",
                            "Same-number neighbors can change meaning across waves."],
        },
        "raw_replay": replays, "target_profiles": targets, "reference_profiles": references,
        "cooking_lighting_joint_profiles": cooking_lighting,
        "tenure_code_3_missing_paid_positive_imputed_source_rows": rent_exceptions,
    }


def render(report: dict) -> str:
    lines = ["# Housing reverse evidence v1", "", "Diagnostic only: all 50 target meanings remain "
             "unconfirmed; no database or mapping changes.", "", "Entries are **positive / non-null** "
             "expense counts, not population estimates. Missing is not zero. Neighbor labels are "
             "same-number hypotheses only. `*` marks n < 20.", ""]
    for section, records in (("Target waves", report["target_profiles"]),
                             ("Documented reference waves", report["reference_profiles"])):
        lines += [f"## {section}", ""]
        for field in FIELDS:
            features = RENT if field == "dwelling_tenure_source_code" else ENERGY
            lines += [f"### {field}", "", "| Wave | Code | n | " + " | ".join(features) +
                      " | Documented category / unconfirmed neighbors |",
                      "|" + " --- |" * (len(features) + 4)]
            for r in records:
                if r["field"] != field:
                    continue
                cells = [f"{r['expenses'][f]['positive']}/{r['expenses'][f]['observed']}" for f in features]
                label = r.get("documented_category") or "; ".join(
                    f"{n['survey_wave']}: {n['documented_category']}"
                    for n in r["same_number_neighbor_hypotheses"])
                lines.append(f"| {r['survey_wave']} | {r['code']} | {r['rows']}"
                             f"{'*' if r['sparse_under_20'] else ''} | " + " | ".join(cells) + f" | {label} |")
            lines.append("")
    return "\n".join(lines)


def write_outputs(directory: Path, report: dict) -> None:
    outputs = {"evidence.json": json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True,
                                          allow_nan=False) + "\n", "evidence.md": render(report)}
    for name, payload in outputs.items():
        path = directory / name
        if path.exists() and path.read_text() != payload:
            raise ValueError(f"Refusing to overwrite different evidence: {path}")
    directory.mkdir(parents=True, exist_ok=True)
    for name, payload in outputs.items():
        path = directory / name
        if not path.exists():
            path.write_text(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    report = build(root)
    output = args.output_dir or root / "data/processing/cses/housing_reverse_evidence_v1"
    write_outputs(output, report)
    print(json.dumps({"target_profiles": len(report["target_profiles"]),
                      "raw_rows_replayed": sum(r["rows"] for r in report["raw_replay"]),
                      "database_mutated": False, "output": str(output)}))


if __name__ == "__main__":
    main()
