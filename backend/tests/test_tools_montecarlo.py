"""M4 tool, third group: simulate_savings_plan (seeded block-bootstrap Monte Carlo)."""

import time

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.schemas.tools import ProductWeight, SimulateInput
from app.tools.base import ToolError
from app.tools.montecarlo import (
    DAYS_PER_MONTH,
    N_PATHS,
    P_CONTINUE,
    SEED,
    block_log_returns,
    month_indices,
    simulate_savings_plan,
)

SLOW = settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])


def _sim(ctx, monthly=50.0, years=20, ids=("P03",), weights=None, fee=1.0):
    return simulate_savings_plan(
        SimulateInput(
            monthly_eur=monthly,
            years=years,
            product_ids=None if weights else list(ids),
            weights=weights,
            fee_per_execution=fee,
        ),
        ctx,
    )


# ── output shape and basic sanity ───────────────────────────────────────────


def test_fifty_euro_twenty_years_in_p03(ctx):
    out = _sim(ctx)
    assert out.years == list(range(1, 21)) and (out.n_paths, out.seed) == (5000, 20260920)
    assert out.total_contributions == 12_000.0 and out.contributions[-1] == 12_000.0
    assert out.contributions[0] == 600.0
    assert out.total_costs == 240.0  # 1 EUR fee x 240 monthly executions, ETF without entry cost
    assert out.p5[-1] < out.p25[-1] < out.p50[-1] < out.p75[-1] < out.p95[-1]
    assert out.p50[-1] > out.total_contributions  # equities grew over the simulated history
    assert 0 <= out.prob_below_contributions < 0.5
    assert out.kest_estimate == pytest.approx(0.275 * (out.p50[-1] - out.total_contributions), abs=0.01)


def test_riskier_products_have_a_wider_fan(ctx):
    def spread(pid):
        o = _sim(ctx, years=10, ids=(pid,))
        return o.p95[-1] / o.p5[-1]

    assert spread("P39") < spread("P33") < spread("P03") < spread("P32")  # money market < bonds < world < tech fund


def test_money_market_barely_moves_and_never_loses(ctx):
    out = _sim(ctx, years=5, ids=("P39",))
    assert out.prob_below_contributions < 0.05
    assert out.p95[-1] / out.p5[-1] < 1.05


def test_median_grows_with_the_horizon(ctx):
    out = _sim(ctx, years=30)
    assert out.p50 == sorted(out.p50)
    assert out.contributions == sorted(out.contributions)


def test_kest_is_zero_without_a_gain(ctx):
    out = _sim(ctx, years=1, ids=("P39",), fee=50.0)  # fees eat the tiny money market return
    assert out.p50[-1] < out.total_contributions and out.kest_estimate == 0.0


def test_costs_include_fees_per_product_and_entry_costs(ctx):
    two = _sim(ctx, monthly=100, years=5, ids=("P03", "P07"))
    assert two.total_costs == 2 * 60 * 1.0  # one fee per product and month
    fund = _sim(ctx, monthly=100, years=5, ids=("P25",))  # active fund, 4 % entry cost
    assert fund.total_costs == pytest.approx(60 * (100 * 0.04 + 1.0))
    free = _sim(ctx, monthly=100, years=5, ids=("P25",), fee=0.0)
    assert free.total_costs == pytest.approx(60 * 4.0) and free.p50[-1] > fund.p50[-1]


def test_explicit_weights_blend_the_products(ctx):
    mix = _sim(
        ctx,
        years=15,
        weights=[ProductWeight(product_id="P03", weight=0.5), ProductWeight(product_id="P33", weight=0.5)],
    )
    equity = _sim(ctx, years=15, ids=("P03",))
    bonds = _sim(ctx, years=15, ids=("P33",))
    assert bonds.p50[-1] < mix.p50[-1] < equity.p50[-1]
    assert mix.p95[-1] / mix.p5[-1] < equity.p95[-1] / equity.p5[-1]


def test_equal_weights_from_product_ids_match_explicit_weights(ctx):
    a = _sim(ctx, ids=("P03", "P33"), years=5)
    b = _sim(
        ctx, years=5, weights=[ProductWeight(product_id="P03", weight=0.5), ProductWeight(product_id="P33", weight=0.5)]
    )
    assert a == b
    assert _sim(ctx, ids=("P03", "P03"), years=5) == _sim(ctx, ids=("P03",), years=5)  # duplicates collapse


# ── input validation ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kwargs",
    [
        {"product_ids": None, "weights": None},
        {"product_ids": ["P03"], "weights": [ProductWeight(product_id="P03", weight=1.0)]},
        {"product_ids": []},
        {"product_ids": None, "weights": [ProductWeight(product_id="P03", weight=0.6)]},
        {
            "product_ids": None,
            "weights": [ProductWeight(product_id="P03", weight=0.5), ProductWeight(product_id="P03", weight=0.5)],
        },
    ],
)
def test_invalid_product_selection_is_rejected(ctx, kwargs):
    with pytest.raises(ToolError) as e:
        simulate_savings_plan(SimulateInput(monthly_eur=50, years=5, **kwargs), ctx)
    assert e.value.code == "invalid"


def test_unknown_product(ctx):
    with pytest.raises(ToolError) as e:
        _sim(ctx, ids=("P99",))
    assert e.value.code == "not_found"


# ── determinism ─────────────────────────────────────────────────────────────


def test_same_inputs_give_identical_output(ctx):
    assert _sim(ctx) == _sim(ctx)
    assert _sim(ctx).model_dump_json() == _sim(ctx).model_dump_json()


def test_different_inputs_give_different_output(ctx):
    assert _sim(ctx, monthly=50) != _sim(ctx, monthly=51)
    assert _sim(ctx, ids=("P03",)) != _sim(ctx, ids=("P22",))


@SLOW
@given(
    monthly=st.floats(5, 3000),
    years=st.integers(1, 40),
    ids=st.lists(st.sampled_from([f"P{i:02d}" for i in range(1, 41)]), min_size=1, max_size=4, unique=True),
    fee=st.floats(0, 5),
)
def test_property_percentiles_are_monotonic_and_the_run_is_deterministic(ctx, monthly, years, ids, fee):
    out = _sim(ctx, monthly, years, ids, fee=fee)
    for y in range(years):
        assert out.p5[y] <= out.p25[y] <= out.p50[y] <= out.p75[y] <= out.p95[y]
        assert out.p5[y] >= 0
    assert len(out.years) == len(out.p50) == len(out.contributions) == years
    assert out.contributions == sorted(out.contributions)
    assert 0 <= out.prob_below_contributions <= 1 and out.total_costs >= 0 and out.kest_estimate >= 0
    assert out == _sim(ctx, monthly, years, ids, fee=fee)


@SLOW
@given(
    years=st.integers(1, 25),
    raw=st.lists(st.floats(0.01, 1.0), min_size=2, max_size=4),
)
def test_property_explicit_weights_that_sum_to_one_are_accepted(ctx, years, raw):
    total = sum(raw)
    weights = [ProductWeight(product_id=f"P{i + 3:02d}", weight=w / total) for i, w in enumerate(raw)]
    out = _sim(ctx, years=years, weights=weights)
    assert out.p50[-1] > 0


# ── the bootstrap itself ────────────────────────────────────────────────────


def test_block_log_returns_are_compounded_21_day_windows_with_wraparound():
    rng = np.random.default_rng(1)
    daily = rng.normal(0.0004, 0.01, 60)
    block = block_log_returns(daily)
    assert len(block) == 60
    for s in (0, 7, 45, 59):  # 45 and 59 wrap around the end of the history
        window = [daily[(s + k) % 60] for k in range(DAYS_PER_MONTH)]
        assert block[s] == pytest.approx(np.log(np.prod(1 + np.array(window))))


def test_months_continue_the_previous_window_with_the_stationary_probability():
    n_days, paths, months = 1000, 4000, 60
    idx = month_indices(n_days, paths, months, np.random.default_rng(SEED))
    assert idx.shape == (paths, months) and idx.min() >= 0 and idx.max() < n_days
    continues = idx[:, 1:] == (idx[:, :-1] + DAYS_PER_MONTH) % n_days
    assert continues.mean() == pytest.approx(P_CONTINUE, abs=0.01)  # about 34 %: mean block length 20 days
    assert P_CONTINUE == pytest.approx(0.95**21)
    restarts = idx[:, 1:][~continues]
    assert restarts.min() >= 0 and len(np.unique(restarts)) > 900  # restarts cover the whole history


def test_bootstrap_starts_are_spread_uniformly():
    idx = month_indices(500, 5000, 12, np.random.default_rng(SEED))[:, 0]
    counts = np.bincount(idx, minlength=500)
    assert counts.min() > 0 and counts.max() < 30  # mean 10 per day


# ── performance ─────────────────────────────────────────────────────────────


def test_5000_paths_over_30_years_take_under_300_ms(ctx):
    _sim(ctx, years=30)  # warm-up: price arrays are already parsed, but numpy caches are cold
    timings = []
    for _ in range(5):
        t = time.perf_counter()
        out = _sim(ctx, years=30, ids=("P03", "P22", "P33"))
        timings.append((time.perf_counter() - t) * 1000)
    assert out.n_paths == N_PATHS == 5000 and out.years[-1] == 30
    assert min(timings) < 300, f"best of 5: {min(timings):.0f} ms, all: {[round(x) for x in timings]}"
