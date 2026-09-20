from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

# EUR per million tokens: (input, output). List prices in USD from platform.claude.com/docs/en/about-claude/pricing
# (checked 2026-09-20: Haiku 4.5 $1/$5, Sonnet 5 $2/$10, Opus 5 $5/$25) times an assumed USD->EUR rate. Editable.
USD_TO_EUR = 0.92
PRICE_TABLE_EUR_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (round(1 * USD_TO_EUR, 4), round(5 * USD_TO_EUR, 4)),
    "claude-sonnet-5": (round(2 * USD_TO_EUR, 4), round(10 * USD_TO_EUR, 4)),
    "claude-opus-5": (round(5 * USD_TO_EUR, 4), round(25 * USD_TO_EUR, 4)),
}

MAX_TOOL_ROUNDS = 6  # SPEC §8


def cost_eur(model: str, input_tokens: int, output_tokens: int) -> float:
    """Cost of one LLM call from the price table. Raises KeyError for a model without a price, so a mistyped
    MODEL override fails loudly in the tests instead of silently costing nothing."""
    price_in, price_out = PRICE_TABLE_EUR_PER_MTOK[model]
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    anthropic_api_key: SecretStr | None = None
    llm_mode: Literal["live", "record", "replay"] | None = None
    router_model: str = "claude-haiku-4-5-20251001"
    orchestrator_model: str = "claude-sonnet-5"
    judge_model: str = "claude-opus-5"
    rerank: bool = False
    embed_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    rerank_model: str = "jinaai/jina-reranker-v2-base-multilingual"
    # Outside data/generated (`make data` wipes it) and outside the repo: model files sit in deep folders, and a
    # long checkout path overflows Windows' 260-character limit. Override with MODEL_CACHE_DIR.
    model_cache_dir: Path = Path.home() / ".cache" / "invest-copilot" / "fastembed"
    data_dir: Path = REPO_ROOT / "data" / "generated"
    cassette_dir: Path = REPO_ROOT / "fixtures" / "cassettes"
    record_refresh: bool = False  # RECORD_REFRESH=1: `make record` overwrites existing cassettes
    # Outside data/generated so `make data` does not wipe the traces.
    trace_db: Path = REPO_ROOT / "data" / "traces.sqlite"
    # "flag": ungrounded numbers are reported in the trace. "fail": they trigger the repair round (NUMBERS_GUARD=fail).
    numbers_guard: Literal["flag", "fail"] = "flag"

    @property
    def has_api_key(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value().strip())

    @property
    def effective_llm_mode(self) -> Literal["live", "record", "replay"]:
        """Replay is the default when no API key is set, so reviewers can run without one."""
        if not self.has_api_key:
            return "replay"
        return self.llm_mode or "replay"


@lru_cache
def get_settings() -> Settings:
    return Settings()
