"""Additive HEALTH publication contract; database writes require explicit CLI gates."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cses_db"))
from publish_cses_health_illness import (  # noqa: E402
    APPEND_KEYS,
    JSON_COLUMNS,
    OBJECTS,
    SOURCE,
    VERSION,
    compare,
    descriptor,
    execution,
    load_frame,
    registry_ddl,
)


def test_targets_are_additive_and_bounded():
    assert len(OBJECTS) == 5
    assert all("health_illness" in n for _, n in OBJECTS)
    assert not any("final_" in n for _, n in OBJECTS)
    assert ("cses_data", SOURCE) in OBJECTS
    assert not any(t.startswith("cses_data.") for t in APPEND_KEYS)


def test_registry_ddl_escapes_regex_braces_for_psycopg_format():
    ddl = registry_ddl().as_string()
    assert "^[0-9a-f]{64}$" in ddl
    assert '"cses_alignment"."cses_health_illness_evidence_v1"' in ddl


def test_descriptor_preserves_nullable_and_json_types():
    frame = pd.DataFrame({"raw_type_code": pd.Series([99, None], dtype="Float64"),
        "category": pd.Series([None, "x"], dtype="string"),
        "raw_type_answers": pd.Series(['{"q":99}', '{"q":null}'], dtype="string"),
        "strict_screening_eligible": [False, True], "source_row_number": [1, 2]})
    cols = {c["name"]: c for c in descriptor(frame)}
    assert cols["raw_type_code"] == {"name": "raw_type_code", "type": "double precision", "nullable": True}
    assert cols["raw_type_answers"]["type"] == "jsonb"
    assert cols["source_row_number"]["type"] == "bigint"
    assert cols["category"]["nullable"]
    assert not cols["strict_screening_eligible"]["nullable"]


def test_unsupported_dtype_does_not_silently_stringify():
    with pytest.raises(ValueError, match="Unsupported dtype"):
        descriptor(pd.DataFrame({"x": [object()]}))


def test_json_fields_include_every_raw_slot_container():
    assert JSON_COLUMNS == {"raw_record", "source_member_chain", "raw_type_answers", "source_type_variables"}


def test_execution_refuses_wrong_confirmation_before_opening_backup(tmp_path):
    folder = tmp_path / "data/releases" / VERSION
    folder.mkdir(parents=True)
    (folder / "execution.json").write_text(json.dumps({"release_id": VERSION}))
    with pytest.raises(ValueError, match="confirmation mismatch"):
        execution(tmp_path, "wrong")


def test_execution_refuses_changed_file(tmp_path):
    folder = tmp_path / "data/releases" / VERSION
    folder.mkdir(parents=True)
    (tmp_path / "source").write_text("changed")
    (folder / "execution.json").write_text(json.dumps({"release_id": VERSION, "file_sha256": {"source": "0" * 64}}))
    with pytest.raises(ValueError, match="input changed"):
        execution(tmp_path)


class FakeCopy:
    def __init__(self):
        self.rows = []

    def cursor(self):
        return self

    def copy(self, statement):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def write_row(self, row):
        self.rows.append(row)


def test_copy_keeps_sentinels_slots_and_nulls():
    frame = pd.DataFrame({"raw_type_code": pd.Series([99, None], dtype="Float64"),
                          "raw_type_answers": pd.Series(['{"a":99,"b":null}', '{"a":null,"b":2}'], dtype="string"),
                          "source_row_number": [1, 2]})
    conn = FakeCopy()
    load_frame(conn, "test", frame, descriptor(frame))
    assert conn.rows[0][0] == 99
    assert conn.rows[1][0] is None
    assert conn.rows[0][1].obj == {"a": 99, "b": None}
    assert conn.rows[1][1].obj == {"a": None, "b": 2}


def test_compare_error_does_not_disclose_respondent_values():
    class FakeRead:
        def execute(self, *args):
            return self

        def fetchall(self):
            return [{"survey_wave": "2021", "source_id": "s", "source_row_number": 1, "secret": "private_answer"}]

    frame = pd.DataFrame({"survey_wave": pd.Series(["2021"], dtype="string"),
        "source_id": pd.Series(["s"], dtype="string"), "source_row_number": [1], "secret": pd.Series(["other"], dtype="string")})
    with pytest.raises(ValueError, match="Cell mismatch") as exc:
        compare(FakeRead(), "schema", "table", frame)
    assert "private_answer" not in str(exc.value)
