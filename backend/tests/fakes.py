"""A scripted fake LLM (no network) and helpers to build its responses.

    llm = ScriptedLLM([router("discover"), tool_turn(tool_use("screen_products", {...})), text_turn("BEREIT"),
                       render_turn([text_block("Hallo"), {"type": "product_cards", ...}])])

Each call to `complete` returns the next scripted response and records the request, so tests can assert what reached
the model (`llm.requests`, `llm.request_text()`).
"""

import json
from collections.abc import Callable
from itertools import count
from typing import Any, Literal

from app.agent.llm import LLMRequest, LLMResponse

_ids = count(1)


def _response(
    content: list[dict[str, Any]], stop: str = "end_turn", tokens: tuple[int, int] = (1000, 100)
) -> LLMResponse:
    return LLMResponse(content=content, stop_reason=stop, input_tokens=tokens[0], output_tokens=tokens[1], model="fake")


def router(
    intent: str = "discover", *, advice: bool = False, injection: bool = False, pii: bool = False, **slots
) -> LLMResponse:
    decision = {
        "intent": intent,
        "slots": {
            "monthly_eur": None,
            "years": None,
            "regions": None,
            "sfdr_min": None,
            "exclusions": None,
            "product_ids": None,
            "topic": None,
            **slots,
        },  # fmt: skip
        "flags": {"advice_request": advice, "injection_suspected": injection, "pii_present": pii},
        "confidence": 0.9,
    }
    return _response([{"type": "text", "text": json.dumps(decision)}], tokens=(400, 60))


def tool_use(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": f"toolu_{next(_ids)}", "name": name, "input": args}


def tool_turn(*uses: dict[str, Any]) -> LLMResponse:
    return _response(list(uses), stop="tool_use", tokens=(1500, 80))


def text_turn(text: str = "BEREIT") -> LLMResponse:
    return _response([{"type": "text", "text": text}], tokens=(1600, 5))


def render_turn(blocks: list[dict[str, Any]]) -> LLMResponse:
    return _response([tool_use("render_ui", {"blocks": blocks})], stop="tool_use", tokens=(1800, 300))


def text_block(markdown: str) -> dict[str, Any]:
    return {"type": "text", "markdown": markdown}


def cards_block(result_id: str = "r1", product_ids: list[str] | None = None) -> dict[str, Any]:
    return {"type": "product_cards", "result_id": result_id, "product_ids": product_ids}


class ScriptedLLM:
    mode: Literal["live", "record", "replay"] = "replay"

    def __init__(self, script: list[LLMResponse | Callable[[LLMRequest], LLMResponse | Exception]]):
        self.script = list(script)
        self.requests: list[LLMRequest] = []

    async def complete(self, req: LLMRequest) -> LLMResponse:
        # deep copy through JSON: later mutation of the message list must not change what we recorded
        self.requests.append(LLMRequest(**{**req.__dict__, "messages": json.loads(json.dumps(req.messages))}))
        if not self.script:
            raise AssertionError(f"unscripted LLM call #{len(self.requests)} ({req.label})")
        step = self.script.pop(0)
        out = step(req) if callable(step) else step
        if isinstance(out, Exception):
            raise out
        return out

    def request_text(self) -> str:
        """Everything that was ever sent to the model, as one string."""
        return "\n".join(json.dumps(r.api_kwargs(), ensure_ascii=False) for r in self.requests)

    def labels(self) -> list[str]:
        return [r.label for r in self.requests]
