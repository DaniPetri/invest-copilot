import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from .config import REPO_ROOT, get_settings
from .data.store import DataMissingError, get_store
from .rag.search import IndexMissingError
from .schemas.tools import ToolResult
from .tools.base import ToolContext, ToolError
from .tools.registry import execute

FIXTURE_DIR = REPO_ROOT / "frontend" / "fixtures" / "sse"

app = FastAPI(title="Invest Copilot", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str | bool]:
    settings = get_settings()
    return {
        "status": "ok",
        "version": app.version,
        "llm_mode": settings.effective_llm_mode,
        "has_api_key": settings.has_api_key,
    }


async def _replay(path: Path, fast: bool) -> AsyncIterator[dict[str, str]]:
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        line = json.loads(raw)
        if not fast:
            await asyncio.sleep(line.get("delay_ms", 0) / 1000)
        yield {"event": line["event"], "data": json.dumps(line["data"], ensure_ascii=False)}


@app.get("/api/_debug/sse/{name}")
def debug_sse(name: str, fast: bool = False) -> EventSourceResponse:
    """Dev aid: stream a recorded fixture over real SSE, to check parsing and buffering end to end.

    Replaced by POST /api/chat in M6; `curl -N localhost:8000/api/_debug/sse/discover`.
    """
    path = FIXTURE_DIR / f"{name}.jsonl"
    if not path.is_file() or path.parent != FIXTURE_DIR:
        raise HTTPException(status_code=404, detail="unknown fixture")
    return EventSourceResponse(_replay(path, fast))


def get_tool_context() -> ToolContext:
    return ToolContext(get_store())


@app.post("/api/tools/{name}")
def run_tool(
    name: str,
    body: Annotated[dict[str, Any], Body()],
    ctx: Annotated[ToolContext, Depends(get_tool_context)],
) -> ToolResult:
    """Run a deterministic tool without the LLM (SPEC §7): instant screens such as the simulator use this.

    Each call has its own request-scoped result store, so `result_id` is always `r1`."""
    try:
        return execute(name, body, ctx)
    except ToolError as e:
        raise HTTPException(status_code=404 if e.code == "not_found" else 422, detail=e.message) from None
    except (DataMissingError, IndexMissingError) as e:
        raise HTTPException(status_code=503, detail=str(e)) from None
