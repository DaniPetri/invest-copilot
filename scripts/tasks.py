"""Task runner. The Makefile only calls this, so it works the same on Windows without make.

    uv run python scripts/tasks.py <target>

Standard library only.
"""

import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def run(cmd: list[str], cwd: Path = ROOT) -> int:
    print(f"$ {' '.join(cmd)}   (in {cwd.relative_to(ROOT) if cwd != ROOT else '.'})", flush=True)
    return subprocess.call(cmd, cwd=cwd)


def npm(*args: str) -> list[str]:
    exe = shutil.which("npm")
    if not exe:
        sys.exit("npm not found on PATH (install Node.js LTS)")
    return [exe, *args]


def first_failure(*codes: int) -> int:
    return next((c for c in codes if c), 0)


def setup() -> int:
    return first_failure(run(["uv", "sync"], BACKEND), run(npm("install"), FRONTEND))


def test() -> int:
    """Run both suites even if the first fails, so one run shows every failure."""
    return first_failure(
        run(["uv", "run", "pytest", "-q"], BACKEND),
        run(npm("test", "--", "--run"), FRONTEND),
    )


def contracts() -> int:
    return run(["uv", "run", "python", "-m", "app.schemas.export"], BACKEND)


def data() -> int:
    """Generate the synthetic universe into data/generated/ (seed 20260920)."""
    return run(["uv", "run", "python", "-m", "app.data.generate"], BACKEND)


def ingest() -> int:
    """Parse the KID PDFs and build the Qdrant (dense) and BM25 (lexical) indexes in data/generated/."""
    return run(["uv", "run", "python", "-m", "app.rag.index"], BACKEND)


def fixtures() -> int:
    """Rebuild frontend/fixtures/api and the simulate/roentgen SSE streams from the real tools (needs data + ingest)."""
    return run(["uv", "run", "python", "../scripts/build_frontend_fixtures.py"], BACKEND)


def eval_all() -> int:
    """All five suites in replay mode (recorded LLM responses, no key). Live: `python -m evals.run --mode live`."""
    return run(["uv", "run", "--project", "backend", "python", "-m", "evals.run", "--suite", "all", "--mode", "replay"])


def eval_ci() -> int:
    """SPEC §11: retrieval (no LLM) + router + redteam in replay mode; exits 1 when a gate fails."""
    generated = ROOT / "data" / "generated"
    if not (generated / "bm25.pkl").is_file():  # the retrieval suite needs the universe and its index
        if code := first_failure(0 if (generated / "products.json").is_file() else data(), ingest()):
            return code
    return run(["uv", "run", "--project", "backend", "python", "-m", "evals.run", "--suite", "ci", "--mode", "replay"])


def record() -> int:
    """SPEC §12: record the LLM responses of the 8 demo questions and of the eval sets as cassettes (needs a key).

    Recording is idempotent, so requests that already have a cassette cost nothing. The eval suites run live and
    cache-through: exit 1 there means a gate failed (documented, see PROGRESS.md), only other codes are errors."""
    if code := run(["uv", "run", "--project", "backend", "python", "scripts/record_demo.py"]):
        return code
    code = run(
        ["uv", "run", "--project", "backend", "python", "-m", "evals.run", "--suite", "all", "--mode", "live",
         "--max-cost-eur", "1.0"]
    )
    return 0 if code in (0, 1) else code


def api_dev_command() -> list[str]:
    """uvicorn with auto-reload, run from backend/. `--reload-dir app` limits the watcher to the source: by default
    it watches all of backend/, .venv included, and installed packages (.pyc writes, first imports) then restart
    the server in a loop at startup."""
    return ["uv", "run", "uvicorn", "app.main:app", "--reload", "--reload-dir", "app", "--port", "8000"]


def dev() -> int:
    """API on :8000 and web on :5173 together; Ctrl-C stops both."""
    procs = [
        subprocess.Popen(api_dev_command(), cwd=BACKEND),
        subprocess.Popen(npm("run", "dev"), cwd=FRONTEND),
    ]
    print("API http://localhost:8000/api/health · Web http://localhost:5173", flush=True)
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


TARGETS: dict[str, Callable[[], int]] = {
    "setup": setup,
    "data": data,
    "ingest": ingest,
    "dev": dev,
    "test": test,
    "eval": eval_all,
    "eval-ci": eval_ci,
    "contracts": contracts,
    "fixtures": fixtures,
    "record": record,
}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in TARGETS:
        print(f"usage: tasks.py <{'|'.join(TARGETS)}>", file=sys.stderr)
        return 1
    return TARGETS[argv[1]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
