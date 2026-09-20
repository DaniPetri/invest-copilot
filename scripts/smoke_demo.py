"""Smoke test for the 8 demo questions (scripts/demo_questions.yaml) against a running API.

    uv run --project backend python scripts/smoke_demo.py [--base http://localhost:8000] [--mode replay]

Sends every question to POST /api/chat, reads the SSE stream and checks the expectations in the YAML. Exit 0 when all
questions pass, 1 otherwise. `--mode` is the LLM mode the server must report (default replay: recorded cassettes, no
API key, zero live calls); a trace in any other mode fails the run, so this is also the proof that nothing was live.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml  # PyYAML comes with uvicorn[standard]

QUESTIONS = Path(__file__).with_name("demo_questions.yaml")
Event = tuple[str, dict[str, Any]]


def load_questions() -> list[dict[str, Any]]:
    return yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]


PERSONAS = ("anna", "markus", "elif")


def load_ui_matrix() -> list[dict[str, Any]]:
    """Every one-click UI question (`ui_prompts`) as every persona: the cassette is persona-specific (the system
    prompt names the customer), and the UI sends the question with whichever persona is selected."""
    prompts = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["ui_prompts"]
    return [{**p, "id": f"{p['id']}/{c}", "customer_id": c, "category": "ui"} for p in prompts for c in PERSONAS]


def parse_sse(lines) -> list[Event]:
    """`event:` / `data:` lines to (event, data) pairs; comments and pings are skipped."""
    events: list[Event] = []
    name, data = "message", []
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line:
            if data:
                events.append((name, json.loads("\n".join(data))))
            name, data = "message", []
        elif line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
    if data:
        events.append((name, json.loads("\n".join(data))))
    return events


def ask(base: str, customer_id: str, message: str, timeout: float = 120) -> list[Event]:
    req = urllib.request.Request(
        f"{base}/api/chat",
        data=json.dumps({"customer_id": customer_id, "message": message}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310  (a URL we were given)
        return parse_sse(line.decode("utf-8") for line in res)


def _texts(events: list[Event]) -> tuple[str, list[dict]]:
    """The visible answer (streamed deltas) and the hydrated blocks of the last `ui` event."""
    text = "".join(d["text"] for e, d in events if e == "text_delta")
    blocks = next((d["blocks"] for e, d in reversed(events) if e == "ui"), [])
    return text, blocks


def check(question: dict[str, Any], events: list[Event], mode: str | None) -> list[str]:
    """Problems found in one answer; an empty list means it passes."""
    exp = question["expect"]
    problems: list[str] = []
    names = [e for e, _ in events]
    if names[-1:] != ["done"]:
        problems.append(f"stream does not end with `done` (last: {names[-1:] or 'nothing'})")
    problems += [f"error event: {d.get('code')}: {d.get('message')}" for e, d in events if e == "error"]
    trace = next((d for e, d in events if e == "trace"), None)
    if mode and (trace is None or trace["mode"] != mode):
        problems.append(f"trace mode is {trace and trace['mode']!r}, expected {mode!r}")

    router = next((d for e, d in events if e == "router"), {})
    if "intent" in exp and router.get("intent") != exp["intent"]:
        problems.append(f"intent {router.get('intent')!r}, expected {exp['intent']!r}")

    called = [d["name"] for e, d in events if e == "tool_start"]
    for tool in exp.get("tools", []):
        if tool not in called:
            problems.append(f"tool {tool} was not called (called: {called})")
    if exp.get("tools") == [] and called:
        problems.append(f"no tool expected, but called {called}")

    text, blocks = _texts(events)
    types = [b["type"] for b in blocks]
    for t in exp.get("blocks", []):
        if t not in types:
            problems.append(f"block {t} missing (blocks: {types})")
    if not any(b["type"] == "text" for b in blocks) and not text.strip():
        problems.append("no answer text")

    if exp.get("cited") and not any(b.get("citations") for b in blocks if b["type"] == "text"):
        problems.append("no source chip on the answer text")
    visible = text + json.dumps(blocks, ensure_ascii=False)
    problems += [f"answer does not mention {s!r}" for s in exp.get("mentions", []) if s not in visible]

    if exp.get("quarantined"):
        held = any("quarantined" in (c.get("flags") or []) for e, d in events if e == "retrieval" for c in d["chunks"])
        held = held or any(d["name"] == "quarantine" and d["status"] != "pass" for e, dd in events if e == "guardrail" for d in dd["checks"])
        if not held:
            problems.append("no chunk was quarantined")

    raw = json.dumps([d for _, d in events], ensure_ascii=False)
    problems += [f"{s!r} appears in the stream" for s in exp.get("never", []) if re.search(re.escape(s), raw, re.I)]

    for e, d in events:
        if e == "guardrail":
            problems += [f"guardrail {c['name']} = {c['status']}: {c['detail']}" for c in d["checks"] if c["status"] == "fail"]
            problems += [f"guardrail {c['name']} fired ({c['status']})" for c in d["checks"] if c["name"] in ("fallback", "repair")]
    return problems


def summary(events: list[Event]) -> str:
    router = next((d for e, d in events if e == "router"), {})
    tools = ",".join(d["name"] for e, d in events if e == "tool_start") or "-"
    _, blocks = _texts(events)
    done = next((d for e, d in events if e == "done"), {})
    return (
        f"{router.get('intent', '?'):<18} tools={tools:<28} blocks={','.join(b['type'] for b in blocks) or '-':<34} "
        f"{done.get('total_ms', 0) / 1000:5.1f}s {done.get('cost_eur', 0):.4f} EUR"
    )


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):  # German text and € on a Windows console
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--mode", default="replay", help="LLM mode every trace must report; '' disables the check")
    ap.add_argument("--ui", action="store_true", help="run every one-click UI question as every persona instead")
    args = ap.parse_args(argv)

    try:
        with urllib.request.urlopen(f"{args.base}/api/health", timeout=10) as res:  # noqa: S310
            health = json.load(res)
    except (urllib.error.URLError, OSError) as e:
        print(f"API not reachable at {args.base}: {e}\nStart it with: uv run python scripts/tasks.py dev", file=sys.stderr)
        return 1
    print(f"API {args.base}: llm_mode={health['llm_mode']} has_api_key={health['has_api_key']}")

    failed = 0
    questions = load_ui_matrix() if args.ui else load_questions()
    for q in questions:
        t0 = time.perf_counter()
        try:
            events = ask(args.base, q["customer_id"], q["message"])
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            events, problems = [], [f"request failed: {e}"]
        else:
            problems = check(q, events, args.mode or None)
        status = "PASS" if not problems else "FAIL"
        failed += bool(problems)
        print(f"{status} {q['id']:<3} {q['customer_id']:<7} {summary(events) if events else ''}  ({time.perf_counter() - t0:.1f}s wall)")
        print(f"       {q['message']}")
        for p in problems:
            print(f"       - {p}")
    total = len(questions)
    what = "UI question x persona combinations" if args.ui else "demo questions"
    print(f"\n{total - failed}/{total} {what} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
