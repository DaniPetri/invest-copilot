"""cost_projection: what a savings plan costs, year by year (SPEC §7).

Model (no market-return assumption, so the numbers are simple and reproducible):
- Contributions are made at the start of each month, and the balance is the sum of contributions so far.
- The TER is charged on the average balance of the year: `start + 6.5 * monthly` (12 contributions at month start).
- The savings plan fee is charged once per monthly execution.
- The entry cost is charged on every contribution.
Check against design/03: 50 EUR a month for 10 years at 0.15 % TER gives 45 EUR fund costs and 120 EUR fees
(2.8 % of 6,000 EUR of contributions).
"""

from ..fmt import de_num, de_pct
from ..schemas.tools import CostProjectionInput, CostProjectionOutput, CostRow, CostYear
from .base import ToolContext

AVERAGE_MONTHS_HELD = 6.5  # mean of 1..12: each of the 12 contributions sits in the fund for the rest of the year


def cost_projection(inp: CostProjectionInput, ctx: ToolContext) -> CostProjectionOutput:
    p = ctx.product(inp.product_id)
    m = inp.monthly_eur
    by_year: list[CostYear] = []
    cumulative = ter_total = fee_total = entry_total = 0.0
    for year in range(1, inp.years + 1):
        start_balance = 12 * m * (year - 1)
        ter = p.ter * (start_balance + AVERAGE_MONTHS_HELD * m)
        fees = 12 * inp.fee_per_execution
        entry = p.entry_cost * 12 * m
        cumulative += ter + fees + entry
        ter_total, fee_total, entry_total = ter_total + ter, fee_total + fees, entry_total + entry
        by_year.append(
            CostYear(
                year=year,
                ter_eur=round(ter, 2),
                fees_eur=round(fees, 2),
                entry_eur=round(entry, 2),
                cumulative_eur=round(cumulative, 2),
            )
        )

    contributions = 12 * m * inp.years
    fee_label = de_num(inp.fee_per_execution, 0 if float(inp.fee_per_execution).is_integer() else 2)
    rows = [
        CostRow(label=f"Laufende Fondskosten ({de_pct(p.ter)} p. a.)", amount_eur=round(ter_total, 2)),
        CostRow(label=f"Sparplan-Entgelt ({fee_label} € je Rate)", amount_eur=round(fee_total, 2)),
    ]
    if p.entry_cost > 0:
        rows.append(CostRow(label=f"Einstiegskosten ({de_pct(p.entry_cost)})", amount_eur=round(entry_total, 2)))
    total = round(ter_total + fee_total + entry_total, 2)
    return CostProjectionOutput(
        product_id=p.id,
        total_contributions_eur=round(contributions, 2),
        by_year=by_year,
        rows=rows,
        total_eur=total,
        total_pct_of_contributions=round(total / contributions * 100, 2),
    )


def summarize(out: CostProjectionOutput, ctx: ToolContext) -> str:
    return (
        f"Kosten gesamt {de_num(out.total_eur, 2)} € "
        f"({de_num(out.total_pct_of_contributions, 1)} % von {de_num(out.total_contributions_eur)} € Einzahlungen)"
    )
