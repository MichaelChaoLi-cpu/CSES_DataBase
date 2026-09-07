"""Publication guardrails; live rollback/postflight provide integration coverage."""
import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rsc/cses_db"))
import publish_cses_age_topcode as pub  # noqa: E402


def test_scope_is_exactly_five_additive_views():
    assert set(pub.VIEWS) == {"cses_hl_age_v1", "cses_ed_age_v1", "cses_ec_age_v1", "cses_hh_head_age_v1", "cses_age_2004_rule_v1"}
    assert len(pub.VIEWS) == 5


def test_wrong_execution_confirmation_stops_before_database_or_backup(monkeypatch):
    monkeypatch.setattr(pub, "plan_checked", lambda root: {})
    monkeypatch.setattr(pub, "execution", lambda root: ({}, "expected"))
    with pytest.raises(ValueError, match="Literal verified execution"):
        pub.apply(ROOT, "wrong")


def test_existing_target_is_never_replaced():
    class Result:
        def fetchall(self):
            return [{"relname": "cses_hl_age_v1"}]

    class Connection:
        def execute(self, *args):
            return Result()

    with pytest.raises(ValueError, match="Target exists"):
        pub.absent(Connection())


def test_no_destructive_or_metadata_dml_statements_in_writer():
    tree = ast.parse((ROOT / pub.SELF).read_text())
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not any(s.lstrip().upper().startswith(("DROP ", "DELETE ", "UPDATE ", "INSERT ", "TRUNCATE ", "CREATE OR REPLACE")) for s in strings)
    assert any(s.startswith("CREATE VIEW") for s in strings)


def test_checks_and_protected_state_comparison_precede_commit():
    tree = ast.parse((ROOT / pub.SELF).read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "apply")
    source = ast.unparse(node)
    assert source.index("results = checks") < source.index("conn.commit()")
    assert source.index("Protected state changed after view creation") < source.index("conn.commit()")
    assert "conn.rollback()" in source
