"""Router decision and SSE events (SPEC §8, §9).

On the wire each event is `event: <name>` plus `data: <json>`. Recorded streams (fixtures, cassettes)
store one `{"event": ..., "data": ...}` object per line, which is what the envelope models below validate.
"""

from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter

from .base import Contract
from .tools import ToolName
from .ui import UIBlock

Intent = Literal[
    "discover",
    "product_question",
    "portfolio_insight",
    "simulate",
    "learn",
    "advice_request",
    "out_of_scope",
]
LLMMode = Literal["live", "record", "replay"]


# ── router ──────────────────────────────────────────────────────────────────


class RouterSlots(Contract):
    monthly_eur: float | None = None
    years: int | None = None
    regions: list[str] | None = None
    sfdr_min: int | None = None
    exclusions: list[str] | None = None
    product_ids: list[str] | None = None
    topic: str | None = None


class RouterFlags(Contract):
    advice_request: bool = False
    injection_suspected: bool = False
    pii_present: bool = False


class RouterDecision(Contract):
    intent: Intent
    slots: RouterSlots
    flags: RouterFlags
    confidence: float = Field(ge=0, le=1)


# ── event payloads ──────────────────────────────────────────────────────────


class TraceData(Contract):
    trace_id: str
    started_at: str
    mode: LLMMode


class RouterData(Contract):
    intent: Intent
    flags: RouterFlags
    confidence: float = Field(ge=0, le=1)
    model: str
    latency_ms: int = Field(ge=0)


class ToolStartData(Contract):
    call_id: str
    name: ToolName
    args: dict[str, Any]


class ToolEndData(Contract):
    call_id: str
    name: ToolName
    ok: bool
    duration_ms: int = Field(ge=0)
    result_id: str | None
    summary: str


class RetrievalChunk(Contract):
    id: str
    product_id: str
    page: int = Field(ge=1)
    section: str
    score: float
    flags: list[str] = Field(default_factory=list)


class RetrievalData(Contract):
    query: str
    mode: Literal["hybrid", "dense", "bm25", "hybrid_rerank"]
    chunks: list[RetrievalChunk]


class TextDeltaData(Contract):
    text: str


class UIData(Contract):
    blocks: list[UIBlock]


class GuardrailCheck(Contract):
    name: str
    status: Literal["pass", "flag", "fail"]
    detail: str


class GuardrailData(Contract):
    checks: list[GuardrailCheck]


class UsageData(Contract):
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_eur: float = Field(ge=0)


class DoneData(Contract):
    trace_id: str
    total_ms: int = Field(ge=0)
    cost_eur: float = Field(ge=0)


class ErrorData(Contract):
    code: str
    message: str


# ── envelopes (discriminated on `event`) ────────────────────────────────────


class TraceEvent(Contract):
    event: Literal["trace"] = "trace"
    data: TraceData


class RouterEvent(Contract):
    event: Literal["router"] = "router"
    data: RouterData


class ToolStartEvent(Contract):
    event: Literal["tool_start"] = "tool_start"
    data: ToolStartData


class ToolEndEvent(Contract):
    event: Literal["tool_end"] = "tool_end"
    data: ToolEndData


class RetrievalEvent(Contract):
    event: Literal["retrieval"] = "retrieval"
    data: RetrievalData


class TextDeltaEvent(Contract):
    event: Literal["text_delta"] = "text_delta"
    data: TextDeltaData


class UIEvent(Contract):
    event: Literal["ui"] = "ui"
    data: UIData


class GuardrailEvent(Contract):
    event: Literal["guardrail"] = "guardrail"
    data: GuardrailData


class UsageEvent(Contract):
    event: Literal["usage"] = "usage"
    data: UsageData


class DoneEvent(Contract):
    event: Literal["done"] = "done"
    data: DoneData


class ErrorEvent(Contract):
    event: Literal["error"] = "error"
    data: ErrorData


SSEEvent = Annotated[
    TraceEvent
    | RouterEvent
    | ToolStartEvent
    | ToolEndEvent
    | RetrievalEvent
    | TextDeltaEvent
    | UIEvent
    | GuardrailEvent
    | UsageEvent
    | DoneEvent
    | ErrorEvent,
    Field(discriminator="event"),
]

SSEEventAdapter: TypeAdapter[SSEEvent] = TypeAdapter(SSEEvent)
