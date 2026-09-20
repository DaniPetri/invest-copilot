"""Eval runner (SPEC §11).

    uv run --project backend python -m evals.run --suite all|ci|router|retrieval|answers|redteam|calibration
                                                 --mode live|replay [--only r55,a01] [--limit N]

Writes `evals/reports/<timestamp>.json`, `latest.json` and `latest.md`, and exits 1 when a gate in
`evals/thresholds.yaml` fails. Exit 2: the live-spend cap stopped the run.
`ci` = retrieval + router + redteam (what `make eval-ci` runs).

replay  reads recorded LLM responses from fixtures/cassettes/ (no key, no cost). A missing recording is an error.
live    same, but records what is missing from the API (needs ANTHROPIC_API_KEY); see evals/clients.py.
        Spend is capped by --max-cost-eur. `--only` / `--limit` run a subset: the report is written under its
        timestamp only (never as latest.*) and no gates are checked.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / "backend")]

import yaml  # noqa: E402  (PyYAML comes with uvicorn[standard])

from app.config import get_settings  # noqa: E402
from app.data.store import DataMissingError, Store  # noqa: E402
from app.tools.base import ToolContext  # noqa: E402
from evals import suites  # noqa: E402
from evals.clients import BudgetClient, BudgetExceededError, make_eval_client  # noqa: E402
from evals.report import render_markdown  # noqa: E402
from evals.suites import run_answers, run_calibration, run_redteam, run_retrieval, run_router  # noqa: E402

ALL_SUITES = ["retrieval", "router", "redteam", "answers", "calibration"]
CI_SUITES = [
    "retrieval",
    "router",
    "redteam",
]  # SPEC §11: `make eval-ci` = retrieval (no LLM) + router + redteam, replay
DEFAULT_THRESHOLDS = REPO_ROOT / "evals" / "thresholds.yaml"


def evaluate_gates(results: dict[str, dict], thresholds: dict[str, dict]) -> list[dict]:
    """One row per gate of every suite that ran. A metric that is missing or undefined (None / NaN) fails its gate,
    a suite that was stopped early fails `completed`, and every suite gets an implicit `errors <= 0` gate."""
    gates: list[dict] = []
    for name, result in results.items():
        wanted = {"errors": {"max": 0}, **thresholds.get(name, {})}
        for metric, bound in wanted.items():
            value = result["metrics"].get(metric)
            ok = isinstance(value, int | float) and value == value  # not None, not NaN
            if ok and "min" in bound:
                ok = value >= bound["min"]
            if ok and "max" in bound:
                ok = value <= bound["max"]
            gates.append(
                {
                    "suite": name,
                    "metric": metric,
                    "value": value,
                    "min": bound.get("min"),
                    "max": bound.get("max"),
                    "passed": bool(ok),
                }
            )
        if result.get("aborted"):
            gates.append(
                {"suite": name, "metric": "completed", "value": False, "min": None, "max": None, "passed": False}
            )
    return gates


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", default="all", choices=["all", "ci", *ALL_SUITES])
    ap.add_argument("--mode", default="replay", choices=["live", "replay"])
    ap.add_argument("--only", help="comma-separated item IDs (r55,a01,rt05,c03): run just these")
    ap.add_argument("--limit", type=int, help="first N items of each suite")
    ap.add_argument("--max-cost-eur", type=float, default=1.0, help="live spend cap for this run (default 1.0)")
    ap.add_argument("--refresh", action="store_true", help="live: ignore existing cassettes and call the API again")
    ap.add_argument("--no-judge", action="store_true", help="answers: deterministic checks only, no LLM judge")
    ap.add_argument("--rerank-every", type=int, help="retrieval: also measure hybrid_rerank on every N-th question")
    ap.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    ap.add_argument("--reports-dir", type=Path, default=suites.REPORTS)
    return ap.parse_args(argv)


async def run_suites(args: argparse.Namespace, names: list[str]) -> tuple[dict[str, dict], BudgetClient | None]:
    settings = get_settings()
    only = args.only.split(",") if args.only else None
    llm, meter = None, None
    if any(n != "retrieval" for n in names):
        llm, meter = make_eval_client(args.mode, settings, args.max_cost_eur, args.refresh)
    ctx = ToolContext(Store(settings.data_dir))
    agent = suites.make_agent(llm, settings, ctx) if llm else None
    results: dict[str, dict] = {}
    for name in names:
        try:
            if name == "retrieval":
                results[name] = run_retrieval(settings, args.rerank_every)
            elif name == "router":
                results[name] = await run_router(llm, settings, only, args.limit)
            elif name == "answers":
                results[name] = await run_answers(agent, llm, settings, only, args.limit, judge=not args.no_judge)
            elif name == "redteam":
                results[name] = await run_redteam(agent, only, args.limit)
            elif name == "calibration":
                results[name] = await run_calibration(llm, settings, only, args.limit)
        except BudgetExceededError as e:
            results[name] = {"metrics": {"errors": 0}, "n": 0, "aborted": str(e), "errors": [], "cost_eur": 0.0}
            break
        print(f"  {name}: {results[name]['n']} items", flush=True)
    return results, meter


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    args = parse_args(argv)
    if args.rerank_every:
        os.environ["RERANK"] = "1"
        get_settings.cache_clear()
    names = {"all": ALL_SUITES, "ci": CI_SUITES}.get(args.suite, [args.suite])
    if args.only or args.limit:
        names = [n for n in names if n != "retrieval"] or names  # retrieval has no items to subset
    partial = bool(args.only or args.limit)

    print(f"eval: {', '.join(names)} · mode {args.mode}" + (" · PARTIAL (no gates)" if partial else ""), flush=True)
    try:
        results, meter = asyncio.run(run_suites(args, names))
    except DataMissingError as e:
        print(f"{e}", file=sys.stderr)
        return 2

    thresholds = yaml.safe_load(args.thresholds.read_text(encoding="utf-8")) or {}
    gates = [] if partial else evaluate_gates(results, thresholds)
    now = datetime.now(UTC)
    report: dict[str, Any] = {
        "generated_at": now.isoformat(timespec="seconds"),
        "mode": args.mode,
        "partial": partial,
        "suites": results,
        "gates": gates,
        "passed": all(g["passed"] for g in gates),
        "recorded_cost_eur": sum(r.get("cost_eur", 0.0) for r in results.values()),
        "live": (
            {"spent_eur": meter.spent_eur, "calls": meter.calls, "by_label": meter.by_label, "cap_eur": meter.max_eur}
            if meter
            else None
        ),
    }
    out = args.reports_dir
    out.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    (out / f"{now.strftime('%Y%m%dT%H%M%SZ')}.json").write_text(blob, encoding="utf-8")
    markdown = render_markdown(report)
    if not partial:
        (out / "latest.json").write_text(blob, encoding="utf-8")
        (out / "latest.md").write_text(markdown, encoding="utf-8")
    print(markdown)

    if any(r.get("aborted") for r in results.values()):
        return 2
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
