import pytest
from pydantic import ValidationError

from app.schemas.events import RouterDecision, SSEEventAdapter
from app.schemas.products import Product
from app.schemas.tools import TOOL_MODELS
from app.schemas.ui import UIBlockAdapter

BLOCKS = [
    {"type": "text", "markdown": "Hallo", "citations": []},
    {"type": "risk_meter", "sri": 4},
    {
        "type": "fan_chart",
        "years": [1],
        "p5": [1.0],
        "p25": [1.0],
        "p50": [1.0],
        "p75": [1.0],
        "p95": [1.0],
        "contributions": [1.0],
    },
    {"type": "exposure_bars", "dimension": "sector", "rows": [{"key": "tech", "label": "Technologie", "weight": 0.4}]},
    {"type": "overlap_matrix", "products": [{"product_id": "P01", "name": "A"}], "matrix": [[1.0]]},
    {
        "type": "cost_breakdown",
        "rows": [{"label": "TER", "amount_eur": 45.0}],
        "total": 45.0,
        "total_pct_of_contributions": None,
    },
    {
        "type": "suitability",
        "verdict": "warn",
        "reasons": [{"rule": "risk", "status": "warn", "text": "x", "profile_field": "risk_class"}],
    },
    {"type": "handoff", "reason": "r", "actions": [{"id": "a", "label": "A"}]},
    {
        "type": "citations",
        "items": [
            {"chunk_id": "KID:P01:p1:ziele", "product_name": "A", "page": 1, "section": "Ziele", "snippet": "s"}
        ],
    },
]


@pytest.mark.parametrize("block", BLOCKS, ids=lambda b: b["type"])
def test_ui_block_round_trips(block):
    parsed = UIBlockAdapter.validate_python(block)
    assert parsed.model_dump(mode="json") == block


def test_unknown_block_type_is_rejected():
    with pytest.raises(ValidationError):
        UIBlockAdapter.validate_python({"type": "iframe", "src": "https://evil.example"})


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        UIBlockAdapter.validate_python({"type": "risk_meter", "sri": 4, "extra": 1})


def test_sri_range_enforced():
    with pytest.raises(ValidationError):
        UIBlockAdapter.validate_python({"type": "risk_meter", "sri": 8})


EVENT_EXAMPLES = {
    "trace": {"trace_id": "t", "started_at": "2026-09-20T00:00:00Z", "mode": "replay"},
    "router": {"intent": "discover", "flags": {}, "confidence": 0.5, "model": "m", "latency_ms": 1},
    "tool_start": {"call_id": "c", "name": "screen_products", "args": {}},
    "tool_end": {
        "call_id": "c",
        "name": "screen_products",
        "ok": True,
        "duration_ms": 1,
        "result_id": None,
        "summary": "s",
    },
    "retrieval": {"query": "q", "mode": "bm25", "chunks": []},
    "text_delta": {"text": "x"},
    "ui": {"blocks": []},
    "guardrail": {"checks": [{"name": "n", "status": "flag", "detail": "d"}]},
    "usage": {"model": "m", "input_tokens": 1, "output_tokens": 1, "cost_eur": 0.0},
    "done": {"trace_id": "t", "total_ms": 1, "cost_eur": 0.0},
    "error": {"code": "x", "message": "m"},
}


def test_every_sse_event_name_from_the_spec_is_covered():
    spec_events = {
        "trace", "router", "tool_start", "tool_end", "retrieval", "text_delta",
        "ui", "guardrail", "usage", "done", "error",
    }
    assert set(EVENT_EXAMPLES) == spec_events
    for name, data in EVENT_EXAMPLES.items():
        assert SSEEventAdapter.validate_python({"event": name, "data": data}).event == name


def test_unknown_event_rejected():
    with pytest.raises(ValidationError):
        SSEEventAdapter.validate_python({"event": "mystery", "data": {}})


def test_router_intents_and_confidence_bounds():
    ok = {"intent": "advice_request", "slots": {}, "flags": {"advice_request": True}, "confidence": 0.9}
    assert RouterDecision.model_validate(ok).flags.advice_request is True
    with pytest.raises(ValidationError):
        RouterDecision.model_validate({**ok, "intent": "smalltalk"})
    with pytest.raises(ValidationError):
        RouterDecision.model_validate({**ok, "confidence": 1.5})


def test_product_isin_prefix_enforced():
    base = {
        "id": "P01", "isin": "XD0000000782", "name": "n", "issuer": "i", "asset_class": "equity_etf",
        "region": "Welt", "sfdr": 8, "exclusions": [], "ter": 0.002, "entry_cost": 0.0,
        "distribution": "thesaurierend", "savings_plan_min_eur": None, "replication": "physisch",
        "inception": "2020-01-01", "fund_size_eur_m": 100.0, "benchmark": "b", "sri": 4,
        "recommended_holding_years": 5, "holdings": [],
    }
    assert Product.model_validate(base)
    with pytest.raises(ValidationError):
        Product.model_validate({**base, "isin": "DE0000000782"})


def test_all_seven_tools_have_models():
    assert set(TOOL_MODELS) == {
        "screen_products", "search_kid", "portfolio_lookthrough", "explain_move",
        "simulate_savings_plan", "cost_projection", "suitability_check",
    }
