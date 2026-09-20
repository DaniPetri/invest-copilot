"""The frontend fixtures (frontend/fixtures/api) must stay valid against the pydantic contracts."""

import json

import pytest

from app.portfolio_view import build_portfolio_view, event_window
from app.schemas.evals import EvalReport
from app.schemas.portfolio import Customer, PortfolioView
from app.schemas.products import MarketEvent, Product
from app.schemas.tools import TOOL_MODELS, ToolResult
from tests.conftest import REPO_ROOT

API = REPO_ROOT / "frontend" / "fixtures" / "api"
load = lambda name: json.loads((API / name).read_text(encoding="utf-8"))  # noqa: E731

OUTPUT_BY_KIND = {
    "explain": "explain_move",
    "lookthrough": "portfolio_lookthrough",
    "simulate": "simulate_savings_plan",
    "cost": "cost_projection",
    "suitability": "suitability_check",
}


# ── the portfolio view builder ──────────────────────────────────────────────


def test_portfolio_view_for_markus(data_store):
    v = build_portfolio_view(data_store, "markus")
    assert str(v.as_of) == "2026-08-31" and len(v.series) == 252
    assert v.series[-1].value_eur == v.total_value_eur == pytest.approx(sum(p.value_eur for p in v.positions), abs=0.05)
    assert [p.product_id for p in v.positions] == ["P03", "P22", "P11"]  # largest first
    assert sum(p.weight for p in v.positions) == pytest.approx(1.0, abs=1e-5)
    assert [e.event.id for e in v.events] == ["E10", "E11", "E12"]
    assert v.change_3m_eur < 0  # the depot is down over the last three months


def test_event_markers_match_explain_move_over_the_shared_window(data_store):
    from app.schemas.tools import ExplainMoveInput
    from app.tools.attribution import explain_move
    from app.tools.base import ToolContext

    v = build_portfolio_view(data_store, "markus")
    marker = next(e for e in v.events if e.event.id == "E12")
    start, end = event_window(marker.event)
    assert (str(start), str(end)) == ("2026-08-11", "2026-08-14")
    move = explain_move(ExplainMoveInput(customer_id="markus", start=start, end=end), ToolContext(data_store))
    assert marker.change_eur == move.change_eur and marker.change_pct == move.change_pct
    assert marker.change_pct < -2  # the chip shock is a clear drop (design/04: -3.4 %)


def test_series_is_the_sum_of_units_times_nav(data_store):
    v = build_portfolio_view(data_store, "elif")
    prices = data_store.prices
    last = sum(p.units * float(prices.products[p.product_id][-1]) for p in data_store.customer("elif").positions)
    assert v.series[-1].value_eur == pytest.approx(last, abs=0.05)
    assert all(pt.value_eur > 0 for pt in v.series)


# ── every fixture file validates ────────────────────────────────────────────


def test_customers_and_products_validate():
    customers = [Customer.model_validate(c) for c in load("customers.json")]
    assert [c.id for c in customers] == ["anna", "markus", "elif"]
    products = [Product.model_validate(p) for p in load("products.json")]
    assert len(products) == 40 and all(len(p.holdings) <= 10 for p in products)
    assert products[2].id == "P03" and products[2].name == "Welt ETF"


def test_portfolios_validate_and_cover_every_persona():
    portfolios = load("portfolios.json")
    assert set(portfolios) == {"anna", "markus", "elif"}
    for cid, raw in portfolios.items():
        view = PortfolioView.model_validate(raw)
        assert view.customer_id == cid and view.series and view.positions and view.events


def test_tool_results_validate_against_the_output_models():
    tools = load("tools.json")
    kinds = {}
    for key, raw in tools.items():
        kind = key.split("|")[0]
        result = ToolResult.model_validate({k: v for k, v in raw.items() if k != "request"})
        name = OUTPUT_BY_KIND[kind]
        assert result.name == name and result.ok
        TOOL_MODELS[name][1].model_validate(result.payload)
        kinds[kind] = kinds.get(kind, 0) + 1
    assert kinds == {"explain": 9, "lookthrough": 3, "simulate": 48, "cost": 160, "suitability": 120}


def test_every_event_marker_has_its_explain_move_fixture():
    tools, portfolios = load("tools.json"), load("portfolios.json")
    for cid, view in portfolios.items():
        for marker in view["events"]:
            start, end = event_window(MarketEvent.model_validate(marker["event"]))
            result = tools[f"explain|{cid}|{start}|{end}"]
            assert result["payload"]["change_pct"] == marker["change_pct"]


def test_simulation_fixtures_carry_their_request_and_the_documented_mixes():
    tools = load("tools.json")
    entry = tools["simulate|50|20|ausgewogen"]
    assert entry["request"]["weights"] == [{"product_id": "P03", "weight": 0.6}, {"product_id": "P33", "weight": 0.4}]
    assert entry["payload"]["years"][-1] == 20 and entry["payload"]["total_contributions"] == 12000.0


def test_evals_fixture_is_the_measured_report():
    from pathlib import Path  # noqa: PLC0415

    from app.evals_view import build_eval_report  # noqa: PLC0415

    report = EvalReport.model_validate(load("evals.json"))
    measured = build_eval_report(Path(__file__).resolve().parents[2] / "evals" / "reports")
    assert report.mode == "fixture"
    assert report.model_dump(exclude={"mode"}) == measured.model_dump(exclude={"mode"})
    assert not any(s.sample for s in (report.retrieval, report.router, report.answers, report.redteam))
    hybrid = next(r for r in report.retrieval.rows if r.mode == "hybrid")
    assert hybrid.recall_at_5 == pytest.approx(0.920, abs=1e-3) and hybrid.n_questions == 1080
    # the documented red router gate stays visible
    assert [g.metric for g in report.gates if not g.passed] == ["Beratungsanfragen erkannt"]
