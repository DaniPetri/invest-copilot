import json

import pytest

from app.schemas.events import SSEEventAdapter

from .conftest import FIXTURE_DIR

FILES = sorted(FIXTURE_DIR.glob("*.jsonl"))


def _lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _ui_blocks(name):
    return next(x["data"]["blocks"] for x in _lines(FIXTURE_DIR / name) if x["event"] == "ui")


def test_the_five_fixture_streams_exist():
    assert [f.name for f in FILES] == [
        "advice_refusal.jsonl",
        "depot_august.jsonl",
        "discover.jsonl",
        "roentgen.jsonl",
        "simulate.jsonl",
    ]


def test_the_streams_together_cover_all_eleven_block_types():
    kinds = {b["type"] for f in FILES for b in _ui_blocks(f.name)}
    assert kinds == {
        "text", "product_cards", "risk_meter", "fan_chart", "exposure_bars", "overlap_matrix",
        "attribution", "cost_breakdown", "suitability", "handoff", "citations",
    }  # fmt: skip


def test_simulate_and_roentgen_streams_show_their_tools():
    sim = {x["data"]["name"] for x in _lines(FIXTURE_DIR / "simulate.jsonl") if x["event"] == "tool_start"}
    assert sim == {"simulate_savings_plan", "cost_projection", "suitability_check", "search_kid"}
    assert any(x["event"] == "retrieval" for x in _lines(FIXTURE_DIR / "simulate.jsonl"))
    roentgen = [x for x in _lines(FIXTURE_DIR / "roentgen.jsonl") if x["event"] == "tool_start"]
    assert [x["data"]["name"] for x in roentgen] == ["portfolio_lookthrough"]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_fixture_events_validate(path):
    for i, line in enumerate(_lines(path)):
        delay = line.pop("delay_ms")
        assert isinstance(delay, int) and delay >= 0, f"line {i + 1}"
        SSEEventAdapter.validate_python(line)


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_fixture_event_order(path):
    names = [x["event"] for x in _lines(path)]
    assert names[0] == "trace" and names[1] == "router" and names[-1] == "done"
    assert names.count("done") == 1 and "error" not in names
    assert names.index("text_delta") < names.index("ui") < names.index("guardrail") < names.index("done")
    assert names.index("usage") > names.index("guardrail")


def test_discover_ends_with_product_cards_and_citations():
    kinds = [b["type"] for b in _ui_blocks("discover.jsonl")]
    assert "product_cards" in kinds and kinds[-1] == "citations"


def test_depot_ends_with_attribution():
    assert _ui_blocks("depot_august.jsonl")[-1]["type"] == "attribution"


def test_advice_stream_has_handoff_and_no_tools():
    lines = _lines(FIXTURE_DIR / "advice_refusal.jsonl")
    names = {x["event"] for x in lines}
    assert not {"tool_start", "tool_end", "retrieval"} & names
    assert next(x for x in lines if x["event"] == "router")["data"]["flags"]["advice_request"] is True
    assert _ui_blocks("advice_refusal.jsonl")[-1]["type"] == "handoff"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_text_deltas_equal_final_text_block(path):
    lines = _lines(path)
    streamed = "".join(x["data"]["text"] for x in lines if x["event"] == "text_delta")
    assert streamed == _ui_blocks(path.name)[0]["markdown"]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_done_cost_is_sum_of_usage(path):
    lines = _lines(path)
    usage = sum(x["data"]["cost_eur"] for x in lines if x["event"] == "usage")
    done = next(x["data"]["cost_eur"] for x in lines if x["event"] == "done")
    assert done == pytest.approx(usage, abs=1e-4)
