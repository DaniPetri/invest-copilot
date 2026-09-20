"""The data behind the Übersicht and Depot screens: value curve, positions and event markers for one customer.

Everything is derived from the deterministic tools, so the numbers on screen are the tools' numbers.
"""

from datetime import date, timedelta

import numpy as np

from .data.store import Store
from .schemas.portfolio import EventMarker, PortfolioPosition, PortfolioView, SeriesPoint
from .schemas.tools import ExplainMoveInput
from .tools.attribution import explain_move, matched_events
from .tools.base import ToolContext, ToolError
from .tools.lookthrough import position_weights

SERIES_DAYS = 252  # about 12 months of business days


def event_window(ev) -> tuple[date, date]:
    """The window used to ask 'what did this event do to my depot': the day before the shock to the day after it
    ends. Shared with the frontend (`eventWindow` in lib/events.ts): keep both in sync."""
    return ev.date - timedelta(days=1), ev.date + timedelta(days=ev.duration_days)


def _value_series(store: Store, customer, n_days: int) -> tuple[np.ndarray, np.ndarray]:
    prices = store.prices
    units = {p.product_id: np.zeros(len(prices.dates)) for p in customer.positions}
    for t in customer.transactions:
        units[t.product_id][prices.index_on_or_after(t.date) :] += t.units if t.kind != "verkauf" else -t.units
    total = sum(units[pid] * prices.products[pid] for pid in units)
    return prices.dates[-n_days:], total[-n_days:]


def build_portfolio_view(store: Store, customer_id: str, n_days: int = SERIES_DAYS) -> PortfolioView:
    ctx = ToolContext(store)
    customer = ctx.customer(customer_id)
    dates, values = _value_series(store, customer, n_days)
    as_of = date.fromisoformat(str(dates[-1]))

    three_months_ago = as_of - timedelta(days=91)
    move = explain_move(ExplainMoveInput(customer_id=customer_id, start=three_months_ago, end=as_of), ctx)

    weights = position_weights(customer, ctx)
    nav = store.prices.products
    positions = []
    for p in sorted(customer.positions, key=lambda p: -weights.get(p.product_id, 0)):
        product = ctx.product(p.product_id)
        positions.append(
            PortfolioPosition(
                product_id=p.product_id,
                name=product.name,
                asset_class=product.asset_class,
                sri=product.sri,
                units=p.units,
                value_eur=round(p.units * float(nav[p.product_id][-1]), 2),
                weight=round(weights.get(p.product_id, 0.0), 6),
            )
        )

    first = date.fromisoformat(str(dates[0]))
    markers = []
    for ev in sorted(matched_events(customer, first, as_of, ctx), key=lambda e: e.date):
        start, end = event_window(ev)
        try:
            m = explain_move(ExplainMoveInput(customer_id=customer_id, start=start, end=end), ctx)
        except ToolError:
            continue  # the customer held nothing yet
        if m.start_value_eur > 0:
            markers.append(EventMarker(event=ev, change_eur=m.change_eur, change_pct=m.change_pct))

    return PortfolioView(
        customer_id=customer_id,
        as_of=as_of,
        total_value_eur=round(float(values[-1]), 2),
        cash_eur=customer.cash_eur,
        change_3m_eur=move.change_eur,
        change_3m_pct=move.change_pct,
        series=[
            SeriesPoint(date=date.fromisoformat(str(d)), value_eur=round(float(v), 2))
            for d, v in zip(dates, values, strict=True)
        ],
        positions=positions,
        events=markers,
    )
