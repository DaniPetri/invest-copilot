"""suitability_check: rule-based MiFID-style fit of a product to a customer's profile (SPEC §7).

Rules (each yields pass / warn / fail with a reason that names the profile field it looked at):
- risk:          customer risk class 1-5 against the product's SRI 1-7 (`MAX_SRI_BY_RISK_CLASS`)
- knowledge:     required level by product complexity against `profile.knowledge[asset_class]`
- experience:    the same against `profile.experience[asset_class]`
- horizon:       `profile.horizon_years` against the recommended holding period
- sustainability: `profile.sustainability_preference` against the SFDR article
The verdict is the worst of the individual results.
"""

from ..schemas.portfolio import Customer
from ..schemas.products import Product
from ..schemas.tools import SuitabilityInput, SuitabilityOutput, SuitabilityReason, Verdict
from .base import ToolContext

# Highest SRI that fits a risk class without a warning.
MAX_SRI_BY_RISK_CLASS = {1: 2, 2: 3, 3: 4, 4: 5, 5: 7}

LEVEL_RANK = {"keine": 0, "basis": 1, "erweitert": 2}
TYPE_PLURAL_DE = {
    "equity_etf": "Aktien-ETFs",
    "equity_fund": "Aktienfonds",
    "bond_fund": "Anleihenfonds",
    "mixed_fund": "Mischfonds",
    "money_market": "Geldmarktfonds",
}
KNOWLEDGE_DE = {"keine": "keine Vorkenntnisse", "basis": "Grundkenntnisse", "erweitert": "erweiterte Kenntnisse"}
EXPERIENCE_DE = {"keine": "keine Erfahrung", "basis": "etwas Erfahrung", "erweitert": "viel Erfahrung"}
PREFERENCE_DE = {"art8": "ein nachhaltiges Produkt (mindestens Artikel 8)", "art9": "ein Produkt nach Artikel 9"}
_SEVERITY = {"pass": 0, "warn": 1, "fail": 2}


def _status_from_deficit(deficit: int) -> Verdict:
    return "pass" if deficit <= 0 else "warn" if deficit == 1 else "fail"


def required_knowledge(p: Product) -> str:
    if p.asset_class == "money_market":
        return "keine"
    return "erweitert" if p.replication == "synthetisch" or p.sri >= 6 else "basis"


def required_experience(p: Product) -> str:
    if p.replication == "synthetisch" or p.sri >= 6 or p.asset_class in ("equity_fund", "mixed_fund"):
        return "basis"
    return "keine"


def check_risk(c: Customer, p: Product) -> SuitabilityReason:
    rc, limit = c.profile.risk_class, MAX_SRI_BY_RISK_CLASS[c.profile.risk_class]
    status = _status_from_deficit(p.sri - limit)
    base = f"Deine Risikoklasse ist {rc} von 5. Das Produkt hat Risikostufe {p.sri} von 7"
    text = {
        "pass": f"{base} und liegt damit im passenden Bereich (bis Stufe {limit}).",
        "warn": f"{base}, eine Stufe über dem, was zu deiner Risikoklasse passt (bis Stufe {limit}).",
        "fail": f"{base}, deutlich über dem, was zu deiner Risikoklasse passt (bis Stufe {limit}).",
    }[status]
    return SuitabilityReason(rule="risk", status=status, text=text, profile_field="risk_class")


def check_knowledge(c: Customer, p: Product) -> SuitabilityReason:
    need, have = required_knowledge(p), c.profile.knowledge[p.asset_class]
    status = _status_from_deficit(LEVEL_RANK[need] - LEVEL_RANK[have])
    text = (
        f"Für {TYPE_PLURAL_DE[p.asset_class]} sind {KNOWLEDGE_DE[need]} nötig. "
        f"Bei dir ist eingetragen: {KNOWLEDGE_DE[have]}."
    )
    return SuitabilityReason(rule="knowledge", status=status, text=text, profile_field=f"knowledge.{p.asset_class}")


def check_experience(c: Customer, p: Product) -> SuitabilityReason:
    need, have = required_experience(p), c.profile.experience[p.asset_class]
    status = _status_from_deficit(LEVEL_RANK[need] - LEVEL_RANK[have])
    text = (
        f"Für {TYPE_PLURAL_DE[p.asset_class]} ist {EXPERIENCE_DE[need]} nötig. "
        f"Bei dir ist eingetragen: {EXPERIENCE_DE[have]}."
    )
    return SuitabilityReason(rule="experience", status=status, text=text, profile_field=f"experience.{p.asset_class}")


def check_horizon(c: Customer, p: Product) -> SuitabilityReason:
    h, rhp = c.profile.horizon_years, p.recommended_holding_years
    status: Verdict = "pass" if h >= rhp else "warn" if h * 2 >= rhp else "fail"
    text = f"Die empfohlene Haltedauer beträgt {rhp} Jahre. Dein Anlagehorizont: {h} Jahre."
    return SuitabilityReason(rule="horizon", status=status, text=text, profile_field="horizon_years")


def check_sustainability(c: Customer, p: Product) -> SuitabilityReason:
    pref = c.profile.sustainability_preference
    field = "sustainability_preference"
    if pref == "keine":
        return SuitabilityReason(
            rule="sustainability",
            status="pass",
            text="Du hast keine Nachhaltigkeitspräferenz angegeben.",
            profile_field=field,
        )
    wanted = 8 if pref == "art8" else 9
    met = p.sfdr >= wanted
    # Art. 9 wanted but Art. 6 offered is a clear miss; every other gap is a warning.
    status: Verdict = "pass" if met else "fail" if (wanted == 9 and p.sfdr == 6) else "warn"
    text = f"Du wünschst dir {PREFERENCE_DE[pref]}. Das Produkt ist nach Artikel {p.sfdr} eingestuft."
    return SuitabilityReason(rule="sustainability", status=status, text=text, profile_field=field)


def suitability_check(inp: SuitabilityInput, ctx: ToolContext) -> SuitabilityOutput:
    c, p = ctx.customer(inp.customer_id), ctx.product(inp.product_id)
    reasons = [
        check_risk(c, p),
        check_knowledge(c, p),
        check_experience(c, p),
        check_horizon(c, p),
        check_sustainability(c, p),
    ]
    verdict = max((r.status for r in reasons), key=lambda s: _SEVERITY[s])
    return SuitabilityOutput(customer_id=c.id, product_id=p.id, verdict=verdict, reasons=reasons)


def summarize(out: SuitabilityOutput, ctx: ToolContext) -> str:
    counts = {s: sum(r.status == s for r in out.reasons) for s in ("pass", "warn", "fail")}
    return f"Ergebnis {out.verdict}: {counts['pass']} passt, {counts['warn']} Hinweis, {counts['fail']} passt nicht"
