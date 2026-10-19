#!/usr/bin/env python3
"""Versioned driver fixing unknown-date normalization before first publication.

The frozen v1 engine and its rolled-back evidence are retained. This driver reuses
its transactional publication, with strict date validation and both code hashes
pinned through an implementation manifest in the prepared SQL definitions.
"""
import argparse
import json
from pathlib import Path

import pandas as pd
import publish_cses_2025_age as engine
from build_cses_additional_waves import encoded
from cache_cses_questionnaires import file_sha, put

SELF = Path(__file__).resolve()
ROOT = SELF.parents[2]
VERSION = 'cses-2025-age-source-v2'
OUT = ROOT / 'data/releases' / VERSION
ORIGINAL_CALENDAR = engine.calendar_check
ORIGINAL_CHECKED = engine.checked
ORIGINAL_DEFINITIONS = engine.definitions


def calendar_check(roster, cover):
    """Reject missing codes and any date normalized away from its components."""
    year, month, day = (roster[c] for c in ['q01ac04c', 'q01ac04b', 'q01ac04a'])
    bounded = (year.between(1, 9999) & month.between(1, 12) & day.between(1, 31)
               & year.mod(1).eq(0) & month.mod(1).eq(0) & day.mod(1).eq(0))
    birth = pd.to_datetime(dict(year=year.where(bounded), month=month.where(bounded),
                               day=day.where(bounded)), errors='coerce')
    valid = bounded & birth.dt.year.eq(year) & birth.dt.month.eq(month) & birth.dt.day.eq(day)
    safe = roster.copy(deep=True)
    for column in ['q01ac04a', 'q01ac04b', 'q01ac04c']:
        safe[column] = safe[column].where(valid)
    return ORIGINAL_CALENDAR(safe, cover)


def checked():
    implementation = json.loads((OUT / 'implementation.json').read_text())
    for relative, sha in implementation['code'].items():
        engine.require(file_sha(ROOT / relative) == sha, 'Versioned implementation changed: ' + relative)
    return ORIGINAL_CHECKED()


def definitions():
    definitions = ORIGINAL_DEFINITIONS()
    # SQL literal hash makes the execution plan pin the versioned driver too.
    definitions[engine.RULE] += (f",'{file_sha(OUT / 'implementation.json')}'::text AS implementation_sha256")
    return definitions


def build():
    evidence = engine.build()
    put(OUT / 'implementation.json', encoded({'version': VERSION,
        'code': {str(SELF.relative_to(ROOT)): file_sha(SELF),
                 str(Path(engine.__file__).resolve().relative_to(ROOT)): file_sha(Path(engine.__file__))},
        'rejected_diagnostic': 'cses-2025-age-source-v1; rollback only; never published',
        'correction': 'Reject -98, noninteger and normalized invalid birth components before calendar checks.'}))
    return evidence


# The physical/view names remain v1: this is their FIRST committed publication.
engine.VERSION = VERSION
engine.OUT = OUT
engine.BACKUP = ROOT / 'data/backups/cses_2025_age_v2/before_2025_age.dump'
engine.calendar_check = calendar_check
engine.checked = checked
engine.definitions = definitions


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'prepare', 'rehearse', 'publish', 'validate'])
    action = parser.parse_args().action
    result = {'build': build, 'prepare': engine.prepare, 'rehearse': lambda: engine.publish(True),
              'publish': engine.publish, 'validate': engine.postflight}[action]()
    print(json.dumps(result, indent=2))
