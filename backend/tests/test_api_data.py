"""The read-only data endpoints and the eval-report adapter (SPEC §9)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api_data import store_or_503
from app.data.store import Store
from app.evals_view import NoEvalReportError, build_eval_report
from app.main import app
from app.schemas.evals import EvalReport
from app.schemas.portfolio import Customer, PortfolioView
from app.schemas.products import Product

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(data_store):
    app.dependency_overrides[store_or_503] = lambda: data_store
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_customers_are_the_three_personas(client):
    res = client.get("/api/customers")
    assert res.status_code == 200
    customers = [Customer.model_validate(c) for c in res.json()]
    assert [c.id for c in customers] == ["anna", "markus", "elif"]


def test_portfolio_matches_the_view_builder(client):
    res = client.get("/api/customers/markus/portfolio")
    assert res.status_code == 200
    view = PortfolioView.model_validate(res.json())
    assert {p.product_id for p in view.positions} == {"P03", "P22", "P11"}
    assert view.series[-1].value_eur == pytest.approx(sum(p.value_eur for p in view.positions), abs=0.05)


def test_portfolio_unknown_customer_is_404(client):
    assert client.get("/api/customers/nobody/portfolio").status_code == 404


def test_products_list_and_detail(client):
    listed = client.get("/api/products").json()
    assert len(listed) == 40
    one = Product.model_validate(client.get("/api/products/P07").json())
    assert one.id == "P07" and one.holdings
    assert client.get("/api/products/P99").status_code == 404


def test_kid_pdf_is_served_inline_and_only_for_real_products(client):
    res = client.get("/api/kid/P07.pdf")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["content-disposition"].startswith("inline")
    assert res.content.startswith(b"%PDF")
    assert client.get("/api/kid/P99.pdf").status_code == 404


def test_missing_universe_is_503_with_a_hint(tmp_path, monkeypatch):
    monkeypatch.setattr("app.api_data.get_store", lambda: Store(tmp_path / "empty"))
    res = TestClient(app).get("/api/products")
    assert res.status_code == 503
    assert "make data" in res.json()["detail"]


# ── evals adapter ───────────────────────────────────────────────────────────


def test_committed_reports_build_a_valid_eval_report():
    report = build_eval_report(REPO_ROOT / "evals" / "reports")
    assert isinstance(report, EvalReport)
    assert not any(s.sample for s in (report.retrieval, report.router, report.answers, report.redteam))
    assert [r.mode for r in report.retrieval.rows] == ["bm25", "dense", "hybrid", "hybrid_rerank"]
    latest = json.loads((REPO_ROOT / "evals" / "reports" / "latest.json").read_text(encoding="utf-8"))
    assert report.router.advice_recall == latest["suites"]["router"]["metrics"]["advice_recall"]
    # the documented red gate is reported as failed, not hidden
    advice = next(g for g in report.gates if g.metric == "Beratungsanfragen erkannt")
    assert advice.passed is False and advice.threshold == 0.95


def test_a_suite_missing_from_the_newest_report_comes_from_an_older_one(tmp_path):
    src = REPO_ROOT / "evals" / "reports" / "latest.json"
    full = json.loads(src.read_text(encoding="utf-8"))
    (tmp_path / "20260101T000000Z.json").write_text(json.dumps(full), encoding="utf-8")
    ci_only = {**full, "generated_at": "2026-02-02T00:00:00+00:00"}
    ci_only["suites"] = {k: v for k, v in full["suites"].items() if k in ("retrieval", "router", "redteam")}
    (tmp_path / "20260202T000000Z.json").write_text(json.dumps(ci_only), encoding="utf-8")
    report = build_eval_report(tmp_path)
    assert report.answers.n == 30


def test_a_partial_run_is_ignored(tmp_path):
    full = json.loads((REPO_ROOT / "evals" / "reports" / "latest.json").read_text(encoding="utf-8"))
    (tmp_path / "20260101T000000Z.json").write_text(json.dumps(full), encoding="utf-8")
    partial = {**full, "partial": True}
    partial["suites"] = {**full["suites"], "router": {**full["suites"]["router"], "n": 3}}
    (tmp_path / "20260303T000000Z.json").write_text(json.dumps(partial), encoding="utf-8")
    assert build_eval_report(tmp_path).router.n_dev == 60


def test_no_reports_is_an_error_naming_the_fix(tmp_path):
    with pytest.raises(NoEvalReportError, match="make eval"):
        build_eval_report(tmp_path)


def test_evals_endpoint_returns_the_contract(client):
    res = client.get("/api/evals/latest")
    assert res.status_code == 200
    EvalReport.model_validate(res.json())
