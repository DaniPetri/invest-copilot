"""M6: request hashing, recording and replay of cassettes, and LLM_MODE selection. No network."""

import json

import pytest

from app.agent.llm import (
    AnthropicClient,
    CassetteMiss,
    LLMRequest,
    RecordingClient,
    ReplayClient,
    make_llm_client,
    normalise_request,
    request_hash,
)
from app.config import Settings

from .fakes import ScriptedLLM, router, text_turn, tool_turn, tool_use


def req(**kw) -> LLMRequest:
    base = {
        "model": "claude-sonnet-5",
        "system": "Du bist ein Assistent.",
        "messages": [{"role": "user", "content": "Was ist ein ETF?"}],
        "max_tokens": 100,
        "label": "orchestrator",
    }
    return LLMRequest(**{**base, **kw})


# ── hashing ─────────────────────────────────────────────────────────────────


def test_the_hash_ignores_the_label_and_the_random_tool_use_ids():
    history_a = [
        {"role": "user", "content": "Frage"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "toolu_AAA", "name": "screen_products", "input": {}}],
        },
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_AAA", "content": "ok"}]},
    ]
    history_b = json.loads(json.dumps(history_a).replace("toolu_AAA", "toolu_ZZZ"))
    assert request_hash(req(messages=history_a, label="x")) == request_hash(req(messages=history_b, label="y"))
    assert normalise_request(req(messages=history_a))["messages"][1]["content"][0]["id"] == "tool_0"


def test_the_hash_changes_with_every_part_of_the_request():
    base = request_hash(req())
    variants = [
        req(system="Anderer Prompt"),
        req(messages=[{"role": "user", "content": "Andere Frage"}]),
        req(model="claude-haiku-4-5-20251001"),
        req(tools=[{"name": "t"}]),
        req(tool_choice={"type": "tool", "name": "render_ui"}),
        req(output_config={"format": {}}),
        req(thinking={"type": "disabled"}),
        req(max_tokens=200),
    ]
    assert len({base, *(request_hash(v) for v in variants)}) == len(variants) + 1


def test_the_hash_does_not_depend_on_key_order():
    a = req(tools=[{"name": "t", "input_schema": {"a": 1, "b": 2}}])
    b = req(tools=[{"input_schema": {"b": 2, "a": 1}, "name": "t"}])
    assert request_hash(a) == request_hash(b)


# ── record and replay ───────────────────────────────────────────────────────


async def test_recording_writes_a_cassette_and_replay_returns_the_same_response(tmp_path):
    live = ScriptedLLM([tool_turn(tool_use("screen_products", {"limit": 3}))])
    recorder = RecordingClient(live, tmp_path)
    request = req()
    recorded = await recorder.complete(request)

    files = list(tmp_path.glob("*.jsonl"))
    assert [f.stem for f in files] == [request_hash(request)[:32]]
    meta, body = (json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines())
    assert meta["hash"] == request_hash(request)  # the full sha256 is inside the file
    assert meta["kind"] == "meta" and meta["label"] == "orchestrator" and meta["first_user"] == "Was ist ein ETF?"
    assert body["kind"] == "response" and body["stop_reason"] == "tool_use"

    replayed = await ReplayClient(tmp_path).complete(request)
    assert replayed.content == recorded.content and replayed.stop_reason == recorded.stop_reason
    assert (replayed.input_tokens, replayed.output_tokens) == (recorded.input_tokens, recorded.output_tokens)
    assert replayed.tool_uses[0]["name"] == "screen_products"


async def test_recording_is_idempotent_and_refresh_re_records(tmp_path):
    live = ScriptedLLM([text_turn("erste Antwort"), text_turn("zweite Antwort")])
    request = req()
    first = await RecordingClient(live, tmp_path).complete(request)
    again = await RecordingClient(live, tmp_path).complete(request)  # served from the cassette: no second live call
    assert again.text == first.text == "erste Antwort" and len(live.requests) == 1

    refreshed = await RecordingClient(live, tmp_path, refresh=True).complete(request)
    assert refreshed.text == "zweite Antwort" and len(live.requests) == 2
    assert (await ReplayClient(tmp_path).complete(request)).text == "zweite Antwort"


async def test_replay_miss_names_the_hash_and_what_changed(tmp_path):
    await RecordingClient(ScriptedLLM([text_turn()]), tmp_path).complete(req())

    with pytest.raises(CassetteMiss) as e:
        await ReplayClient(tmp_path).complete(req(system="Ein geänderter Systemprompt"))
    msg = str(e.value)
    assert e.value.code == "cassette_miss" and request_hash(req(system="Ein geänderter Systemprompt"))[:16] in msg
    assert "differs in: system" in msg and "make record" in msg  # the closest recording, and the part that changed

    with pytest.raises(CassetteMiss) as e:  # nothing recorded for this conversation at all
        await ReplayClient(tmp_path).complete(req(messages=[{"role": "user", "content": "Ganz neu"}]))
    assert "Closest recording" not in str(e.value)


async def test_replay_with_a_missing_cassette_directory_is_a_clean_miss(tmp_path):
    with pytest.raises(CassetteMiss):
        await ReplayClient(tmp_path / "does-not-exist").complete(req())


async def test_a_full_recorded_conversation_replays_through_the_agent(ctx, tmp_path):
    """Record an agent run with a scripted 'live' client, then replay it from cassettes only."""
    from app.agent.orchestrator import Agent
    from app.schemas.events import ChatRequest

    from .fakes import render_turn, text_block

    def script():
        return ScriptedLLM([router("learn"), text_turn(), render_turn([text_block("Ein ETF ist ein Fonds.")])])

    async def run(client):
        agent = Agent(client, ctx, Settings(_env_file=None, anthropic_api_key=None))
        return [
            json.loads(e["data"]) async for e in agent.run(ChatRequest(customer_id="anna", message="Was ist ein ETF?"))
        ]

    recorded = await run(RecordingClient(script(), tmp_path))
    replayed = await run(ReplayClient(tmp_path))
    assert len(list(tmp_path.glob("*.jsonl"))) == 3
    ui = [d for d in replayed if "blocks" in d][0]
    assert ui["blocks"][0]["markdown"] == "Ein ETF ist ein Fonds."
    assert [d.get("model") for d in recorded if "input_tokens" in d] == [
        d.get("model") for d in replayed if "input_tokens" in d
    ]


# ── mode selection ──────────────────────────────────────────────────────────


def test_llm_mode_selection(tmp_path):
    def build(**kw):
        return make_llm_client(Settings(_env_file=None, cassette_dir=tmp_path, **kw))

    assert build(anthropic_api_key=None).mode == "replay"  # no key: replay, whatever LLM_MODE says
    assert build(anthropic_api_key=None, llm_mode="live").mode == "replay"
    assert build(anthropic_api_key="sk-test", llm_mode="live").mode == "live"
    assert isinstance(build(anthropic_api_key="sk-test", llm_mode="live"), AnthropicClient)
    assert build(anthropic_api_key="sk-test").mode == "replay"  # a key alone does not switch to live
    recorder = build(anthropic_api_key="sk-test", llm_mode="record", record_refresh=True)
    assert recorder.mode == "record" and recorder.refresh is True and recorder.directory == tmp_path
