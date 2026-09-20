"""Record the LLM responses behind the 8 demo questions (scripts/demo_questions.yaml) as cassettes.

    uv run --project backend python scripts/record_demo.py [--refresh] [--only p1,a1]

Runs every question through the real POST /api/chat (in process, LLM_MODE=record) with the live Anthropic API and
writes fixtures/cassettes/<hash>.jsonl. Recording is idempotent: a request that already has a cassette is served
from it and costs nothing (`--refresh` re-records). Needs ANTHROPIC_API_KEY. After recording, every answer is checked
against the expectations in the YAML, so a recording that does not show what the demo needs is reported, not kept
quietly. Exit 0 = all recorded and passing, 1 = an expectation failed, 2 = no key / no data.
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["LLM_MODE"] = "record"  # before the settings are read
sys.path[:0] = [str(ROOT / "backend"), str(Path(__file__).parent)]

from app.config import get_settings  # noqa: E402
from smoke_demo import check, load_questions, load_ui_matrix, parse_sse, summary  # noqa: E402


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--refresh", action="store_true", help="re-record even when a cassette exists (spends money)")
    ap.add_argument("--only", default="", help="comma-separated question ids (UI ones look like u_august/anna)")
    ap.add_argument("--no-ui", action="store_true", help="skip the one-click UI questions x all personas")
    ap.add_argument("--max-cost-eur", type=float, default=2.0, help="stop when the answers' shown cost adds up to this")
    args = ap.parse_args(argv)
    if args.refresh:
        os.environ["RECORD_REFRESH"] = "1"

    settings = get_settings()
    if not settings.has_api_key:
        print("No ANTHROPIC_API_KEY: recording needs the live API (set it in .env).", file=sys.stderr)
        return 2
    if not (settings.data_dir / "manifest.json").exists():
        print("No universe: run `make data && make ingest` first.", file=sys.stderr)
        return 2

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from app.main import app  # noqa: PLC0415

    wanted = {x for x in args.only.split(",") if x}
    questions = load_questions() + ([] if args.no_ui else load_ui_matrix())
    questions = [q for q in questions if not wanted or q["id"] in wanted]
    cassettes = lambda: {p.name for p in settings.cassette_dir.glob("*.jsonl")}  # noqa: E731
    before = cassettes()
    failed = 0
    spent = 0.0
    with TestClient(app) as client:
        for q in questions:
            if spent > args.max_cost_eur:
                print(f"stopping: {spent:.2f} EUR shown so far exceeds --max-cost-eur {args.max_cost_eur}", file=sys.stderr)
                return 1
            with client.stream("POST", "/api/chat", json={"customer_id": q["customer_id"], "message": q["message"]}) as res:
                events = parse_sse(res.iter_lines())
            problems = check(q, events, "record")
            spent += next((d["cost_eur"] for e, d in events if e == "done"), 0.0)
            failed += bool(problems)
            print(f"{'ok  ' if not problems else 'FAIL'} {q['id']:<3} {q['customer_id']:<7} {summary(events)}")
            print(f"       {q['message']}")
            for p in problems:
                print(f"       - {p}")
    new = cassettes() - before
    print(f"\n{len(questions)} questions, {len(new)} new cassettes in {settings.cassette_dir.relative_to(ROOT)}, "
          f"cost shown by the answers {spent:.4f} EUR (includes the price of cassettes that were reused)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
