"""portfolio_lookthrough: what a customer's products actually contain (SPEC §7).

Position weights come from units x the latest NAV. Exposure of a holding is
`sum over products of position_weight * holding_weight`. Overlap of two products is `sum of min(w_a, w_b)` over
the holdings they share, from the products' own holding weights (independent of how much the customer holds).
Holdings are companies plus, for bond, money-market and mixed funds, the synthetic issuers.
"""

from itertools import combinations

from ..fmt import de_pct
from ..schemas.tools import ExposureRow, LookthroughInput, LookthroughOutput, OverlapPair
from .base import ToolContext

SINGLE_COMPANY_LIMIT = 0.05
TOP10_LIMIT = 0.30


def _rows(weights: dict[str, float], labels: dict[str, str]) -> list[ExposureRow]:
    ordered = sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))
    return [ExposureRow(key=k, label=labels[k], weight=min(1.0, round(w, 10))) for k, w in ordered if w > 0]


def position_weights(customer, ctx: ToolContext) -> dict[str, float]:
    """Share of the invested value per product, at the latest price date."""
    nav = ctx.store.prices.products
    values = {p.product_id: p.units * float(nav[p.product_id][-1]) for p in customer.positions if p.units > 0}
    total = sum(values.values())
    return {pid: v / total for pid, v in values.items()} if total > 0 else {}


def portfolio_lookthrough(inp: LookthroughInput, ctx: ToolContext) -> LookthroughOutput:
    customer = ctx.customer(inp.customer_id)
    weights = position_weights(customer, ctx)
    products = {pid: ctx.product(pid) for pid in sorted(weights)}

    by_company: dict[str, float] = {}
    by_sector: dict[str, float] = {}
    by_country: dict[str, float] = {}
    names: dict[str, str] = {}
    for pid, pw in weights.items():
        for h in products[pid].holdings:
            share = pw * h.weight
            by_company[h.id] = by_company.get(h.id, 0.0) + share
            by_sector[h.sector] = by_sector.get(h.sector, 0.0) + share
            by_country[h.country] = by_country.get(h.country, 0.0) + share
            names[h.id] = h.name

    overlaps = []
    for a, b in combinations(products, 2):
        wa = {h.id: h.weight for h in products[a].holdings}
        wb = {h.id: h.weight for h in products[b].holdings}
        shared = sum(min(wa[i], wb[i]) for i in wa.keys() & wb.keys())
        overlaps.append(OverlapPair(product_a=a, product_b=b, overlap=min(1.0, round(shared, 10))))

    ranked = sorted(by_company.values(), reverse=True)
    top10 = sum(ranked[:10])
    flags = []
    if ranked and ranked[0] > SINGLE_COMPANY_LIMIT:
        flags.append("single_company_over_5pct")
    if top10 > TOP10_LIMIT:
        flags.append("top10_over_30pct")
    return LookthroughOutput(
        customer_id=customer.id,
        n_products=len(products),
        n_companies=len(by_company),
        by_company=_rows(by_company, names),
        by_sector=_rows(by_sector, {k: k for k in by_sector}),
        by_country=_rows(by_country, {k: k for k in by_country}),
        overlaps=overlaps,
        hhi=round(sum(w * w for w in by_company.values()), 10),
        top10_share=round(top10, 10),
        flags=flags,
    )


def summarize(out: LookthroughOutput, ctx: ToolContext) -> str:
    return f"{out.n_products} Produkte, {out.n_companies} Positionen, Top 10 = {de_pct(out.top10_share, 1)}" + (
        f", Hinweise: {', '.join(out.flags)}" if out.flags else ""
    )
