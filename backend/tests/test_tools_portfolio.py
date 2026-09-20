"""M4 tools, second group: portfolio_lookthrough and explain_move."""

from datetime import date, timedelta

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from app.data.store import Store
from app.schemas.portfolio import Position, Transaction
from app.schemas.tools import ExplainMoveInput, LookthroughInput
from app.tools.attribution import explain_move
from app.tools.base import ToolContext, ToolError
from app.tools.lookthrough import portfolio_lookthrough

SLOW = settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])


def with_customer(ctx: ToolContext, customer) -> ToolContext:
    """A context whose only customer is `customer` (same universe, same prices)."""
    store = Store(ctx.store.root)
    store.__dict__["customers"] = [customer]
    store.__dict__["prices"] = ctx.store.prices  # share the parsed prices
    return ToolContext(store)


def _look(ctx, cid):
    return portfolio_lookthrough(LookthroughInput(customer_id=cid), ctx)


# ── portfolio_lookthrough ───────────────────────────────────────────────────


def test_markus_lookthrough_summary(ctx):
    out = _look(ctx, "markus")
    assert (out.n_products, out.n_companies) == (3, 60)
    assert out.flags == ["single_company_over_5pct", "top10_over_30pct"]
    assert out.by_company[0].weight > 0.05
    assert out.top10_share == pytest.approx(sum(r.weight for r in out.by_company[:10]))
    assert out.by_sector[0].key == "Technologie" and out.by_sector[0].weight > 0.4
    assert out.by_country[0].key == "US"
    assert [(o.product_a, o.product_b) for o in out.overlaps] == [("P03", "P11"), ("P03", "P22"), ("P11", "P22")]


def test_exposure_matches_a_hand_computation(ctx):
    c = ctx.customer("markus")
    nav = ctx.store.prices.products
    values = {p.product_id: p.units * float(nav[p.product_id][-1]) for p in c.positions}
    total = sum(values.values())
    top = _look(ctx, "markus").by_company[0]
    expected = sum(
        values[pid] / total * h.weight for pid in values for h in ctx.product(pid).holdings if h.id == top.key
    )
    assert top.weight == pytest.approx(expected)
    assert top.label == next(h.name for h in ctx.product("P03").holdings if h.id == top.key)


def test_exposures_sum_to_100_percent(ctx):
    for c in ctx.store.customers:
        out = _look(ctx, c.id)
        for rows in (out.by_company, out.by_sector, out.by_country):
            assert sum(r.weight for r in rows) == pytest.approx(1.0, abs=1e-6)
            assert [r.weight for r in rows] == sorted((r.weight for r in rows), reverse=True)


def test_overlap_of_world_and_tech_etf_is_hand_checkable(ctx):
    w = {h.id: h.weight for h in ctx.product("P03").holdings}
    t = {h.id: h.weight for h in ctx.product("P22").holdings}
    expected = sum(min(w[i], t[i]) for i in w.keys() & t.keys())
    pair = next(o for o in _look(ctx, "markus").overlaps if (o.product_a, o.product_b) == ("P03", "P22"))
    assert pair.overlap == pytest.approx(expected) and pair.overlap > 0.3
    europe = next(o for o in _look(ctx, "markus").overlaps if (o.product_a, o.product_b) == ("P03", "P11"))
    assert europe.overlap < pair.overlap  # Europe ETF shares little with the world ETF


def test_hhi_is_the_sum_of_squared_company_weights(ctx):
    out = _look(ctx, "markus")
    assert out.hhi == pytest.approx(sum(r.weight**2 for r in out.by_company), rel=1e-6)
    assert 1 / out.n_companies <= out.hhi <= 1


def test_bond_holdings_show_up_in_elifs_look_through(ctx):
    out = _look(ctx, "elif")
    sectors = {r.key for r in out.by_sector}
    assert {"Staatsanleihen", "Unternehmensanleihen", "Geldmarkt"} & sectors
    assert out.n_products == 4


def test_customer_without_positions(ctx):
    empty = ctx.customer("anna").model_copy(update={"positions": [], "transactions": []})
    out = _look_with(ctx, empty)
    assert (out.n_products, out.n_companies, out.hhi, out.top10_share, out.flags) == (0, 0, 0.0, 0.0, [])
    assert out.by_company == out.by_sector == out.by_country == out.overlaps == []


def _look_with(ctx, customer):
    return portfolio_lookthrough(LookthroughInput(customer_id=customer.id), with_customer(ctx, customer))


def test_lookthrough_unknown_customer(ctx):
    with pytest.raises(ToolError) as e:
        _look(ctx, "nobody")
    assert e.value.code == "not_found"


@SLOW
@given(
    picks=st.dictionaries(
        st.sampled_from([f"P{i:02d}" for i in range(1, 41)]), st.floats(0.01, 5000), min_size=1, max_size=6
    )
)
def test_property_exposures_sum_to_one_and_overlap_is_symmetric_and_bounded(ctx, picks):
    base = ctx.customer("markus")
    customer = base.model_copy(
        update={"positions": [Position(product_id=p, units=u) for p, u in picks.items()], "transactions": []}
    )
    out = _look_with(ctx, customer)
    for rows in (out.by_company, out.by_sector, out.by_country):
        assert sum(r.weight for r in rows) == pytest.approx(1.0, abs=1e-6)
        assert all(0 <= r.weight <= 1 for r in rows)
    assert out.n_products == len(picks)
    assert 0 < out.hhi <= 1 and out.top10_share <= 1 + 1e-9
    assert ("single_company_over_5pct" in out.flags) == (out.by_company[0].weight > 0.05)
    assert ("top10_over_30pct" in out.flags) == (out.top10_share > 0.30)
    holdings = {p: {h.id: h.weight for h in ctx.product(p).holdings} for p in picks}
    assert len(out.overlaps) == len(picks) * (len(picks) - 1) // 2
    for o in out.overlaps:
        assert 0 <= o.overlap <= 1
        a, b = holdings[o.product_a], holdings[o.product_b]
        forward = sum(min(a[i], b[i]) for i in a.keys() & b.keys())
        backward = sum(min(b[i], a[i]) for i in b.keys() & a.keys())
        assert forward == pytest.approx(backward) == pytest.approx(o.overlap, abs=1e-8)  # symmetric


# ── explain_move ────────────────────────────────────────────────────────────


def _move(ctx, cid, start, end):
    return explain_move(ExplainMoveInput(customer_id=cid, start=start, end=end), ctx)


def test_attribution_finds_the_ground_truth_event_for_markus_in_august_2026(ctx):
    out = _move(ctx, "markus", date(2026, 8, 1), date(2026, 8, 31))
    assert [e.id for e in out.events] == ["E12"]
    assert out.change_eur < 0 and -6 < out.change_pct < -1  # the month is a decline, as the demo question says
    assert all(r.pnl_eur < 0 for r in out.rows)
    ev = out.events[0]
    assert (str(ev.date), ev.sectors, ev.shock_pct) == ("2026-08-12", ["Technologie"], -6.0)
    assert ev.name == "Chipsektor: schwache Quartalszahlen"


def test_the_event_window_shows_the_tech_etf_as_the_biggest_drag(ctx):
    out = _move(ctx, "markus", date(2026, 8, 11), date(2026, 8, 13))
    assert [e.id for e in out.events] == ["E12"]
    assert out.change_eur < 0 and out.rows[0].product_id == "P22"  # worst first
    assert out.rows[0].pnl_eur < out.rows[1].pnl_eur <= out.rows[2].pnl_eur
    tech = next(r for r in out.rows if r.product_id == "P22")
    europe = next(r for r in out.rows if r.product_id == "P11")
    assert tech.pnl_pct < europe.pnl_pct


def test_contributions_add_up_to_the_total_move(ctx):
    for start, end in [(date(2026, 8, 1), date(2026, 8, 31)), (date(2025, 1, 2), date(2025, 6, 30))]:
        out = _move(ctx, "markus", start, end)
        assert sum(r.pnl_eur for r in out.rows) == pytest.approx(out.change_eur, abs=0.02)
        assert sum(r.contribution_pct for r in out.rows) == pytest.approx(out.change_pct, abs=0.02)
        assert out.change_pct == pytest.approx(out.change_eur / out.start_value_eur * 100, abs=0.01)


def test_savings_plan_purchases_in_the_window_are_not_gains(ctx):
    c = ctx.customer("markus")
    start, end = date(2026, 8, 1), date(2026, 8, 31)
    paid_in = sum(t.amount_eur for t in c.transactions if start < t.date <= end)
    assert paid_in == 105.0  # the 3 August savings plan purchases
    out = _move(ctx, "markus", start, end)
    assert out.end_value_eur - out.start_value_eur - paid_in == pytest.approx(out.change_eur, abs=0.05)


def test_hand_computed_single_purchase(ctx):
    """One purchase on 3 Aug: the P&L is just the value at the end minus what was paid."""
    nav = ctx.store.prices.products["P03"]
    prices = ctx.store.prices
    buy_day, end = date(2026, 8, 3), date(2026, 8, 31)
    units = 10.0
    amount = round(units * float(nav[prices.index_on_or_after(buy_day)]), 2)
    c = ctx.customer("anna").model_copy(
        update={
            "positions": [Position(product_id="P03", units=units)],
            "transactions": [Transaction(date=buy_day, product_id="P03", units=units, amount_eur=amount, kind="kauf")],
        }
    )
    out = explain_move(ExplainMoveInput(customer_id=c.id, start=date(2026, 8, 1), end=end), with_customer(ctx, c))
    expected = units * float(nav[prices.index_on_or_before(end)]) - amount
    assert out.start_value_eur == 0.0
    assert out.change_eur == pytest.approx(expected, abs=0.01)
    assert out.rows[0].pnl_eur == pytest.approx(expected, abs=0.01)
    assert out.change_pct == 0.0  # no start value, so no percentage


def test_weekend_start_uses_the_previous_close(ctx):
    sat = _move(ctx, "markus", date(2026, 8, 1), date(2026, 8, 14))  # Saturday
    fri = _move(ctx, "markus", date(2026, 7, 31), date(2026, 8, 14))  # Friday
    assert sat.start_value_eur == fri.start_value_eur


def test_market_wide_events_are_matched_for_any_portfolio(ctx):
    out = _move(ctx, "markus", date(2024, 8, 1), date(2024, 8, 31))
    assert "E08" in [e.id for e in out.events]  # market-wide shock on 2024-08-05


def test_sector_events_need_exposure_to_that_sector(ctx):
    money = ctx.customer("elif").model_copy(
        update={
            "positions": [Position(product_id="P39", units=100.0)],
            "transactions": [
                Transaction(date=date(2024, 1, 2), product_id="P39", units=100.0, amount_eur=1.0, kind="kauf")
            ],
        }
    )
    mctx = with_customer(ctx, money)
    tech_month = explain_move(ExplainMoveInput(customer_id="elif", start=date(2026, 8, 1), end=date(2026, 8, 31)), mctx)
    assert tech_month.events == []  # a money market fund holds no technology
    crash = explain_move(ExplainMoveInput(customer_id="elif", start=date(2024, 8, 1), end=date(2024, 8, 31)), mctx)
    assert [e.id for e in crash.events] == ["E08"]


def test_a_window_without_a_trading_day_is_rejected(ctx):
    with pytest.raises(ToolError, match="no trading day") as e:
        _move(ctx, "markus", date(2026, 8, 1), date(2026, 8, 2))  # Saturday to Sunday
    assert e.value.code == "invalid"


def test_events_outside_the_window_are_ignored(ctx):
    assert _move(ctx, "markus", date(2026, 6, 1), date(2026, 6, 30)).events == []


def test_events_are_ordered_by_relevance(ctx):
    out = _move(ctx, "markus", date(2024, 1, 1), date(2025, 12, 31))
    ids = [e.id for e in out.events]
    assert {"E08", "E10"} <= set(ids)  # the market crash and the tech rally both touch Markus
    assert ids.index("E10") < ids.index(
        "E07"
    )  # tech rally (heavy exposure) before pharma (little exposure), if present
    assert all(date(2024, 1, 1) <= e.date <= date(2025, 12, 31) for e in out.events)


@pytest.mark.parametrize(
    ("customer", "start", "end", "code"),
    [
        ("nobody", date(2026, 8, 1), date(2026, 8, 31), "not_found"),
        ("markus", date(2026, 8, 31), date(2026, 8, 1), "invalid"),
        ("markus", date(2026, 8, 1), date(2026, 8, 1), "invalid"),
        ("markus", date(2020, 1, 1), date(2020, 2, 1), "invalid"),
    ],
)
def test_explain_move_errors(ctx, customer, start, end, code):
    with pytest.raises(ToolError) as e:
        _move(ctx, customer, start, end)
    assert e.value.code == code


@SLOW
@given(
    customer=st.sampled_from(["anna", "markus", "elif"]),
    start=st.dates(min_value=date(2021, 9, 1), max_value=date(2026, 8, 20)),
    days=st.integers(1, 400),
)
def test_property_attribution_adds_up(ctx, customer, start, days):
    end = min(start + timedelta(days=days), date(2026, 8, 31))
    prices = ctx.store.prices
    assume(end > start and prices.index_on_or_before(end) > prices.index_on_or_before(start))  # needs a trading day
    out = _move(ctx, customer, start, end)
    assert sum(r.pnl_eur for r in out.rows) == pytest.approx(out.change_eur, abs=0.02 * max(1, len(out.rows)))
    assert sum(r.contribution_pct for r in out.rows) == pytest.approx(out.change_pct, abs=0.01 * max(1, len(out.rows)))
    assert [r.pnl_eur for r in out.rows] == sorted(r.pnl_eur for r in out.rows)
    assert all(start <= e.date <= end for e in out.events)
    assert out.end_value_eur >= 0 and out.start_value_eur >= 0
