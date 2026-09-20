import { ArrowLeft, FileText } from 'lucide-react'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { ASSET_CLASS_LABEL } from '../blocks/ProductCardsBlock'
import { CostBreakdownBlockView } from '../blocks/CostBreakdownBlock'
import { SuitabilityBlockView } from '../blocks/SuitabilityBlock'
import { SRI_WORDS, SriScale } from '../components/SriScale'
import { Card, ChoiceButtons, Disclaimer, ErrorNote, Skeleton, SourceBadge } from '../components/ui'
import { api } from '../lib/api'
import { eur, pct, topHoldings } from '../lib/format'
import { RATES } from '../lib/mixes'
import { useLoad } from '../lib/useLoad'
import { usePersona } from '../state/persona'

const HORIZON_YEARS = 10

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5">
      <dt className="text-[15px] text-muted">{label}</dt>
      <dd className="text-right text-[15px] font-semibold text-navy">{value}</dd>
    </div>
  )
}

/** Kurzinfo: the KID in plain German, the cost calculator (direct tool call) and the fit for the current persona. */
export function ProductScreen() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { current } = usePersona()
  const [rate, setRate] = useState<number>(50)

  const product = useLoad(id, () => api.getProduct(id))
  const cost = useLoad(`${id}|${rate}`, () => api.costProjection(id, rate, HORIZON_YEARS))
  const fit = useLoad(current ? `${current.id}|${id}` : null, () => api.suitability(current!.id, id))
  const p = product.data
  const c = cost.data?.payload

  return (
    <div className="pb-4">
      <header className="flex min-h-11 items-center gap-3 px-4 pt-[max(16px,env(safe-area-inset-top))]">
        <button type="button" aria-label="Zurück" onClick={() => navigate(-1)} className="grid size-11 shrink-0 place-items-center rounded-full bg-white shadow-[var(--shadow-card)]">
          <ArrowLeft size={22} aria-hidden="true" />
        </button>
        <h1 className="flex-1 pr-11 text-center text-[17px] font-bold text-navy">Kurzinfo</h1>
      </header>

      <div className="space-y-3 px-4 pt-3">
        {product.error && <ErrorNote message={product.error} />}
        {!p && !product.error && <Skeleton className="h-40 bg-white" />}
        {p && (
          <>
            <Card tone="blue" className="space-y-3 p-5" data-testid="product-hero">
              <p className="text-[15px] font-semibold opacity-90">Aus dem Basisinformationsblatt</p>
              <h2 className="text-[28px] font-extrabold leading-tight">{p.name}</h2>
              <ul className="flex flex-wrap gap-2">
                {[
                  `Art. ${p.sfdr}`,
                  p.distribution,
                  p.replication === 'aktiv' ? 'aktiv verwaltet' : `${p.replication} repliziert`,
                  p.savings_plan_min_eur ? 'Sparplan-fähig' : 'kein Sparplan',
                ].map((t) => (
                  <li key={t} className="rounded-full bg-white/20 px-3 py-1.5 text-[15px] font-semibold">
                    {t}
                  </li>
                ))}
              </ul>
            </Card>

            <Card className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-[22px] font-extrabold text-navy">Wie riskant?</h2>
                <SourceBadge productId={p.id} page={1} href={api.kidUrl(p.id, 1)} />
              </div>
              <SriScale sri={p.sri} />
              <p className="text-[17px] leading-snug text-ink-2">
                Stufe {p.sri} von 7 laut Hersteller, also {SRI_WORDS[p.sri]}. Der Wert kann deutlich schwanken, Verluste
                sind möglich.
              </p>
            </Card>

            <Card className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-[22px] font-extrabold text-navy">Was kostet dich das?</h2>
                <SourceBadge productId={p.id} page={2} href={api.kidUrl(p.id, 2)} />
              </div>
              <div>
                <p className="mb-2 text-[15px] text-muted">Monatliche Rate</p>
                <ChoiceButtons
                  label="Monatliche Rate"
                  value={rate}
                  onChange={setRate}
                  options={RATES.map((r) => ({ value: r as number, label: eur(r) }))}
                />
              </div>
              {cost.error && <ErrorNote message={cost.error} />}
              {c ? (
                <div className="space-y-3" aria-live="polite" data-testid="cost-result">
                  <p className="text-[15px] text-muted">Über {HORIZON_YEARS} Jahre ungefähr</p>
                  <CostBreakdownBlockView bare block={{ type: 'cost_breakdown', rows: c.rows, total: c.total_eur, total_pct_of_contributions: c.total_pct_of_contributions }} />
                  <p className="text-[15px] leading-snug text-ink-2">
                    Bei {eur(c.total_contributions_eur)} Einzahlungen. Das Entgelt pro Ausführung ist fix, bei kleinen Raten fällt es
                    stärker ins Gewicht.
                  </p>
                </div>
              ) : (
                !cost.error && <Skeleton className="h-32 bg-ground" />
              )}
            </Card>

            {fit.data && (
              <div data-testid="product-fit">
                <p className="mb-2 px-1 text-[15px] font-semibold text-muted">Für {current?.name}</p>
                <SuitabilityBlockView block={{ type: 'suitability', verdict: fit.data.payload.verdict, reasons: fit.data.payload.reasons }} />
              </div>
            )}
            {fit.error && <ErrorNote message={fit.error} />}

            <Card className="space-y-1">
              <h2 className="text-[17px] font-bold text-navy">Eckdaten</h2>
              <dl className="divide-y divide-line">
                <Fact label="Produktart" value={ASSET_CLASS_LABEL[p.asset_class]} />
                <Fact label="Laufende Kosten" value={`${pct(p.ter, 2)} p. a.`} />
                <Fact label="Einstiegskosten" value={pct(p.entry_cost, 2)} />
                <Fact label="Empfohlene Haltedauer" value={`${p.recommended_holding_years} Jahre`} />
                <Fact label="Ertragsverwendung" value={p.distribution} />
                <Fact label="Ausgeschlossen" value={p.exclusions.length ? p.exclusions.join(', ') : 'keine Ausschlüsse'} />
                <Fact label="Vergleichsindex" value={p.benchmark} />
                <Fact label="Emittent" value={p.issuer} />
                <Fact label="ISIN" value={p.isin} />
              </dl>
              <a
                href={api.kidUrl(p.id)}
                target="_blank"
                rel="noreferrer"
                className="mt-2 flex min-h-11 items-center gap-2 text-[15px] font-bold text-blue-ink"
              >
                <FileText size={18} aria-hidden="true" /> Basisinformationsblatt öffnen (PDF)
              </a>
            </Card>

            {p.holdings.length > 0 && (
              <Card className="space-y-1">
                <h2 className="text-[17px] font-bold text-navy">Größte Positionen</h2>
                <ul className="divide-y divide-line">
                  {topHoldings(p.holdings, 5).map((h) => (
                    <li key={h.id} className="flex items-baseline justify-between gap-3 py-2 text-[15px]">
                      <span className="text-navy">{h.name}</span>
                      <span className="font-semibold text-navy">{pct(h.weight, 1)}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
            <Disclaimer />
          </>
        )}
      </div>
    </div>
  )
}
