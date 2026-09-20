"""screen_products: filter and sort the 40 products (SPEC §7)."""

from ..fmt import de_num, de_pct
from ..schemas.products import Product
from ..schemas.tools import ScreenInput, ScreenItem, ScreenOutput
from .base import ToolContext

ASSET_CLASS_LABEL = {
    "equity_etf": "Aktien-ETF",
    "equity_fund": "Aktienfonds",
    "bond_fund": "Anleihenfonds",
    "mixed_fund": "Mischfonds",
    "money_market": "Geldmarktfonds",
}
_EPS = 1e-12

SORT_KEYS = {
    "ter": lambda p: (p.ter, p.id),
    "sri": lambda p: (p.sri, p.ter, p.id),
    "fund_size": lambda p: (-p.fund_size_eur_m, p.id),
    "name": lambda p: (p.name.lower(), p.id),
}


def why_matched(p: Product, f) -> list[str] | None:
    """The reasons `p` satisfies every active filter, or None when it fails one. Inactive filters add nothing.

    Empty lists and `savings_plan=False` count as "no filter": models often send them to mean "don't care".
    """
    reasons: list[str] = []
    if f.asset_classes:
        if p.asset_class not in f.asset_classes:
            return None
        reasons.append(f"Typ: {ASSET_CLASS_LABEL[p.asset_class]}")
    if f.savings_plan:
        if p.savings_plan_min_eur is None:
            return None
        reasons.append(f"Sparplan ab {de_num(p.savings_plan_min_eur)} €")
    if f.regions:
        if p.region not in f.regions:
            return None
        reasons.append(f"Region: {p.region}")
    if f.sfdr_min is not None:
        if p.sfdr < f.sfdr_min:
            return None
        reasons.append(f"Nachhaltig: Art. {p.sfdr}")
    if f.exclusions:
        if not set(f.exclusions) <= set(p.exclusions):
            return None
        reasons.append("ohne " + ", ".join(f.exclusions))
    if f.max_sri is not None:
        if p.sri > f.max_sri:
            return None
        reasons.append(f"Risiko {p.sri}/7")
    if f.max_ter is not None:
        if p.ter > f.max_ter + _EPS:
            return None
        reasons.append(f"Kosten {de_pct(p.ter)} p. a.")
    if f.distribution is not None:
        if p.distribution != f.distribution:
            return None
        reasons.append(p.distribution.capitalize())
    return reasons


def screen_products(inp: ScreenInput, ctx: ToolContext) -> ScreenOutput:
    matches: list[tuple[Product, list[str]]] = []
    for p in ctx.store.products:
        reasons = why_matched(p, inp.filter)
        if reasons is not None:
            matches.append((p, reasons))
    matches.sort(key=lambda m: SORT_KEYS[inp.sort](m[0]))
    items = [
        ScreenItem(
            product_id=p.id,
            name=p.name,
            isin=p.isin,
            asset_class=p.asset_class,
            region=p.region,
            sfdr=p.sfdr,
            sri=p.sri,
            ter=p.ter,
            distribution=p.distribution,
            savings_plan_min_eur=p.savings_plan_min_eur,
            why_matched=reasons,
        )
        for p, reasons in matches[: inp.limit]
    ]
    return ScreenOutput(total_matches=len(matches), items=items)


def summarize(out: ScreenOutput, ctx: ToolContext) -> str:
    return f"{out.total_matches} von {len(ctx.store.products)} Produkten passen"
