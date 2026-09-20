"""M6: POST /api/chat over real SSE and GET /api/traces/{id}, with a scripted agent."""

import json

import pytest
from fastapi.testclient import TestClient

from app.agent.orchestrator import Agent
from app.config import Settings
from app.main import app, get_agent, get_trace_store
from app.schemas.events import SSEEventAdapter, TraceRecord
from app.tracing.store import TraceStore

from .fakes import ScriptedLLM, render_turn, router, text_block, text_turn
from .test_debug_sse import _parse_sse


@pytest.fixture
def client(ctx):
    store = TraceStore(":memory:")
    llm = ScriptedLLM(
        [router("learn"), text_turn(), render_turn([text_block("Ein ETF ist ein börsengehandelter Fonds.")])]
    )
    agent = Agent(llm, ctx, Settings(_env_file=None, anthropic_api_key=None), store)
    app.dependency_overrides[get_agent] = lambda: agent
    app.dependency_overrides[get_trace_store] = lambda: store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    store.close()


def test_chat_streams_the_agent_events_over_sse(client):
    res = client.post("/api/chat", json={"customer_id": "anna", "message": "Was ist ein ETF?"})
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(res.text)
    names = [n for n, _ in events]
    assert (
        names[0] == "trace"
        and names[-1] == "done"
        and {"router", "usage", "text_delta", "ui", "guardrail"} <= set(names)
    )
    for name, data in events:  # every wire event validates against the contract
        SSEEventAdapter.validate_python({"event": name, "data": json.loads(data)})
    text = "".join(json.loads(d)["text"] for n, d in events if n == "text_delta")
    assert text == "Ein ETF ist ein börsengehandelter Fonds."


def test_the_trace_can_be_fetched_after_the_stream(client):
    res = client.post("/api/chat", json={"customer_id": "anna", "message": "Was ist ein ETF?"})
    trace_id = json.loads(next(d for n, d in _parse_sse(res.text) if n == "trace"))["trace_id"]

    got = client.get(f"/api/traces/{trace_id}")
    assert got.status_code == 200
    record = TraceRecord.model_validate(got.json())
    assert (
        record.status == "ok" and record.intent == "learn" and record.mode == "replay" and record.customer_id == "anna"
    )
    assert [e.event for e in record.events][0] == "trace" and [e.event for e in record.events][-1] == "done"
    assert record.cost_eur is not None and record.cost_eur > 0 and record.total_ms is not None

    assert client.get("/api/traces/tr_unknown").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"customer_id": "anna"},  # message missing
        {"customer_id": "anna", "message": ""},
        {"customer_id": "anna", "message": "x" * 2001},
        {"customer_id": "anna", "message": "hi", "extra": 1},  # unknown field
    ],
)
def test_invalid_chat_requests_are_rejected(client, body):
    assert client.post("/api/chat", json=body).status_code == 422


def test_an_unknown_customer_ends_the_stream_with_an_error_event(client):
    res = client.post("/api/chat", json={"customer_id": "nobody", "message": "Hallo"})
    assert [n for n, _ in _parse_sse(res.text)] == ["trace", "error"]


def test_chat_without_generated_data_streams_a_data_missing_error(tmp_path):
    from app.data.store import Store
    from app.main import get_tool_context
    from app.tools.base import ToolContext

    app.dependency_overrides.clear()
    app.dependency_overrides[get_tool_context] = lambda: ToolContext(Store(tmp_path / "empty"))
    try:
        # the store is lazy: a missing universe surfaces as an error event that says what to run, not a crash
        res = TestClient(app).post("/api/chat", json={"customer_id": "anna", "message": "Hallo"})
        assert res.status_code == 200
        names = [n for n, _ in _parse_sse(res.text)]
        assert names[-1] == "error" and "make data" in json.loads(_parse_sse(res.text)[-1][1])["message"]
    finally:
        app.dependency_overrides.clear()
