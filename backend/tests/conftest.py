from pathlib import Path

import pytest

from app.data.generate import generate
from app.data.store import Store
from app.rag.index import build_index
from app.rag.search import close_all_clients
from app.tools.base import ToolContext

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "frontend" / "fixtures" / "sse"
CONTRACT_DIR = REPO_ROOT / "contracts"


@pytest.fixture(scope="session")
def universe_root(tmp_path_factory) -> Path:
    """The synthetic universe (seed 20260920), built once per test session."""
    out = tmp_path_factory.mktemp("tools_universe") / "gen"
    generate(out)
    return out


@pytest.fixture(scope="session")
def data_store(universe_root) -> Store:
    return Store(universe_root)


@pytest.fixture(scope="session")
def ctx(data_store) -> ToolContext:
    """Tool context without a retrieval index (every tool except search_kid)."""
    return ToolContext(data_store)


@pytest.fixture(scope="session")
def indexed_ctx(universe_root):
    """Tool context whose universe also has the retrieval index (downloads the embedding model once)."""
    build_index(universe_root)
    yield ToolContext(Store(universe_root))
    close_all_clients()
