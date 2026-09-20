"""Router (SPEC §8): a fast model classifies the message into a `RouterDecision` with structured output; a fixed
policy table then decides what happens next, in code, not in a prompt.

| intent / flag            | policy      | what happens                                                        |
|--------------------------|-------------|---------------------------------------------------------------------|
| advice_request (either)  | refuse      | no tools, no orchestrator call: refusal template + hand-off block   |
| out_of_scope             | redirect    | no tools, no orchestrator call: short redirect                      |
| everything else          | orchestrate | tool loop, then the strict render_ui step                           |

`injection_suspected` does not change the policy; it hardens the orchestrator prompt and is reported as a guardrail.
"""

import json
from typing import Literal

from pydantic import ValidationError

from ..config import Settings
from ..guardrails.advice import looks_like_advice_request
from ..schemas.events import RouterDecision, RouterFlags, RouterSlots
from ..tools.registry import strict_input_schema
from .llm import LLMClient, LLMError, LLMRequest, LLMResponse
from .prompts import ROUTER_SYSTEM

Policy = Literal["refuse", "redirect", "orchestrate"]


def policy(decision: RouterDecision) -> Policy:
    if decision.intent == "advice_request" or decision.flags.advice_request:
        return "refuse"
    if decision.intent == "out_of_scope":
        return "redirect"
    return "orchestrate"


def router_request(message: str, settings: Settings) -> LLMRequest:
    return LLMRequest(
        model=settings.router_model,
        system=ROUTER_SYSTEM,
        messages=[{"role": "user", "content": message}],
        max_tokens=400,
        output_config={"format": {"type": "json_schema", "schema": strict_input_schema(RouterDecision)}},
        label="router",
    )


async def route(llm: LLMClient, message: str, settings: Settings) -> tuple[RouterDecision, LLMResponse]:
    """Classify `message` (already PII-redacted). Raises LLMError when the model's output is not a valid decision."""
    resp = await llm.complete(router_request(message, settings))
    try:
        return RouterDecision.model_validate(json.loads(resp.text)), resp
    except (json.JSONDecodeError, ValidationError) as e:
        raise LLMError("router_invalid", f"Router returned an invalid decision: {e}") from e


def fallback_decision(message: str) -> RouterDecision:
    """Used only when the router model is unreachable: a conservative regex guess, so an advice request is still
    refused and everything else is treated as a product search."""
    advice = looks_like_advice_request(message)
    return RouterDecision(
        intent="advice_request" if advice else "discover",
        slots=RouterSlots(),
        flags=RouterFlags(advice_request=advice),
        confidence=0.0,
    )
