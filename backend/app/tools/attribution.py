"""explain_move: what moved a customer's portfolio between two dates, and which known events explain it (SPEC §7).

Per position: `pnl = units_end * NAV_end - units_start * NAV_start - money paid in during the window`, so savings-plan
purchases inside the window do not count as gains. Prices are the last close on or before each date.
`change_eur` is the sum of position P&L; `contribution_pct` is each P&L over the portfolio's start value, in
percentage points, so the contributions add up to `change_pct`.
Events are the ground-truth market events dated inside the window that touch the customer's holdings (a
market-wide event always does; a sector event when the portfolio has exposure to one of its sectors).
"""

from datetime import date

from ..fmt import de_num
from ..schemas.products import MarketEvent
from ..schemas.tools import AttributionRow, ExplainMoveInput, ExplainMoveOutput
from .base import ToolContext, ToolError
from .lookthrough import position_weights


def _sector_exposure(customer, ctx: ToolContext) -> dict[str, float]:
    exposure: dict[str, float] = {}
    for pid, pw in position_weights(customer, ctx).items():
        for h in ctx.product(pid).holdings:
            exposure[h.sector] = exposure.get(h.sector, 0.0) + pw * h.weight
    return exposure


def matched_events(customer, start: date, end: date, ctx: ToolContext) -> list[MarketEvent]:
    """Events inside [start, end] that touch the holdings, most relevant first (exposure x size of the shock)."""
    exposure = _sector_exposure(customer, ctx)
    scored = []
    for ev in ctx.store.events:
        if not start <= ev.date <= end:
            continue
        reach = 1.0 if not ev.sectors else sum(exposure.get(s, 0.0) for s in ev.sectors)
        if reach > 0:
            scored.append((reach * abs(ev.shock_pct), ev))
    scored.sort(key=lambda t: (-t[0], t[1].date))
    return [ev for _, ev in scored]


def explain_move(inp: ExplainMoveInput, ctx: ToolContext) -> ExplainMoveOutput:
    if inp.start >= inp.end:
        raise ToolError("invalid", f"start ({inp.start}) must be before end ({inp.end})")
    customer = ctx.customer(inp.customer_id)
    prices = ctx.store.prices
    try:
        i0 = prices.index_on_or_before(inp.start)
    except ValueError as e:
        raise ToolError("invalid", str(e)) from None
    i1 = prices.index_on_or_before(inp.end)
    if i1 <= i0:
        raise ToolError("invalid", "the window contains no trading day")

    rows: list[AttributionRow] = []
    start_total = end_total = pnl_total = 0.0
    products = sorted({t.product_id for t in customer.transactions} | {p.product_id for p in customer.positions})
    raw = []
    for pid in products:
        nav = prices.products[pid]
        txs = [t for t in customer.transactions if t.product_id == pid]
        units_start = sum(t.units for t in txs if t.date <= inp.start)
        units_end = sum(t.units for t in txs if t.date <= inp.end)
        paid_in = sum(t.amount_eur for t in txs if inp.start < t.date <= inp.end)
        if units_start == 0 and units_end == 0:
            continue
        v0, v1 = units_start * float(nav[i0]), units_end * float(nav[i1])
        raw.append((pid, v0, v1, v1 - v0 - paid_in, v0 + paid_in))
        start_total, end_total, pnl_total = start_total + v0, end_total + v1, pnl_total + (v1 - v0 - paid_in)

    for pid, _, _, pnl, base in raw:
        rows.append(
            AttributionRow(
                product_id=pid,
                name=ctx.product(pid).name,
                pnl_eur=round(pnl, 2),
                pnl_pct=round(pnl / base * 100, 2) if base > 0 else 0.0,
                contribution_pct=round(pnl / start_total * 100, 2) if start_total > 0 else 0.0,
            )
        )
    rows.sort(key=lambda r: (r.pnl_eur, r.product_id))
    return ExplainMoveOutput(
        customer_id=customer.id,
        start=inp.start,
        end=inp.end,
        start_value_eur=round(start_total, 2),
        end_value_eur=round(end_total, 2),
        change_eur=round(pnl_total, 2),
        change_pct=round(pnl_total / start_total * 100, 2) if start_total > 0 else 0.0,
        rows=rows,
        events=matched_events(customer, inp.start, inp.end, ctx),
    )


def summarize(out: ExplainMoveOutput, ctx: ToolContext) -> str:
    sign = "+" if out.change_eur >= 0 else ""
    n = len(out.events)
    events = "1 passendes Ereignis" if n == 1 else f"{n} passende Ereignisse"
    return f"Depot {sign}{de_num(out.change_eur, 2)} € ({sign}{de_num(out.change_pct, 2)} %), {events}"
