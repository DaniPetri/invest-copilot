# ruff: noqa: E501
"""Build the frontend fixtures from the real universe and the real tools (no hand-typed numbers).

    cd backend && uv run python ../scripts/build_frontend_fixtures.py     # needs `make data` and `make ingest`

Writes frontend/fixtures/api/{customers,products,portfolios,tools,evals}.json and the two SSE streams
frontend/fixtures/sse/{simulate,roentgen}.jsonl (the other three streams were written in M1 and refreshed with
real numbers). Keys in tools.json are built exactly like `toolKey` in frontend/src/lib/fixtures.ts.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from app.config import get_settings  # noqa: E402
from app.data.store import Store  # noqa: E402
from app.fmt import de_num, de_pct  # noqa: E402
from app.portfolio_view import build_portfolio_view, event_window  # noqa: E402
from app.evals_view import build_eval_report  # noqa: E402
from app.schemas.products import MarketEvent  # noqa: E402
from app.schemas.ui import UIBlockAdapter  # noqa: E402
from app.tools.base import ToolContext  # noqa: E402
from app.tools.registry import execute  # noqa: E402

API_DIR = REPO / "frontend" / "fixtures" / "api"
SSE_DIR = REPO / "frontend" / "fixtures" / "sse"
RATES, YEARS = [25, 50, 100, 250], [5, 10, 20, 30]
MIXES = {  # keep in sync with frontend/src/lib/mixes.ts (a frontend test compares them)
    "vorsichtig": {"P36": 0.4, "P33": 0.3, "P03": 0.3},
    "ausgewogen": {"P03": 0.6, "P33": 0.4},
    "dynamisch": {"P03": 0.7, "P22": 0.3},
}
CHECKS_OK = [
    {"name": "pii", "status": "pass", "detail": "Keine IBAN, E-Mail oder Telefonnummer erkannt."},
    {"name": "quarantine", "status": "pass", "detail": "Keine verdächtigen Textabschnitte im Kontext."},
    {"name": "citations", "status": "pass", "detail": "Alle Quellenverweise stammen aus dieser Anfrage."},
    {
        "name": "numeric_grounding",
        "status": "pass",
        "detail": "Alle Zahlen stammen aus Werkzeugergebnissen oder Quellen.",
    },
    {"name": "advice_language", "status": "pass", "detail": "Keine Empfehlungssprache gefunden."},
    {"name": "ai_label", "status": "pass", "detail": "KI-Kennzeichnung vorhanden."},
]


def dump(path: Path, obj, indent: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {path.relative_to(REPO)}  ({path.stat().st_size / 1024:.0f} KB)")


def run(ctx: ToolContext, name: str, args: dict) -> dict:
    return execute(name, args, ctx).model_dump(mode="json")


def weights_arg(mix: dict[str, float]) -> list[dict]:
    return [{"product_id": p, "weight": w} for p, w in mix.items()]


# ── API fixtures ────────────────────────────────────────────────────────────


def build_tools(ctx: ToolContext, portfolios: dict) -> dict:
    tools: dict[str, dict] = {}
    for c in ctx.store.customers:
        tools[f"lookthrough|{c.id}"] = run(ctx, "portfolio_lookthrough", {"customer_id": c.id})
        for marker in portfolios[c.id]["events"]:
            start, end = event_window(MarketEvent.model_validate(marker["event"]))
            tools[f"explain|{c.id}|{start}|{end}"] = run(
                ctx, "explain_move", {"customer_id": c.id, "start": str(start), "end": str(end)}
            )
        for p in ctx.store.products:
            tools[f"suitability|{c.id}|{p.id}"] = run(
                ctx, "suitability_check", {"customer_id": c.id, "product_id": p.id}
            )
    for mix_name, mix in MIXES.items():
        for rate in RATES:
            for years in YEARS:
                args = {
                    "monthly_eur": rate,
                    "years": years,
                    "product_ids": None,
                    "weights": weights_arg(mix),
                    "fee_per_execution": 1.0,
                }
                tools[f"simulate|{rate}|{years}|{mix_name}"] = {
                    **run(ctx, "simulate_savings_plan", args),
                    "request": args,
                }
    for p in ctx.store.products:
        for rate in RATES:
            tools[f"cost|{p.id}|{rate}|10"] = run(
                ctx, "cost_projection", {"product_id": p.id, "monthly_eur": rate, "years": 10}
            )
    return tools


def build_evals() -> dict:
    """The measured eval report (evals/reports), through the same adapter as GET /api/evals/latest. Only `mode`
    differs, so fixture mode shows the real numbers and says it is a copy."""
    report = build_eval_report(REPO / "evals" / "reports").model_dump(mode="json")
    report["mode"] = "fixture"
    return report



# ── SSE fixtures built from real tool output ────────────────────────────────


def text_deltas(text: str, first: int = 600, step: int = 45) -> list[tuple[str, dict, int]]:
    chunks, cur = [], ""
    for w in text.split(" "):
        cur += w + " "
        if len(cur) > 28:
            chunks.append(cur)
            cur = ""
    if cur:
        chunks.append(cur)
    chunks[-1] = chunks[-1].rstrip()
    return [("text_delta", {"text": c}, first if i == 0 else step) for i, c in enumerate(chunks)]


def write_stream(name: str, events: list[tuple[str, dict, int]]) -> None:
    lines = [json.dumps({"event": e, "data": d, "delay_ms": ms}, ensure_ascii=False) for e, d, ms in events]
    path = SSE_DIR / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(REPO)}  ({len(lines)} events)")


def flags(**kw):
    return {"advice_request": False, "injection_suspected": False, "pii_present": False, **kw}


def build_simulate_stream(ctx: ToolContext) -> None:
    args = {"monthly_eur": 50, "years": 20, "product_ids": ["P03"], "weights": None, "fee_per_execution": 1.0}
    sim = execute("simulate_savings_plan", args, ctx)
    cost = execute("cost_projection", {"product_id": "P03", "monthly_eur": 50, "years": 20}, ctx)
    suit = execute("suitability_check", {"customer_id": "anna", "product_id": "P03"}, ctx)
    query = "Risikoindikator und laufende Kosten Welt ETF"
    search = execute("search_kid", {"query": query, "product_ids": ["P03"], "k": 2}, ctx)
    s, c = sim.payload, cost.payload
    p03 = ctx.product("P03")
    risk_chunk = next(ch for ch in search.payload["chunks"] if ch["section"] == "Risikoindikator")
    text = (
        f"Bei 50 € im Monat zahlst du in 20 Jahren {de_num(s['total_contributions'])} € ein. "
        f"In der Simulation liegt der mittlere Verlauf bei {de_num(s['p50'][-1])} €, "
        f"in den schwächsten 5 % der Verläufe unter {de_num(s['p5'][-1])} €. "
        f"Die Kosten betragen {de_num(c['total_eur'], 2)} € ({de_pct(c['total_pct_of_contributions'] / 100, 1)} deiner Einzahlungen). "
        f"Der Welt ETF hat Risikostufe {p03.sri} von 7 [[cite:{risk_chunk['id']}]]."
    )
    citations = [
        {
            "chunk_id": ch["id"],
            "product_name": p03.name,
            "page": ch["page"],
            "section": ch["section"],
            "snippet": ch["text"].replace("\n", " ")[:140],
        }
        for ch in search.payload["chunks"]
    ]
    blocks = [
        {"type": "text", "markdown": text, "citations": [risk_chunk["id"]]},
        {"type": "fan_chart", **{k: s[k] for k in ("years", "p5", "p25", "p50", "p75", "p95", "contributions")}},
        {
            "type": "cost_breakdown",
            "rows": c["rows"],
            "total": c["total_eur"],
            "total_pct_of_contributions": c["total_pct_of_contributions"],
        },
        {"type": "risk_meter", "sri": p03.sri},
        {"type": "suitability", "verdict": suit.payload["verdict"], "reasons": suit.payload["reasons"]},
        {"type": "citations", "items": citations},
    ]
    for b in blocks:
        UIBlockAdapter.validate_python(b)
    events = [
        ("trace", {"trace_id": "tr_fixture_simulate", "started_at": "2026-09-20T09:22:30Z", "mode": "replay"}, 0),
        (
            "router",
            {
                "intent": "simulate",
                "flags": flags(),
                "confidence": 0.95,
                "model": "claude-haiku-4-5-20251001",
                "latency_ms": 402,
            },
            380,
        ),
        ("tool_start", {"call_id": "c1", "name": "simulate_savings_plan", "args": args}, 700),
        (
            "tool_end",
            {
                "call_id": "c1",
                "name": "simulate_savings_plan",
                "ok": True,
                "duration_ms": 61,
                "result_id": "r1",
                "summary": sim.summary,
            },
            90,
        ),
        (
            "tool_start",
            {
                "call_id": "c2",
                "name": "cost_projection",
                "args": {"product_id": "P03", "monthly_eur": 50, "years": 20, "fee_per_execution": 1.0},
            },
            320,
        ),
        (
            "tool_end",
            {
                "call_id": "c2",
                "name": "cost_projection",
                "ok": True,
                "duration_ms": 2,
                "result_id": "r2",
                "summary": cost.summary,
            },
            40,
        ),
        (
            "tool_start",
            {"call_id": "c3", "name": "suitability_check", "args": {"customer_id": "anna", "product_id": "P03"}},
            280,
        ),
        (
            "tool_end",
            {
                "call_id": "c3",
                "name": "suitability_check",
                "ok": True,
                "duration_ms": 1,
                "result_id": "r3",
                "summary": suit.summary,
            },
            30,
        ),
        (
            "tool_start",
            {"call_id": "c4", "name": "search_kid", "args": {"query": query, "product_ids": ["P03"], "k": 2}},
            260,
        ),
        (
            "retrieval",
            {
                "query": query,
                "mode": "hybrid",
                "chunks": [
                    {
                        "id": ch["id"],
                        "product_id": ch["product_id"],
                        "page": ch["page"],
                        "section": ch["section"],
                        "score": round(ch["score"], 4),
                        "flags": ch["flags"],
                    }
                    for ch in search.payload["chunks"]
                ],
            },
            190,
        ),
        (
            "tool_end",
            {
                "call_id": "c4",
                "name": "search_kid",
                "ok": True,
                "duration_ms": 196,
                "result_id": "r4",
                "summary": search.summary,
            },
            10,
        ),
        *text_deltas(text),
        ("ui", {"blocks": blocks}, 200),
        ("guardrail", {"checks": CHECKS_OK}, 90),
        (
            "usage",
            {"model": "claude-haiku-4-5-20251001", "input_tokens": 405, "output_tokens": 92, "cost_eur": 0.0008},
            5,
        ),
        ("usage", {"model": "claude-sonnet-5", "input_tokens": 5120, "output_tokens": 830, "cost_eur": 0.0241}, 5),
        ("done", {"trace_id": "tr_fixture_simulate", "total_ms": 5320, "cost_eur": 0.0249}, 10),
    ]
    write_stream("simulate.jsonl", events)


def build_roentgen_stream(ctx: ToolContext) -> None:
    look = execute("portfolio_lookthrough", {"customer_id": "markus"}, ctx)
    p = look.payload
    names = {
        pr["product_id"]: pr["name"]
        for pr in [
            {"product_id": x.product_id, "name": ctx.product(x.product_id).name}
            for x in ctx.customer("markus").positions
        ]
    }
    ids = sorted(names)
    pair = {(o["product_a"], o["product_b"]): o["overlap"] for o in p["overlaps"]}
    matrix = [[1.0 if a == b else pair.get((a, b), pair.get((b, a), 0.0)) for b in ids] for a in ids]
    top = p["by_company"][0]
    text = (
        f"Dein Depot besteht aus {p['n_products']} Produkten mit zusammen {p['n_companies']} Positionen. "
        f"Die zehn größten machen {de_pct(p['top10_share'], 1)} aus, die größte allein {de_pct(top['weight'], 1)}. "
        "Das ist keine Empfehlung, nur ein Blick hinein."
    )
    blocks = [
        {"type": "text", "markdown": text, "citations": []},
        {"type": "exposure_bars", "dimension": "sector", "rows": p["by_sector"][:6]},
        {"type": "exposure_bars", "dimension": "country", "rows": p["by_country"][:6]},
        {
            "type": "overlap_matrix",
            "products": [{"product_id": i, "name": names[i]} for i in ids],
            "matrix": [[round(v, 4) for v in row] for row in matrix],
        },
    ]
    for b in blocks:
        UIBlockAdapter.validate_python(b)
    events = [
        ("trace", {"trace_id": "tr_fixture_roentgen", "started_at": "2026-09-20T09:25:10Z", "mode": "replay"}, 0),
        (
            "router",
            {
                "intent": "portfolio_insight",
                "flags": flags(),
                "confidence": 0.93,
                "model": "claude-haiku-4-5-20251001",
                "latency_ms": 371,
            },
            350,
        ),
        ("tool_start", {"call_id": "c1", "name": "portfolio_lookthrough", "args": {"customer_id": "markus"}}, 620),
        (
            "tool_end",
            {
                "call_id": "c1",
                "name": "portfolio_lookthrough",
                "ok": True,
                "duration_ms": 92,
                "result_id": "r1",
                "summary": look.summary,
            },
            100,
        ),
        *text_deltas(text, first=520),
        ("ui", {"blocks": blocks}, 170),
        ("guardrail", {"checks": CHECKS_OK}, 90),
        (
            "usage",
            {"model": "claude-haiku-4-5-20251001", "input_tokens": 372, "output_tokens": 74, "cost_eur": 0.0007},
            5,
        ),
        ("usage", {"model": "claude-sonnet-5", "input_tokens": 3480, "output_tokens": 690, "cost_eur": 0.0167}, 5),
        ("done", {"trace_id": "tr_fixture_roentgen", "total_ms": 3110, "cost_eur": 0.0174}, 10),
    ]
    write_stream("roentgen.jsonl", events)


def main() -> None:
    store = Store(get_settings().data_dir)
    ctx = ToolContext(store)
    dump(API_DIR / "customers.json", [c.model_dump(mode="json") for c in store.customers])
    products = []
    for p in store.products:
        d = p.model_dump(mode="json")
        d["holdings"] = sorted(d["holdings"], key=lambda h: -h["weight"])[:10]  # top 10 keeps the fixture small
        products.append(d)
    dump(API_DIR / "products.json", products)
    portfolios = {c.id: build_portfolio_view(store, c.id).model_dump(mode="json") for c in store.customers}
    dump(API_DIR / "portfolios.json", portfolios)
    dump(API_DIR / "tools.json", build_tools(ctx, portfolios))
    dump(API_DIR / "evals.json", build_evals(), indent=1)
    from app.rag.search import close_all_clients  # noqa: PLC0415

    ctx_index = ToolContext(store)
    build_simulate_stream(ctx_index)
    build_roentgen_stream(ctx_index)
    close_all_clients()


if __name__ == "__main__":
    main()
