"""Regression test from docs/trace_case.md: swarm C-002@55 (FM-03 ticket_trust).

The ticket says "giao trễ 5 ngày", the DB says delay_days=2. On seed 55 (seed % 5 == 0) the
reference swarm writes `model_override {"delay_days": 5}` at event 3 and refunds 20.000đ for a
claim whose label is denied. The test runs the real shapes on a fresh store and pins both sides:
the graders must flag the buggy trace, and the fix must keep the DB fact and pass."""
import pytest

pytestmark = pytest.mark.student
CLAIM, SEED = "C-002", 55


def _ctx(case):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="trace_case", inputs={}, metadata=None, expected_output=case["label"],
                            output=case["trial"], duration=0.0, _span_tree=None, attributes={}, metrics={})


@pytest.fixture(scope="module")
def run():
    from lab9.trace_case import investigate

    return lambda shape: investigate(shape, CLAIM, SEED)


def test_first_wrong_step_is_model_override(run):
    events = run("swarm")["trial"]["events"]
    kinds = [e.get("kind") for e in events]
    first = kinds.index("model_override")
    assert first == 2                                                   # event #3 (1-based)
    assert events[1]["payload"]["lookup_order"]["order"]["delay_days"] == 2   # #2 read the DB right
    assert events[first]["payload"] == {"delay_days": 5}


def test_graders_catch_ticket_trust_on_swarm(run):
    from lab9.graders import DbFactKept, RefundAmountCorrect, TrialPass

    c = _ctx(run("swarm"))
    assert DbFactKept().evaluate(c).value is False
    assert RefundAmountCorrect().evaluate(c).value is False             # ledger 20000, label 0
    assert TrialPass().evaluate(c).value is False


def test_fixed_keeps_db_fact_and_passes(run):
    from lab9.graders import ApprovalBypass, DbFactKept, RefundAmountCorrect, TrialPass

    case = run("fixed")
    c = _ctx(case)
    assert "model_override" not in [e.get("kind") for e in case["trial"]["events"]]
    assert DbFactKept().evaluate(c).value is True
    assert RefundAmountCorrect().evaluate(c).value is True
    assert ApprovalBypass().evaluate(c).value is False
    assert TrialPass().evaluate(c).value is True
