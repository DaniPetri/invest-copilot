from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

# EUR per million tokens: (input, output). PLACEHOLDER values, editable: verify against the
# current pricing page at platform.claude.com before relying on cost figures (planned for M6).
PRICE_TABLE_EUR_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (0.9, 4.5),
    "claude-sonnet-5": (2.7, 13.5),
    "claude-opus-5": (4.5, 22.5),
}


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
