"""M2: the synthetic universe. `universe` builds it once per session into a temp dir."""

import numpy as np
import pytest

from app.data.generate import (
    PIN_MARKET_TOTAL,
    PIN_WINDOW,
    SEED,
    annual_vol,
    generate,
    isin_check_digit,
    isin_is_valid,
    pin_market_window,
    sri_from_vol,
)
from app.data.store import DataMissingError, Store


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("universe") / "gen"
    manifest = generate(out)
    return Store(out), out, manifest


@pytest.fixture(scope="session")
def store(built) -> Store:
    return built[0]


# ── companies ───────────────────────────────────────────────────────────────


def test_150_companies_with_unique_ids_and_names(store):
    cs = store.companies
    assert len(cs) == 150
    assert len({c.id for c in cs}) == 150 and len({c.name for c in cs}) == 150
    assert {c.name.rsplit(" ", 1)[1] for c in cs} <= {"AG", "SE", "plc", "Inc", "Corp"}


def test_companies_cover_11_sectors_and_15_countries(store):
    assert len({c.sector for c in store.companies}) == 11
    assert len({c.country for c in store.companies}) == 15


def test_ten_mega_caps_are_technology(store):
    top = sorted(store.companies, key=lambda c: -c.market_cap_eur_m)[:10]
    assert {c.sector for c in top} == {"Technologie"}
    assert min(c.market_cap_eur_m for c in top) > 200_000  # above every other company


# ── products ────────────────────────────────────────────────────────────────


def test_40_products_with_the_specified_mix(store):
    ps = store.products
    assert [p.id for p in ps] == [f"P{i:02d}" for i in range(1, 41)]
    counts = {c: sum(p.asset_class == c for p in ps) for c in {p.asset_class for p in ps}}
    assert counts == {"equity_etf": 24, "equity_fund": 8, "bond_fund": 4, "mixed_fund": 2, "money_market": 2}
    assert len({p.issuer for p in ps}) == 5
    assert {p.sfdr for p in ps} == {6, 8, 9}


def test_isin_check_digits_are_valid_and_prefixed(store):
    isins = [p.isin for p in store.products]
    assert len(set(isins)) == 40
    for isin in isins:
        assert isin.startswith("XD") and len(isin) == 12
        assert isin_is_valid(isin), isin


def test_isin_validator_agrees_with_real_isins():
    assert isin_is_valid("US0378331005")  # a real, publicly known ISIN: validates the algorithm itself
    assert not isin_is_valid("US0378331006")
    assert isin_check_digit("US037833100") == 5


def test_holding_weights_sum_to_one(store):
    for p in store.products:
        assert sum(h.weight for h in p.holdings) == pytest.approx(1.0, abs=1e-9), p.id
        assert all(h.weight > 0 for h in p.holdings)


def test_equity_products_hold_15_to_40_companies(store):
    for p in store.products:
        if p.asset_class in ("equity_etf", "equity_fund"):
            assert 15 <= len(p.holdings) <= 40, (p.id, len(p.holdings))
            assert all(h.id.startswith("C") for h in p.holdings)


def test_bond_and_money_products_hold_synthetic_issuers(store):
    for p in store.products:
        if p.asset_class in ("bond_fund", "money_market"):
            assert p.holdings and all(h.id[0] in "BM" for h in p.holdings)
    mixed = [p for p in store.products if p.asset_class == "mixed_fund"]
    for p in mixed:
        kinds = {h.id[0] for h in p.holdings}
        assert kinds == {"C", "B"}


def test_exclusions_are_respected_by_holdings(store):
    flags = {c.id: set(c.exclusion_flags) for c in store.companies}
    checked = 0
    for p in store.products:
        for h in p.holdings:
            if h.id in flags:
                assert not flags[h.id] & set(p.exclusions), (p.id, h.name)
                checked += 1
    assert checked > 500
    assert any(p.exclusions for p in store.products)


def test_region_products_only_hold_that_region(store):
    regions = {"USA": {"US"}, "Österreich": {"AT"}, "Schwellenländer": {"CN", "IN", "BR", "KR", "TW"}}
    for p in store.products:
        if p.region in regions and p.asset_class in ("equity_etf", "equity_fund"):
            assert {h.country for h in p.holdings} <= regions[p.region], p.id


def test_savings_plan_eligibility_is_mixed(store):
    plans = [p.savings_plan_min_eur for p in store.products]
    assert None in plans and 25.0 in plans and 50.0 in plans


# ── SRI ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("vol", "sri"),
    [
        (0.0, 1), (0.0049, 1), (0.005, 2), (0.0499, 2), (0.05, 3), (0.1199, 3), (0.12, 4),
        (0.1999, 4), (0.20, 5), (0.2999, 5), (0.30, 6), (0.7999, 6), (0.80, 7), (2.0, 7),
    ],
)  # fmt: skip
def test_sri_band_edges(vol, sri):
    assert sri_from_vol(vol) == sri


def test_product_sri_matches_simulated_volatility(store):
    prices = store.prices
    for p in store.products:
        assert p.sri == sri_from_vol(annual_vol(prices.products[p.id])), p.id


def test_sri_spread_covers_1_to_6_and_asset_classes_are_ordered(store):
    by_id = {p.id: p for p in store.products}
    assert {p.sri for p in store.products} == {1, 2, 3, 4, 5, 6}
    assert all(by_id[i].sri == 1 for i in ("P39", "P40"))
    bonds = [by_id[i].sri for i in ("P33", "P34", "P35", "P36")]
    equity_etf = [p.sri for p in store.products if p.asset_class == "equity_etf"]
    assert max(bonds) < min(equity_etf)
    assert any(s == 5 for s in equity_etf)  # an SRI-5 ETF exists (Elif's suitability demo)


# ── prices and events ───────────────────────────────────────────────────────


def test_prices_span_five_years_of_business_days_ending_2026_08_31(store):
    d = store.prices.dates
    assert str(d[-1]) == "2026-08-31"
    assert str(d[0]) == "2021-09-01"
    assert 1300 <= len(d) <= 1310
    assert np.all(np.is_busday(d)) and np.all(np.diff(d).astype(int) >= 1)
    for series in (*store.prices.assets.values(), *store.prices.products.values()):
        assert len(series) == len(d) and np.all(np.isfinite(series)) and np.all(series > 0)


def test_12_events_with_valid_sectors(store):
    from app.schemas.products import SECTORS

    ev = store.events
    assert len(ev) == 12 and len({e.id for e in ev}) == 12
    assert all(set(e.sectors) <= set(SECTORS) for e in ev)
    assert any(not e.sectors for e in ev) and any(e.sectors for e in ev)
    assert any(e.id == "E12" and str(e.date) == "2026-08-12" and e.sectors == ["Technologie"] for e in ev)


def _rolling_sum(x: np.ndarray, n: int) -> np.ndarray:
    c = np.concatenate([[0.0], np.cumsum(x)])
    return c[n:] - c[:-n]


def test_each_event_is_visible_in_the_affected_returns(store):
    """Sector events: relative return of the affected sectors vs the whole universe; market events: the universe."""
    prices = store.prices
    ids = [c.id for c in store.companies]
    returns = np.array([prices.assets[i][1:] / prices.assets[i][:-1] - 1 for i in ids])
    everything = returns.mean(axis=0)
    dates = prices.dates[1:]

    for ev in store.events:
        if ev.sectors:
            rows = [k for k, c in enumerate(store.companies) if c.sector in ev.sectors]
            series = returns[rows].mean(axis=0) - everything
        else:
            series = everything
        n = ev.duration_days
        window_sums = _rolling_sum(series, n)
        start = int(np.searchsorted(dates, np.datetime64(ev.date)))
        observed = window_sums[start]
        mask = np.ones(len(window_sums), dtype=bool)
        for other in store.events:  # exclude every event window from the baseline
            o = int(np.searchsorted(dates, np.datetime64(other.date)))
            mask[max(0, o - n) : o + other.duration_days] = False
        z = (observed - window_sums[mask].mean()) / window_sums[mask].std()
        assert np.sign(ev.shock_pct) * z >= 2.5, (ev.id, round(float(z), 2))


# ── look-through overlap, personas ──────────────────────────────────────────


def test_markus_world_and_tech_etf_share_the_same_top_10(store):
    def top10(pid):
        return {h.id for h in sorted(store.product(pid).holdings, key=lambda h: -h.weight)[:10]}

    assert top10("P03") == top10("P22")


def test_markus_lookthrough_triggers_the_concentration_flags(store):
    """SPEC §7 flags one company > 5 % or the top 10 > 30 %: the deliberate overlap must trip both."""
    prices = store.prices
    values = {p.product_id: p.units * prices.products[p.product_id][-1] for p in store.customer("markus").positions}
    total = sum(values.values())
    exposure: dict[str, float] = {}
    for pid, value in values.items():
        for h in store.product(pid).holdings:
            exposure[h.id] = exposure.get(h.id, 0.0) + h.weight * value / total
    weights = sorted(exposure.values(), reverse=True)
    assert sum(weights) == pytest.approx(1.0, abs=1e-6)
    assert weights[0] > 0.05 and sum(weights[:10]) > 0.30


def test_three_personas_with_profiles(store):
    cs = {c.id: c for c in store.customers}
    assert set(cs) == {"anna", "markus", "elif"}
    assert (cs["anna"].age, cs["markus"].age, cs["elif"].age) == (29, 45, 61)
    assert (cs["anna"].city, cs["markus"].city, cs["elif"].city) == ("Wien", "Graz", "Linz")
    assert (cs["anna"].profile.risk_class, cs["markus"].profile.risk_class, cs["elif"].profile.risk_class) == (3, 4, 2)
    assert cs["elif"].profile.prefers_distribution and not cs["anna"].profile.prefers_distribution
    for c in cs.values():
        p = c.profile
        assert set(p.knowledge) == set(p.experience) == {
            "equity_etf", "equity_fund", "bond_fund", "mixed_fund", "money_market"
        }  # fmt: skip
        assert c.cash_eur > 0 and c.positions


def test_customer_transactions_span_2_to_3_years_and_match_positions(store):
    prices = store.prices
    for c in store.customers:
        dates = [t.date for t in c.transactions]
        months = (max(dates).year - min(dates).year) * 12 + max(dates).month - min(dates).month
        assert 24 <= months <= 36, (c.id, months)
        assert all(t.date <= np.datetime64("2026-08-31").astype(object) for t in c.transactions)
        for pos in c.positions:
            bought = sum(t.units for t in c.transactions if t.product_id == pos.product_id)
            assert pos.units == pytest.approx(bought, abs=1e-3)
        for t in c.transactions:  # units were priced at that day's NAV
            nav = prices.products[t.product_id][prices.index_on_or_after(t.date)]
            assert t.units * nav == pytest.approx(t.amount_eur, rel=1e-3)
        plan = [t for t in c.transactions if t.kind == "sparplan"]
        first = {}
        for t in plan:
            first.setdefault(t.product_id, []).append(t.date)
        assert all(len(v) >= 24 for v in first.values())


def test_markus_holds_the_overlapping_pair(store):
    held = {p.product_id for p in store.customer("markus").positions}
    assert {"P03", "P22"} <= held


# ── determinism and store ───────────────────────────────────────────────────


def test_same_seed_gives_identical_output_hash(built, tmp_path):
    _, _, manifest = built
    again = generate(tmp_path / "again", SEED)
    assert again["hash"] == manifest["hash"]
    assert again["files"] == manifest["files"]  # every file, including the PDFs, is byte-identical


def test_different_seed_gives_different_hash(built, tmp_path):
    other = generate(tmp_path / "other", SEED + 1, pdfs=False)
    assert other["hash"] != built[2]["hash"]


def test_store_reports_missing_data_clearly(tmp_path):
    with pytest.raises(DataMissingError, match="make data"):
        _ = Store(tmp_path / "nothing").products


def test_manifest_lists_all_outputs(built):
    _, out, manifest = built
    assert sum(k.startswith("kid/") for k in manifest["files"]) == 40
    for name in ("companies.json", "products.json", "events.json", "customers.json", "prices_assets.csv",
                 "prices_products.csv", "kid_facts.jsonl", "retrieval.jsonl", "injections.json"):  # fmt: skip
        assert name in manifest["files"] and (out / name).exists()


# ── the August 2026 scenario constraint ─────────────────────────────────────


def test_pin_market_window_sets_the_total_and_keeps_the_long_run_drift():
    dates = np.arange(np.datetime64("2026-01-01"), np.datetime64("2026-12-31"), dtype="datetime64[D]")
    market = np.random.default_rng(3).normal(0.0004, 0.01, len(dates))
    before = market.sum()
    window = (np.datetime64("2026-08-01"), np.datetime64("2026-08-31"))
    pin_market_window(market, dates, window, -0.03)
    inside = (dates >= window[0]) & (dates <= window[1])
    assert market[inside].sum() == pytest.approx(-0.03)
    assert market.sum() == pytest.approx(before)


def test_august_2026_is_a_decline_for_the_market_and_for_markus(store):
    """The demo question is 'Warum ist mein Depot im August gefallen?', so the data has to make it true."""
    assert PIN_WINDOW[0] == np.datetime64("2026-08-01") and PIN_MARKET_TOTAL < 0
    prices = store.prices
    i0, i1 = prices.index_on_or_before("2026-07-31"), prices.index_on_or_before("2026-08-31")
    companies = np.mean([prices.assets[c.id][i1] / prices.assets[c.id][i0] - 1 for c in store.companies])
    assert companies < -0.01
    for pid in ("P03", "P22", "P11"):  # Markus's three products all fell over the month
        nav = prices.products[pid]
        assert nav[i1] < nav[i0], pid
    j0, j1 = prices.index_on_or_before("2026-08-11"), prices.index_on_or_before("2026-08-13")
    tech, world = prices.products["P22"], prices.products["P03"]
    assert tech[j1] / tech[j0] - 1 < world[j1] / world[j0] - 1 < 0  # the chip shock hits tech hardest
