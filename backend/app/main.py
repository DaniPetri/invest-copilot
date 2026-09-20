import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from .config import REPO_ROOT, get_settings

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
