import { Check, Code2 } from 'lucide-react'
import { Link } from 'react-router'
import { KiLabel } from '../components/ui'
import { SriBars } from '../components/SriScale'
import { cn, eur, pct } from '../lib/format'
import { useSession } from '../state/session'
import type { AssetClass, ProductCardsBlock, ScreenItem } from '../types/contracts'

export const ASSET_CLASS_LABEL: Record<AssetClass, string> = {
  equity_etf: 'Aktien-ETF',
  equity_fund: 'Aktienfonds',
  bond_fund: 'Anleihenfonds',
  mixed_fund: 'Mischfonds',
  money_market: 'Geldmarktfonds',
}

export function ProductCard({ item }: { item: ScreenItem }) {
  return (
    <Link
      to={`/produkt/${item.product_id}`}
      className="block rounded-[20px] bg-card p-4 shadow-[var(--shadow-card)]"
      data-testid="product-card"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-[17px] font-bold leading-snug text-navy">{item.name}</h3>
        <span
          className={cn(
            'shrink-0 rounded-[10px] px-2 py-1 text-[13px] font-bold',
            item.sfdr >= 8 ? 'bg-green-soft text-green' : 'bg-ground text-ink-2',
          )}
        >
          Art. {item.sfdr}
        </span>
      </div>
      <p className="mt-0.5 text-[15px] text-muted">
        {ASSET_CLASS_LABEL[item.asset_class]} {item.region}, {item.distribution}
      </p>
      <dl className="mt-3 grid grid-cols-[auto_1fr_1fr] items-end gap-x-4 text-[13px] text-muted">
        <div>
          <dt>Risiko</dt>
          <dd className="mt-1.5">
            <SriBars sri={item.sri} />
          </dd>
        </div>
        <div>
          <dt>Kosten</dt>
          <dd className="mt-0.5 whitespace-nowrap text-[15px] font-semibold text-navy">{pct(item.ter, 2)} p. a.</dd>
        </div>
        <div>
          <dt>Sparplan</dt>
          <dd className="mt-0.5 text-[15px] font-semibold text-navy">
            {item.savings_plan_min_eur ? `ab ${eur(item.savings_plan_min_eur)}` : 'nicht möglich'}
          </dd>
        </div>
      </dl>
      {item.why_matched.length > 0 && (
        <p className="mt-3 rounded-[12px] bg-green-soft px-3 py-2 text-[13px] leading-snug text-green">
          Passt, weil: {item.why_matched.join(' · ')}
        </p>
      )}
    </Link>
  )
}

/** "Das habe ich verstanden" filter chips plus the result list (design/02). */
export function ProductCardsBlockView({ block }: { block: ProductCardsBlock }) {
  const { setTraceSheetOpen } = useSession()
  return (
    <div className="space-y-3" data-testid="block-product-cards">
      {block.filters.length > 0 && (
        <section aria-label="Das habe ich verstanden" className="space-y-3">
          <h2 className="flex items-center gap-2 text-[17px] font-bold text-navy">
            <KiLabel />
            Das habe ich verstanden
          </h2>
          <ul className="flex flex-wrap gap-2">
            {block.filters.map((f, i) => (
              <li
                key={f.key}
                style={{ animationDelay: `${i * 60}ms` }}
                className="animate-[pop_.25s_ease-out_both] inline-flex min-h-11 items-center gap-2 rounded-full border border-blue/25 bg-blue-soft px-4 text-[15px] font-medium text-blue-ink"
              >
                <Check size={16} aria-hidden="true" />
                {f.label}
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => setTraceSheetOpen(true)}
            className="inline-flex min-h-11 items-center gap-2 rounded-[14px] border border-line bg-white px-4 text-[15px] font-semibold text-navy min-[1100px]:hidden"
          >
            <Code2 size={18} aria-hidden="true" />
            Unter der Haube: strukturierte Ausgabe
          </button>
        </section>
      )}
      <div className="flex items-baseline justify-between pt-1">
        <h2 className="text-[22px] font-bold text-navy">
          {block.total_matches ?? block.items.length} Treffer
        </h2>
        <span className="text-[15px] text-muted">nach Kosten sortiert</span>
      </div>
      <div className="space-y-3">
        {block.items.map((item) => (
          <ProductCard key={item.product_id} item={item} />
        ))}
      </div>
      <p className="px-1 text-[13px] text-muted">Tippe auf ein Produkt für die Kurzinfo.</p>
    </div>
  )
}
