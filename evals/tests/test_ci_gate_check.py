import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci_gate_check.py"
spec = importlib.util.spec_from_file_location("ci_gate_check", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def gate(suite, metric, passed):
    return {"suite": suite, "metric": metric, "passed": passed}


def test_only_the_known_router_gate_red_passes_with_a_warning():
    report = {"gates": [gate("retrieval", "hybrid_recall_at_5", True), gate("router", "advice_recall", False)]}
    code, lines = mod.check(1, report)
    assert code == 0 and "WARNING" in lines[0] and "router/advice_recall" in lines[0]


def test_any_other_failing_gate_fails_even_next_to_the_known_one():
    report = {"gates": [gate("router", "advice_recall", False), gate("retrieval", "hybrid_recall_at_5", False)]}
    code, lines = mod.check(1, report)
    assert code == 1 and "retrieval/hybrid_recall_at_5" in lines[0]


def test_runner_error_fails():
    assert mod.check(2, {"gates": [gate("router", "advice_recall", True)]})[0] == 1


def test_exit_1_without_a_failed_gate_fails():
    assert mod.check(1, {"gates": [gate("router", "advice_recall", True)]})[0] == 1


def test_all_green_passes_and_empty_report_fails():
    assert mod.check(0, {"gates": [gate("router", "advice_recall", True)]}) == (0, ["all gates passed"])
    assert mod.check(0, {"gates": []})[0] == 1


def test_committed_report_is_exactly_the_documented_state():
    import json

    report = json.loads((SCRIPT.parents[1] / "evals" / "reports" / "bundled.json").read_text(encoding="utf-8"))
    assert mod.check(1, report)[0] == 0
