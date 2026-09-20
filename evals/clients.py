"""LLM client for the eval runner.

    replay  cassettes only. No key, no network, no cost. A missing cassette raises `CassetteMiss`.
    live    cache-through: an existing cassette is served, a missing one is fetched from the API and written to
            `fixtures/cassettes/`. So a live run records what it needs, a re-run is free, an interrupted run keeps
            what it already paid for, and `--refresh` (RECORD_REFRESH=1) forces new answers.

Live calls go through a `BudgetClient` that counts spend from the price table and refuses the next call once the cap
(`--max-cost-eur`) is reached, so a run can never spend more than the cap by more than one call.
"""

import sys
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / "backend")]

from app.agent.llm import (  # noqa: E402
    AnthropicClient,
    LLMClient,
    LLMRequest,
    LLMResponse,
    RecordingClient,
    ReplayClient,
)
from app.config import Settings, cost_eur  # noqa: E402


class BudgetExceededError(Exception):
    """The live-spend cap was reached; the run stops and reports what it has."""


class BudgetClient:
    mode: Literal["live", "record", "replay"] = "live"

    def __init__(self, inner: LLMClient, max_eur: float):
        self.inner = inner
        self.max_eur = max_eur
        self.spent_eur = 0.0
        self.calls = 0
        self.by_label: dict[str, dict[str, float]] = {}

    async def complete(self, req: LLMRequest) -> LLMResponse:
        if self.spent_eur >= self.max_eur:
            raise BudgetExceededError(
                f"Live spend cap reached: {self.spent_eur:.3f} EUR of {self.max_eur:.3f} EUR (--max-cost-eur)."
            )
        resp = await self.inner.complete(req)
        cost = cost_eur(req.model, resp.input_tokens, resp.output_tokens)
        self.spent_eur += cost
        self.calls += 1
        row = self.by_label.setdefault(req.label or "?", {"calls": 0, "eur": 0.0})
        row["calls"] += 1
        row["eur"] += cost
        return resp


def make_eval_client(
    mode: Literal["live", "replay"], settings: Settings, max_eur: float, refresh: bool = False
) -> tuple[LLMClient, BudgetClient | None]:
    """The client for a run and, in live mode, the meter that reports what was actually spent."""
    if mode == "replay":
        return ReplayClient(settings.cassette_dir), None
    if not settings.has_api_key:
        raise SystemExit("--mode live needs ANTHROPIC_API_KEY (set it in .env). Use --mode replay without a key.")
    assert settings.anthropic_api_key is not None
    meter = BudgetClient(AnthropicClient(settings.anthropic_api_key.get_secret_value()), max_eur)
    return RecordingClient(meter, settings.cassette_dir, refresh=refresh or settings.record_refresh), meter
