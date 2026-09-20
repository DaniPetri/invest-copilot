"""M4 tools, first group: screen_products, suitability_check, cost_projection."""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.schemas.tools import CostProjectionInput, ScreenFilter, ScreenInput, SuitabilityInput
from app.tools.base import ToolError
from app.tools.costs import cost_projection
from app.tools.screener import screen_products
from app.tools.suitability import (
    MAX_SRI_BY_RISK_CLASS,
    check_horizon,
    check_knowledge,
    check_risk,
    check_sustainability,
    suitability_check,
)

# ── screen_products ─────────────────────────────────────────────────────────


def _screen(ctx, sort="ter", limit=40, **f):
    return screen_products(ScreenInput(filter=ScreenFilter(**f), sort=sort, limit=limit), ctx)


def test_no_filter_returns_everything_sorted_by_cost(ctx):
    out = _screen(ctx)
    assert out.total_matches == 40 and len(out.items) == 40
    ters = [i.ter for i in out.items]
    assert ters == sorted(ters)
    assert all(i.why_matched == [] for i in out.items)


def test_default_limit_is_ten(ctx):
    out = screen_products(ScreenInput(filter=ScreenFilter()), ctx)
    assert len(out.items) == 10 and out.total_matches == 40


def test_discover_example_matches_an_independent_count(ctx):
    """'50 EUR im Monat, nachhaltig, Europa, ohne Waffen' from design/02 and the discover fixture."""
    f = {
        "asset_classes": ["equity_etf"], "savings_plan": True, "regions": ["Europa"], "sfdr_min": 8,
        "exclusions": ["Waffen"], "max_sri": 4, "max_ter": 0.003,
    }  # fmt: skip
    out = _screen(ctx, **f)
    expected = [
        p.id
        for p in ctx.store.products
        if p.asset_class == "equity_etf" and p.savings_plan_min_eur is not None and p.region == "Europa"
        and p.sfdr >= 8 and "Waffen" in p.exclusions and p.sri <= 4 and p.ter <= 0.003
    ]  # fmt: skip
    assert out.total_matches == len(expected) > 0
    assert {i.product_id for i in out.items} == set(expected)
    for item in out.items:
        assert len(item.why_matched) == 7  # one reason per active filter
    assert out.items[0].why_matched[0] == "Typ: Aktien-ETF"


def test_why_matched_only_names_active_filters(ctx):
    out = _screen(ctx, regions=["USA"], max_ter=0.001)
    assert out.items and all(len(i.why_matched) == 2 for i in out.items)
    assert all(i.why_matched[0] == "Region: USA" and i.why_matched[1].startswith("Kosten ") for i in out.items)


def test_empty_lists_and_savings_plan_false_mean_no_filter(ctx):
    baseline = _screen(ctx)
    loose = _screen(ctx, asset_classes=[], regions=[], exclusions=[], savings_plan=False)
    assert loose.total_matches == baseline.total_matches == 40


def test_all_listed_exclusions_are_required(ctx):
    out = _screen(ctx, exclusions=["Waffen", "Fossile"])
    assert out.items
    for item in out.items:
        assert {"Waffen", "Fossile"} <= set(ctx.product(item.product_id).exclusions)


def test_sfdr_minimum_and_distribution(ctx):
    art9 = _screen(ctx, sfdr_min=9)
    assert art9.items and all(i.sfdr == 9 for i in art9.items)
    art8_up = _screen(ctx, sfdr_min=8)
    assert {i.sfdr for i in art8_up.items} == {8, 9}
    dist = _screen(ctx, distribution="ausschüttend")
    assert dist.items and all(i.distribution == "ausschüttend" for i in dist.items)


@pytest.mark.parametrize(
    ("sort", "key", "reverse"),
    [("ter", lambda i: i.ter, False), ("sri", lambda i: i.sri, False), ("name", lambda i: i.name.lower(), False)],
)
def test_sort_orders(ctx, sort, key, reverse):
    keys = [key(i) for i in _screen(ctx, sort=sort).items]
    assert keys == sorted(keys, reverse=reverse)


def test_sort_by_fund_size_is_descending(ctx):
    sizes = [ctx.product(i.product_id).fund_size_eur_m for i in _screen(ctx, sort="fund_size").items]
    assert sizes == sorted(sizes, reverse=True)


def test_limit_and_total_matches(ctx):
    out = _screen(ctx, limit=3, asset_classes=["equity_etf"])
    assert len(out.items) == 3 and out.total_matches == 24


def test_max_ter_boundary_is_inclusive(ctx):
    p = ctx.product("P03")  # TER 0.0015
    ids = {i.product_id for i in _screen(ctx, max_ter=p.ter).items}
    assert "P03" in ids
    assert "P03" not in {i.product_id for i in _screen(ctx, max_ter=p.ter - 0.0001).items}


ASSET_CLASSES = ["equity_etf", "equity_fund", "bond_fund", "mixed_fund", "money_market"]
REGIONS = ["Europa", "USA", "Welt", "Schwellenländer", "Österreich"]
EXCLUSIONS = ["Waffen", "Fossile", "Tabak", "Glücksspiel"]

filters = st.builds(
    ScreenFilter,
    asset_classes=st.none() | st.lists(st.sampled_from(ASSET_CLASSES), max_size=3),
    savings_plan=st.none() | st.booleans(),
    regions=st.none() | st.lists(st.sampled_from(REGIONS), max_size=3),
    sfdr_min=st.none() | st.sampled_from([6, 8, 9]),
    exclusions=st.none() | st.lists(st.sampled_from(EXCLUSIONS), max_size=3),
    max_sri=st.none() | st.integers(1, 7),
    max_ter=st.none() | st.floats(0, 0.03),
    distribution=st.none() | st.sampled_from(["thesaurierend", "ausschüttend"]),
)


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(f=filters, sort=st.sampled_from(["ter", "sri", "fund_size", "name"]), limit=st.integers(1, 40))
def test_property_every_hit_satisfies_every_active_filter(ctx, f, sort, limit):
    out = screen_products(ScreenInput(filter=f, sort=sort, limit=limit), ctx)
    assert len(out.items) <= limit and len(out.items) <= out.total_matches
    for item in out.items:
        p = ctx.product(item.product_id)
        assert not f.asset_classes or p.asset_class in f.asset_classes
        assert not f.savings_plan or p.savings_plan_min_eur is not None
        assert not f.regions or p.region in f.regions
        assert f.sfdr_min is None or p.sfdr >= f.sfdr_min
        assert not f.exclusions or set(f.exclusions) <= set(p.exclusions)
        assert f.max_sri is None or p.sri <= f.max_sri
        assert f.max_ter is None or p.ter <= f.max_ter + 1e-9
        assert f.distribution is None or p.distribution == f.distribution
    assert out == screen_products(ScreenInput(filter=f, sort=sort, limit=limit), ctx)  # deterministic


# ── suitability_check ───────────────────────────────────────────────────────


def _suit(ctx, customer, product):
    return suitability_check(SuitabilityInput(customer_id=customer, product_id=product), ctx)


def test_elif_against_an_sri5_etf_fails_on_risk(ctx):
    out = _suit(ctx, "elif", "P22")
    assert ctx.product("P22").sri == 5 and ctx.product("P22").asset_class == "equity_etf"
    assert out.verdict == "fail"
    risk = next(r for r in out.reasons if r.rule == "risk")
    assert risk.status == "fail" and risk.profile_field == "risk_class"
    assert "2 von 5" in risk.text and "5 von 7" in risk.text and "bis Stufe 3" in risk.text
    assert [r.rule for r in out.reasons] == ["risk", "knowledge", "experience", "horizon", "sustainability"]


def test_markus_fits_a_broad_etf(ctx):
    out = _suit(ctx, "markus", "P03")
    assert out.verdict == "pass" and all(r.status == "pass" for r in out.reasons)


def test_anna_risk_ladder(ctx):
    assert next(r for r in _suit(ctx, "anna", "P08").reasons if r.rule == "risk").status == "pass"  # SRI 4
    assert next(r for r in _suit(ctx, "anna", "P22").reasons if r.rule == "risk").status == "warn"  # SRI 5
    assert next(r for r in _suit(ctx, "anna", "P32").reasons if r.rule == "risk").status == "fail"  # SRI 6


def test_sustainability_preference_against_sfdr(ctx):
    by_product = {
        p: next(r for r in _suit(ctx, "anna", p).reasons if r.rule == "sustainability") for p in ("P03", "P11", "P07")
    }
    assert by_product["P03"].status == "warn" and "Artikel 6" in by_product["P03"].text  # wants Art. 8, has Art. 6
    assert by_product["P11"].status == "pass"  # Art. 8
    assert by_product["P07"].status == "pass"  # Art. 9
    assert next(r for r in _suit(ctx, "markus", "P03").reasons if r.rule == "sustainability").status == "pass"


def test_knowledge_and_experience_versus_complexity(ctx):
    anna_fund = _suit(ctx, "anna", "P25")  # active fund, Anna has no fund knowledge or experience
    kn = next(r for r in anna_fund.reasons if r.rule == "knowledge")
    ex = next(r for r in anna_fund.reasons if r.rule == "experience")
    assert (kn.status, ex.status) == ("warn", "warn")
    assert kn.profile_field == "knowledge.equity_fund" and ex.profile_field == "experience.equity_fund"
    swap = _suit(ctx, "anna", "P06")  # synthetic replication needs advanced knowledge
    assert next(r for r in swap.reasons if r.rule == "knowledge").status == "warn"
    assert next(r for r in _suit(ctx, "markus", "P06").reasons if r.rule == "knowledge").status == "pass"


def test_reason_texts_are_grammatical_german(ctx):
    kn = next(r for r in _suit(ctx, "elif", "P22").reasons if r.rule == "knowledge")
    ex = next(r for r in _suit(ctx, "elif", "P22").reasons if r.rule == "experience")
    assert kn.text == "Für Aktien-ETFs sind Grundkenntnisse nötig. Bei dir ist eingetragen: Grundkenntnisse."
    assert ex.text == "Für Aktien-ETFs ist keine Erfahrung nötig. Bei dir ist eingetragen: etwas Erfahrung."


def test_money_market_fits_everyone_on_risk_and_knowledge(ctx):
    for cid in ("anna", "markus", "elif"):
        out = _suit(ctx, cid, "P39")
        assert next(r for r in out.reasons if r.rule == "risk").status == "pass"
        assert next(r for r in out.reasons if r.rule == "knowledge").status == "pass"


@pytest.mark.parametrize(("horizon", "expected"), [(10, "pass"), (5, "pass"), (4, "warn"), (3, "warn"), (2, "fail")])
def test_horizon_against_the_recommended_holding_period(ctx, horizon, expected):
    c = ctx.customer("markus")
    c = c.model_copy(update={"profile": c.profile.model_copy(update={"horizon_years": horizon})})
    p = ctx.product("P03")
    assert p.recommended_holding_years == 5
    assert check_horizon(c, p).status == expected


def test_risk_status_never_improves_with_a_higher_sri(ctx):
    order = {"pass": 0, "warn": 1, "fail": 2}
    p = ctx.product("P03")
    for rc in range(1, 6):
        c = ctx.customer("anna")
        c = c.model_copy(update={"profile": c.profile.model_copy(update={"risk_class": rc})})
        statuses = [order[check_risk(c, p.model_copy(update={"sri": s})).status] for s in range(1, 8)]
        assert statuses == sorted(statuses)
        assert statuses[MAX_SRI_BY_RISK_CLASS[rc] - 1] == 0  # the limit itself still passes


def test_higher_knowledge_never_worsens_the_result(ctx):
    p = ctx.product("P06")
    order = {"pass": 0, "warn": 1, "fail": 2}
    base = ctx.customer("anna")
    results = []
    for level in ("keine", "basis", "erweitert"):
        know = {**base.profile.knowledge, "equity_etf": level}
        c = base.model_copy(update={"profile": base.profile.model_copy(update={"knowledge": know})})
        results.append(order[check_knowledge(c, p).status])
    assert results == sorted(results, reverse=True)


def test_every_customer_product_pair_is_consistent(ctx):
    fields = {"risk_class", "horizon_years", "sustainability_preference"}
    order = {"pass": 0, "warn": 1, "fail": 2}
    for c in ctx.store.customers:
        for p in ctx.store.products:
            out = _suit(ctx, c.id, p.id)
            assert len(out.reasons) == 5 and len({r.rule for r in out.reasons}) == 5
            assert out.verdict == max((r.status for r in out.reasons), key=order.get)
            for r in out.reasons:
                assert r.text and (
                    r.profile_field in fields or r.profile_field.split(".")[0] in ("knowledge", "experience")
                )
            assert {r.status for r in out.reasons} <= {"pass", "warn", "fail"}


def test_suitability_unknown_ids(ctx):
    with pytest.raises(ToolError) as e:
        _suit(ctx, "nobody", "P03")
    assert e.value.code == "not_found"
    with pytest.raises(ToolError):
        _suit(ctx, "anna", "P99")


def test_sustainability_art9_preference_against_art6_is_a_fail(ctx):
    c = ctx.customer("anna")
    c = c.model_copy(update={"profile": c.profile.model_copy(update={"sustainability_preference": "art9"})})
    assert check_sustainability(c, ctx.product("P03")).status == "fail"  # Art. 6
    assert check_sustainability(c, ctx.product("P11")).status == "warn"  # Art. 8
    assert check_sustainability(c, ctx.product("P07")).status == "pass"  # Art. 9


# ── cost_projection ─────────────────────────────────────────────────────────


def _costs(ctx, product="P07", monthly=50.0, years=10, **kw):
    return cost_projection(CostProjectionInput(product_id=product, monthly_eur=monthly, years=years, **kw), ctx)


def test_matches_the_design_example(ctx):
    """design/03: 50 EUR a month for 10 years in a 0.15 % TER product: 45 EUR fund costs, 120 EUR fees, 2.8 %."""
    out = _costs(ctx)
    assert ctx.product("P07").ter == 0.0015
    ter_row, fee_row = out.rows
    assert ter_row.label == "Laufende Fondskosten (0,15 % p. a.)" and fee_row.label == "Sparplan-Entgelt (1 € je Rate)"
    assert ter_row.amount_eur == pytest.approx(45, abs=0.5)
    assert fee_row.amount_eur == 120.0
    assert out.total_contributions_eur == 6000.0
    assert out.total_pct_of_contributions == pytest.approx(2.8, abs=0.05)
    assert len(out.rows) == 2  # no entry cost on this ETF


def test_entry_cost_is_charged_on_every_contribution(ctx):
    p = ctx.product("P25")
    assert p.entry_cost == 0.04
    out = _costs(ctx, "P25", monthly=100, years=5)
    entry = next(r for r in out.rows if r.label.startswith("Einstiegskosten"))
    assert entry.label == "Einstiegskosten (4,00 %)"
    assert entry.amount_eur == pytest.approx(0.04 * 100 * 12 * 5)


def test_no_fee_means_no_fee_cost(ctx):
    out = _costs(ctx, fee_per_execution=0.0)
    assert out.rows[1].amount_eur == 0.0 and out.total_eur == pytest.approx(out.rows[0].amount_eur)


def test_fee_label_shows_cents_when_needed(ctx):
    assert _costs(ctx, fee_per_execution=1.5).rows[1].label == "Sparplan-Entgelt (1,50 € je Rate)"


def test_ter_cost_grows_with_the_balance_year_by_year(ctx):
    out = _costs(ctx, years=8)
    ter = [y.ter_eur for y in out.by_year]
    assert len(out.by_year) == 8 and [y.year for y in out.by_year] == list(range(1, 9))
    assert ter == sorted(ter) and ter[-1] > ter[0]
    assert out.by_year[-1].cumulative_eur == pytest.approx(out.total_eur, abs=0.05)


def test_cost_projection_unknown_product(ctx):
    with pytest.raises(ToolError) as e:
        _costs(ctx, "P99")
    assert e.value.code == "not_found"


def _assert_pct_of_contributions(out):
    """The tool rounds the percentage once, from unrounded inputs. Recomputing it from the two rounded outputs is off
    by up to their 0.005 rounding relative to the contributions, which is not small for a tiny plan (a few euros)."""
    pct = out.total_eur / out.total_contributions_eur * 100
    rounding = (100 + pct) * 0.005 / out.total_contributions_eur
    assert out.total_pct_of_contributions == pytest.approx(pct, abs=0.005 + rounding + 1e-9)


def test_pct_of_contributions_for_a_tiny_plan_is_consistent_with_the_rounded_outputs(ctx):
    """Regression: found by Hypothesis on CI (P01, 1.84375 EUR/month, 1 year): 54.28 vs 54.2948 from rounded outputs."""
    out = _costs(ctx, "P01", 1.84375, 1, fee_per_execution=1.0)
    _assert_pct_of_contributions(out)
    assert out.total_pct_of_contributions == 54.28


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    product=st.sampled_from([f"P{i:02d}" for i in range(1, 41)]),
    monthly=st.floats(1, 5000),
    years=st.integers(1, 40),
    fee=st.floats(0, 10),
)
def test_property_costs_are_non_negative_and_add_up(ctx, product, monthly, years, fee):
    out = _costs(ctx, product, monthly, years, fee_per_execution=fee)
    assert out.total_eur >= 0 and out.total_pct_of_contributions >= 0
    assert all(r.amount_eur >= 0 for r in out.rows)
    cumulative = [y.cumulative_eur for y in out.by_year]
    assert cumulative == sorted(cumulative)
    for y in out.by_year:
        assert min(y.ter_eur, y.fees_eur, y.entry_eur) >= 0
    assert sum(r.amount_eur for r in out.rows) == pytest.approx(out.total_eur, abs=0.02)
    _assert_pct_of_contributions(out)
