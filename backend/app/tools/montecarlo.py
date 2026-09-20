"""simulate_savings_plan: seeded block-bootstrap Monte Carlo of a monthly savings plan (SPEC §7).

Method
- The portfolio's daily return series is the weighted sum of the chosen products' NAV returns (daily rebalanced,
  fund costs already inside the NAVs).
- Stationary block bootstrap with a mean block length of 20 trading days, discretised to the plan's monthly
  step: a month is 21 trading days, its return is the compounded return of a 21-day window of the history, and the
  next month continues right after the previous window with probability `(1 - 1/20) ** 21` (about 34 %, the chance a
  20-day-mean geometric block survives 21 days), otherwise it restarts at a uniformly random day. The history is
  treated as circular. This keeps the bootstrap fully vectorised (5,000 paths x 30 years in well under 300 ms).
- Each month: contribution (net of entry cost and the per-execution fee) goes in, then the month's return applies.
- Values are read at every year end; percentiles are taken across the 5,000 paths.
- `total_costs` are the explicit costs (fees and entry costs). Fund costs (TER) are already in the returns.
- `kest_estimate` is 27.5 % of the median gain over contributions, simplified.
Deterministic: the seed is fixed, so equal inputs give identical outputs.
"""

import numpy as np

from ..fmt import de_num
from ..schemas.tools import SimulateInput, SimulateOutput
from .base import ToolContext, ToolError

N_PATHS = 5_000
SEED = 20260920
DAYS_PER_MONTH = 21
MEAN_BLOCK_DAYS = 20
P_CONTINUE = (1 - 1 / MEAN_BLOCK_DAYS) ** DAYS_PER_MONTH
KEST_RATE = 0.275
PERCENTILES = (5, 25, 50, 75, 95)


def resolve_weights(inp: SimulateInput, ctx: ToolContext) -> dict[str, float]:
    if (inp.product_ids is None) == (inp.weights is None):
        raise ToolError("invalid", "give exactly one of product_ids (equal weights) or weights")
    if inp.product_ids is not None:
        ids = list(dict.fromkeys(inp.product_ids))
        if not ids:
            raise ToolError("invalid", "product_ids is empty")
        weights = {pid: 1.0 / len(ids) for pid in ids}
    else:
        weights = {}
        for w in inp.weights or []:
            if w.product_id in weights:
                raise ToolError("invalid", f"duplicate product {w.product_id!r} in weights")
            weights[w.product_id] = w.weight
        if abs(sum(weights.values()) - 1.0) > 1e-6:
            raise ToolError("invalid", f"weights must sum to 1, got {sum(weights.values()):.6f}")
    for pid in weights:
        ctx.product(pid)
    return {pid: w for pid, w in weights.items() if w > 0}


def block_log_returns(daily: np.ndarray) -> np.ndarray:
    """Log return of the 21-day window starting at each day (circular history)."""
    log = np.log1p(daily)
    ext = np.concatenate([log, log[:DAYS_PER_MONTH]])
    cum = np.concatenate([[0.0], np.cumsum(ext)])
    n = len(daily)
    return cum[DAYS_PER_MONTH : DAYS_PER_MONTH + n] - cum[:n]


def month_indices(n_days: int, n_paths: int, months: int, rng: np.random.Generator) -> np.ndarray:
    """Start day of each month's 21-day window, shape (paths, months).

    Month 0 starts at a uniform random day. Every later month either continues right after the previous window
    (probability `P_CONTINUE`) or restarts uniformly at random; the history is circular."""
    fresh = rng.integers(0, n_days, size=(n_paths, months))
    keep = rng.random((n_paths, months)) < P_CONTINUE
    keep[:, 0] = False
    month = np.arange(months)
    run_start = np.maximum.accumulate(np.where(keep, 0, month), axis=1)  # month index where the current run began
    base = np.take_along_axis(fresh, run_start, axis=1)
    return (base + (month - run_start) * DAYS_PER_MONTH) % n_days


def month_growth_factors(block_log: np.ndarray, n_paths: int, months: int, rng: np.random.Generator) -> np.ndarray:
    return np.exp(block_log[month_indices(len(block_log), n_paths, months, rng)])


def simulate_savings_plan(inp: SimulateInput, ctx: ToolContext) -> SimulateOutput:
    weights = resolve_weights(inp, ctx)
    prices = ctx.store.prices.products
    daily = sum(w * (prices[pid][1:] / prices[pid][:-1] - 1.0) for pid, w in weights.items())

    months = inp.years * 12
    growth = month_growth_factors(block_log_returns(daily), N_PATHS, months, np.random.default_rng(SEED))

    entry = sum(w * ctx.product(pid).entry_cost for pid, w in weights.items())
    cost_per_month = min(inp.monthly_eur, inp.monthly_eur * entry + len(weights) * inp.fee_per_execution)
    net = inp.monthly_eur - cost_per_month

    value = np.zeros(N_PATHS)
    at_year_end = np.empty((N_PATHS, inp.years))
    for m in range(months):
        value = (value + net) * growth[:, m]
        if (m + 1) % 12 == 0:
            at_year_end[:, (m + 1) // 12 - 1] = value

    pct = np.percentile(at_year_end, PERCENTILES, axis=0)
    total_contributions = inp.monthly_eur * months
    p50_final = float(pct[2, -1])
    return SimulateOutput(
        years=list(range(1, inp.years + 1)),
        p5=[round(float(x), 2) for x in pct[0]],
        p25=[round(float(x), 2) for x in pct[1]],
        p50=[round(float(x), 2) for x in pct[2]],
        p75=[round(float(x), 2) for x in pct[3]],
        p95=[round(float(x), 2) for x in pct[4]],
        contributions=[round(inp.monthly_eur * 12 * y, 2) for y in range(1, inp.years + 1)],
        prob_below_contributions=round(float(np.mean(at_year_end[:, -1] < total_contributions)), 4),
        total_contributions=round(total_contributions, 2),
        total_costs=round(cost_per_month * months, 2),
        kest_estimate=round(KEST_RATE * max(0.0, p50_final - total_contributions), 2),
        n_paths=N_PATHS,
        seed=SEED,
    )


def summarize(out: SimulateOutput, ctx: ToolContext) -> str:
    return (
        f"Nach {out.years[-1]} Jahren: Median {de_num(out.p50[-1])} € "
        f"bei {de_num(out.total_contributions)} € Einzahlungen, 1 von 20 Verläufen unter {de_num(out.p5[-1])} €"
    )
