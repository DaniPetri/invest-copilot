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


def dev() -> int:
    """API on :8000 and web on :5173 together; Ctrl-C stops both."""
    procs = [
        subprocess.Popen(
            ["uv", "run", "uvicorn", "app.main:app", "--reload", "--port", "8000"], cwd=BACKEND
        ),
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


def not_yet(name: str, milestone: str) -> Callable[[], int]:
    def _run() -> int:
        print(f"'{name}' is not implemented yet (arrives in {milestone}).", file=sys.stderr)
        return 2

    return _run


TARGETS: dict[str, Callable[[], int]] = {
    "setup": setup,
    "data": data,
    "ingest": ingest,
    "dev": dev,
    "test": test,
    "eval": not_yet("eval", "M7"),
    "eval-ci": not_yet("eval-ci", "M7"),
    "contracts": contracts,
    "record": not_yet("record", "M8"),
}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in TARGETS:
        print(f"usage: tasks.py <{'|'.join(TARGETS)}>", file=sys.stderr)
        return 1
    return TARGETS[argv[1]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
