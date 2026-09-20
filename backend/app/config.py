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
