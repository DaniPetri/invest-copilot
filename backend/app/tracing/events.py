"""Event emission: every SSE event of a request is validated against the contract, timed, persisted and returned in
the `{"event", "data"}` shape sse-starlette sends."""

import json
import time
from datetime import UTC, datetime
from typing import Any

from ..config import cost_eur
from ..schemas.events import SSEEventAdapter
from .store import TraceStore


def validate_event(event: str, data: dict[str, Any]) -> dict[str, Any]:
    """Round-trips through the SSE envelope models; raises pydantic.ValidationError if the payload breaks the contract.
    Returns the JSON-ready data (defaults filled in)."""
    parsed = SSEEventAdapter.validate_python({"event": event, "data": data})
    return parsed.data.model_dump(mode="json")


class TraceRecorder:
    """One per request: numbers the events, times them from the start of the request, stores them, adds up cost."""

    def __init__(self, trace_id: str, store: TraceStore | None):
        self.trace_id = trace_id
        self.store = store
        self.t0 = time.perf_counter()
        self.started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.cost_eur = 0.0
        self.events: list[dict[str, Any]] = []  # what was emitted, for tests and the fallback path
        self._seq = 0

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.t0) * 1000)

    def emit(self, event: str, data: dict[str, Any]) -> dict[str, str]:
        clean = validate_event(event, data)
        self._seq += 1
        self.events.append({"event": event, "data": clean})
        if self.store is not None:
            self.store.add_event(self.trace_id, self._seq, self.elapsed_ms(), event, clean)
        return {"event": event, "data": json.dumps(clean, ensure_ascii=False)}

    def usage(self, model: str, input_tokens: int, output_tokens: int) -> dict[str, str]:
        cost = cost_eur(model, input_tokens, output_tokens)
        self.cost_eur += cost
        return self.emit(
            "usage",
            {"model": model, "input_tokens": input_tokens, "output_tokens": output_tokens, "cost_eur": round(cost, 6)},
        )
