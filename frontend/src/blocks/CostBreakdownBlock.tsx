import { Card } from '../components/ui'
import { eur, num } from '../lib/format'
import type { CostBreakdownBlock } from '../types/contracts'

const COLORS = ['var(--blue)', '#F0A020', 'var(--navy)']

/** Costs of a savings plan as a split bar with a legend (design/03 "Was kostet dich das?"). */
export function CostBreakdownBlockView({ block, bare = false }: { block: CostBreakdownBlock; bare?: boolean }) {
  const sum = block.rows.reduce((s, r) => s + r.amount_eur, 0) || 1
  const Wrapper = bare ? 'div' : Card
  return (
    <Wrapper className="space-y-3" data-testid="block-cost-breakdown">
      {!bare && <h3 className="text-[17px] font-bold text-navy">Was kostet dich das?</h3>}
      <div>
        <div className="text-[36px] font-extrabold leading-none tracking-wide text-navy">{eur(block.total)}</div>
        {block.total_pct_of_contributions !== null && (
          <p className="mt-1 text-[15px] text-ink-2">{num(block.total_pct_of_contributions, 1)} % deiner Einzahlungen</p>
        )}
      </div>
      <div className="flex h-3 overflow-hidden rounded-full bg-ground" role="img" aria-label="Aufteilung der Kosten">
        {block.rows.map((r, i) => (
          <div key={r.label} style={{ width: `${(r.amount_eur / sum) * 100}%`, background: COLORS[i % COLORS.length] }} />
        ))}
      </div>
      <ul className="space-y-2">
        {block.rows.map((r, i) => (
          <li key={r.label} className="flex items-center justify-between gap-3 text-[15px]">
            <span className="flex min-w-0 items-center gap-2 text-navy">
              <span className="size-3 shrink-0 rounded-[3px]" style={{ background: COLORS[i % COLORS.length] }} />
              {r.label}
            </span>
            <span className="shrink-0 whitespace-nowrap font-bold text-navy">{eur(r.amount_eur)}</span>
          </li>
        ))}
      </ul>
    </Wrapper>
  )
}
