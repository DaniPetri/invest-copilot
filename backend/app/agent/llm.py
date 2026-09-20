"""LLM clients (SPEC §8): live, recording and replay behind one protocol.

    client = make_llm_client()                      # LLM_MODE=live|record|replay, replay when there is no key
    response = await client.complete(LLMRequest(...))

Requests and responses are plain dicts and dataclasses, so a cassette is readable JSON and a scripted fake in the
tests is a few lines. `ReplayClient` looks a request up by the sha256 of its *normalised* form; `RecordingClient`
wraps the live client and writes the cassettes (`make record`).
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from anthropic import APIConnectionError, APIStatusError, AsyncAnthropic

from ..config import Settings, get_settings

log = logging.getLogger(__name__)


class LLMError(Exception):
    """A provider problem the caller can report as an `error` event."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class CassetteMiss(LLMError):
    """Replay mode has no recording for this exact request."""

    def __init__(self, message: str):
        super().__init__("cassette_miss", message)


@dataclass
class LLMRequest:
    model: str
    system: str
    messages: list[dict[str, Any]]
    max_tokens: int = 4096
    tools: list[dict[str, Any]] | None = None
    tool_choice: dict[str, Any] | None = None
    output_config: dict[str, Any] | None = None
    thinking: dict[str, Any] | None = None
    label: str = ""  # "router" | "orchestrator" | "render": for humans (trace, cassette meta), not part of the hash

    def api_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": self.system,
            "messages": self.messages,
        }
        for key in ("tools", "tool_choice", "output_config", "thinking"):
            if (value := getattr(self, key)) is not None:
                kwargs[key] = value
        return kwargs


@dataclass
class LLMResponse:
    content: list[dict[str, Any]]
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    model: str
    latency_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def text(self) -> str:
        return "".join(b.get("text", "") for b in self.content if b.get("type") == "text")

    @property
    def tool_uses(self) -> list[dict[str, Any]]:
        return [b for b in self.content if b.get("type") == "tool_use"]


class LLMClient(Protocol):
    mode: Literal["live", "record", "replay"]

    async def complete(self, req: LLMRequest) -> LLMResponse: ...


# ── normalisation and hashing ───────────────────────────────────────────────


def normalise_request(req: LLMRequest) -> dict[str, Any]:
    """The request as it is hashed: only API-relevant fields, and tool_use ids replaced by their order of appearance
    (they are random per run), so a re-recording does not change the key of an unchanged conversation."""
    ids: dict[str, str] = {}

    def canon(node: Any) -> Any:
        if isinstance(node, dict):
            out = {}
            for key, value in node.items():
                if key in ("id", "tool_use_id") and isinstance(value, str) and value.startswith("toolu_"):
                    out[key] = ids.setdefault(value, f"tool_{len(ids)}")
                else:
                    out[key] = canon(value)
            return out
        if isinstance(node, list):
            return [canon(v) for v in node]
        return node

    return canon(req.api_kwargs())


def _sha(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def request_hash(req: LLMRequest) -> str:
    return _sha(normalise_request(req))


def _parts(norm: dict[str, Any]) -> dict[str, str]:
    """Hash per top-level field: a cassette miss can then say *which* part of the request changed."""
    return {key: _sha(value)[:12] for key, value in norm.items()}


def _first_user_text(req: LLMRequest) -> str:
    for m in req.messages:
        if m.get("role") == "user":
            c = m["content"]
            return c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
    return ""


# ── live ────────────────────────────────────────────────────────────────────


class AnthropicClient:
    mode: Literal["live", "record", "replay"] = "live"

    def __init__(self, api_key: str, client: AsyncAnthropic | None = None):
        self._client = client or AsyncAnthropic(api_key=api_key)

    async def complete(self, req: LLMRequest) -> LLMResponse:
        import time

        started = time.perf_counter()
        try:
            # Streaming plus get_final_message() is the SDK's recommended way to be safe from request timeouts.
            async with self._client.messages.stream(**req.api_kwargs()) as stream:
                message = await stream.get_final_message()
        except APIStatusError as e:
            raise LLMError(f"anthropic_{e.status_code}", f"Anthropic API error {e.status_code}: {e.message}") from e
        except APIConnectionError as e:
            raise LLMError("anthropic_connection", f"Could not reach the Anthropic API: {e}") from e
        return LLMResponse(
            content=[b.model_dump(mode="json", exclude_none=True) for b in message.content],
            stop_reason=message.stop_reason,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            model=message.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


# ── cassettes ───────────────────────────────────────────────────────────────


FILENAME_HEX = 32  # 128 bits: no practical collisions, and a full 64-hex name can overflow Windows' 260-char paths


def cassette_path(directory: Path, key: str) -> Path:
    """`fixtures/cassettes/<first 32 hex of the sha256>.jsonl`; the meta line inside carries the full hash."""
    return directory / f"{key[:FILENAME_HEX]}.jsonl"


def _write_cassette(directory: Path, req: LLMRequest, resp: LLMResponse) -> Path:
    norm = normalise_request(req)
    key = _sha(norm)
    meta = {
        "kind": "meta",
        "hash": key,
        "label": req.label,
        "model": req.model,
        "first_user": _first_user_text(req)[:200],
        "n_messages": len(req.messages),
        "parts": _parts(norm),
    }
    body = {
        "kind": "response",
        "content": resp.content,
        "stop_reason": resp.stop_reason,
        "input_tokens": resp.input_tokens,
        "output_tokens": resp.output_tokens,
        "model": resp.model,
        "latency_ms": resp.latency_ms,
    }
    directory.mkdir(parents=True, exist_ok=True)
    path = cassette_path(directory, key)
    lines = [json.dumps(x, ensure_ascii=False, sort_keys=True) for x in (meta, body)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _read_cassette(path: Path) -> LLMResponse:
    body = json.loads(path.read_text(encoding="utf-8").splitlines()[1])
    return LLMResponse(
        content=body["content"],
        stop_reason=body["stop_reason"],
        input_tokens=body["input_tokens"],
        output_tokens=body["output_tokens"],
        model=body["model"],
        latency_ms=body.get("latency_ms", 0),
    )


class ReplayClient:
    mode: Literal["live", "record", "replay"] = "replay"

    def __init__(self, directory: Path):
        self.directory = directory

    async def complete(self, req: LLMRequest) -> LLMResponse:
        key = request_hash(req)
        path = cassette_path(self.directory, key)
        if path.is_file():
            return _read_cassette(path)
        raise CassetteMiss(self._miss_message(req, key))

    def _miss_message(self, req: LLMRequest, key: str) -> str:
        norm = normalise_request(req)
        parts = _parts(norm)
        head = (
            f"No cassette for this request (sha256 {key[:16]}…, model {req.model}, {len(req.messages)} messages, "
            f"first user turn: {_first_user_text(req)[:80]!r}). Run `make record` with an API key to record it."
        )
        # Closest recording: same model and same first user turn. Say which top-level parts differ.
        best: tuple[int, str, dict] | None = None
        for f in sorted(self.directory.glob("*.jsonl")) if self.directory.is_dir() else []:
            meta = json.loads(f.read_text(encoding="utf-8").splitlines()[0])
            if meta["model"] != req.model or meta["first_user"] != _first_user_text(req)[:200]:
                continue
            same = sum(meta["parts"].get(k) == v for k, v in parts.items())
            if best is None or same > best[0]:
                best = (same, f.stem[:16], meta)
        if best:
            differing = [k for k, v in parts.items() if best[2]["parts"].get(k) != v]
            head += (
                f" Closest recording {best[1]}… ({best[2]['n_messages']} messages) differs in: "
                f"{', '.join(differing) or 'nothing (identical parts)'}. A changed prompt or tool schema "
                "needs a re-record."
            )
        return head


class RecordingClient:
    """Live calls, written to cassettes. An existing cassette is served instead of calling again, so recording is
    idempotent and free to repeat; `refresh=True` (RECORD_REFRESH=1) re-records everything."""

    mode: Literal["live", "record", "replay"] = "record"

    def __init__(self, inner: LLMClient, directory: Path, refresh: bool = False):
        self.inner = inner
        self.directory = directory
        self.refresh = refresh

    async def complete(self, req: LLMRequest) -> LLMResponse:
        path = cassette_path(self.directory, request_hash(req))
        if path.is_file() and not self.refresh:
            return _read_cassette(path)
        resp = await self.inner.complete(req)
        _write_cassette(self.directory, req, resp)
        return resp


def make_llm_client(settings: Settings | None = None) -> LLMClient:
    """LLM_MODE=live|record|replay; replay whenever no API key is set (SPEC §8)."""
    s = settings or get_settings()
    mode = s.effective_llm_mode
    if mode == "replay":
        return ReplayClient(s.cassette_dir)
    assert s.anthropic_api_key is not None
    live = AnthropicClient(s.anthropic_api_key.get_secret_value())
    if mode == "record":
        return RecordingClient(live, s.cassette_dir, refresh=s.record_refresh)
    return live
