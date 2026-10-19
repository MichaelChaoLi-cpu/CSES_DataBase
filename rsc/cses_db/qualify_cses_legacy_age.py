#!/usr/bin/env python3
"""Add age bounds and audit 1999 module universes without changing v1 tables."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from build_cses_additional_waves import OUTPUT as CANDIDATES
from build_cses_additional_waves import encoded, parquet_bytes, verify
from cache_cses_questionnaires import file_sha, put

OUTPUT = "data/processing/cses/additional_age_review_v1"
CACHE = "data/processed/cses_questionnaires/additional_waves_v1"
EVIDENCE = {
    "1996": {"file": "QuestENG_Form2", "line": 370, "printed_page": "3 of 21", "column": 8,
             "quote": '(Enter "98" if age is 98 & over)',
             "sha256": "cc663279a2e9670fd229c7573c090ef1515f8784bdd845f40c68e3a8fbd5c000"},
    "1999": {"file": "QuestENG_Form3Page", "line": 41, "printed_page": "2 of 15", "column": 9,
             "quote": "(Enter 98 if age is 98 or over)",
             "sha256": "44ba56d0bac78b02e0f11d59e1b79d612e97025d1ac6cccacf8bdb7afafa8abc"},
}


def qualify_age(values):
    numeric = pd.to_numeric(values, errors="coerce")
    valid = numeric.between(0, 98) & numeric.mod(1).eq(0)
    topcoded = valid & numeric.eq(98)
    result = pd.DataFrame(index=values.index)
    result["Age Exact Years Qualified"] = numeric.where(valid & ~topcoded).astype("Int64")
    result["Age Lower Bound Years Qualified"] = numeric.where(valid).astype("Int64")
    result["Age Topcoded Qualified"] = topcoded.astype("boolean").where(valid)
    result["Age Qualification Status"] = "invalid_source_age"
    result.loc[values.isna(), "Age Qualification Status"] = "missing_source_age"
    result.loc[valid, "Age Qualification Status"] = "exact_completed_years"
    result.loc[topcoded, "Age Qualification Status"] = "98_or_older"
    return result


def scope_audit(roster, module):
    if roster["Record Key"].isna().any() or roster["Record Key"].duplicated().any():
        raise ValueError("Roster keys must be complete and unique")
    if module["Record Key"].isna().any() or module["Record Key"].duplicated().any():
        raise ValueError("Module keys must be complete and unique")
    age = roster.set_index("Record Key")["Age Source Value"]
    eligible = age.between(5, 98) & age.mod(1).eq(0)
    under = age.between(0, 4) & age.mod(1).eq(0)
    keys = module["Record Key"]
    return {"roster_rows": len(roster), "module_rows": len(module),
            "age_5_plus_roster": int(eligible.sum()),
            "eligible_absent_from_module": int((eligible & ~age.index.isin(keys)).sum()),
            "under_5_module_rows": int(keys.isin(age.index[under]).sum()),
            "unlinked_module_rows": int((~keys.isin(age.index)).sum()),
            "unknown_or_invalid_age_module_rows": int(keys.isin(age.index[~(eligible | under)]).sum()),
            "limitation": "Age universe only; usual residence, item response and routing not certified."}


def build(root):
    root = root.resolve()
    verify(root)
    cache = root / CACHE
    text_cache = cache / "legacy_word_text_v1"
    manifest = json.loads((text_cache / "manifest.json").read_text())
    if file_sha(cache / "manifest.json") != manifest["source_manifest_sha256"]:
        raise ValueError("Original questionnaire manifest changed")
    for name, digest in manifest["artifacts"].items():
        if file_sha(text_cache / name) != digest:
            raise ValueError("Text evidence changed")
    for source in manifest["sources"]:
        if file_sha(cache / source["original_path"]) != source["original_sha256"]:
            raise ValueError("Original Word evidence changed")
    outputs, summaries, rosters = {}, {}, {}
    for wave, evidence in EVIDENCE.items():
        name = f"{wave}/{evidence['file']}.json"
        text = json.loads((text_cache / name).read_text())
        if text["source_sha256"] != evidence["sha256"]:
            raise ValueError("Questionnaire fingerprint mismatch")
        line = text["lines"][evidence["line"] - 1]
        if line["line"] != evidence["line"] or evidence["quote"] not in line["text"]:
            raise ValueError("Age instruction locator mismatch")
        roster = pd.read_parquet(root / CANDIDATES / f"tables/{wave}/HL.parquet")
        qualified = qualify_age(roster["Age Source Value"])
        result = pd.concat([roster, qualified], axis=1)
        result["Age Evidence ID"] = f"legacy_age_{wave}_98plus"
        rosters[wave] = roster
        outputs[f"HL_{wave}_age_qualified.parquet"] = parquet_bytes(result)
        summaries[wave] = {"rows": len(result), "status_counts": qualified["Age Qualification Status"].value_counts().to_dict(),
                           "evidence": {**evidence, "text_json": name}}
    form = json.loads((text_cache / "1999/QuestENG_Form3Page.json").read_text())
    scope_lines = [r for r in form["lines"] if "all members aged" in r["text"] and "5 years and older" in r["text"]]
    if len(scope_lines) != 2:
        raise ValueError("Expected education and employment age universe instructions")
    scopes = {}
    for module, line in zip(["ED", "EC"], scope_lines, strict=True):
        frame = pd.read_parquet(root / CANDIDATES / f"tables/1999/{module}.parquet")
        scopes[module] = {**scope_audit(rosters["1999"], frame), "source_instruction": line}
    report = {"state": "local_candidate_not_published", "age": summaries, "1999_age_universes": scopes,
              "original_tables_modified": False, "database_modified": False}
    outputs["summary.json"] = encoded(report)
    output = root / OUTPUT
    hashes = {name: put(output / name, payload) for name, payload in outputs.items()}
    put(output / "manifest.json", encoded({"artifacts": hashes, "builder_sha256": file_sha(Path(__file__)),
        "candidate_manifest_sha256": file_sha(root / CANDIDATES / "manifest.json"),
        "word_text_manifest_sha256": file_sha(text_cache / "manifest.json")}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    print(json.dumps(build(parser.parse_args().root), indent=2))
