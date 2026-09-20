import { ArrowRight, ChartPie, TrendingUp } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { Area, AreaChart, ResponsiveContainer, YAxis } from 'recharts'
import { PersonaSwitcher } from '../components/PersonaSwitcher'
import { ASSET_CLASS_LABEL } from '../blocks/ProductCardsBlock'
import { BRAND_NAME, Card, Disclaimer, ErrorNote, Overlap, ScreenHeader, Section, Skeleton } from '../components/ui'
import { api } from '../lib/api'
import { cn, eur, pct, signedPct } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import { usePersona } from '../state/persona'

const EXAMPLES = [
  'Ich will monatlich 50 € nachhaltig in Europa anlegen, ohne Waffen',
  'Was steckt eigentlich in meinem Depot?',
  'Wie entwickeln sich 50 € im Monat über 20 Jahre?',
  'Warum ist mein Depot im August gefallen?',
]

export function AskCard({ onAsk }: { onAsk: (q: string) => void }) {
  const [q, setQ] = useState('')
  function submit(e: FormEvent) {
    e.preventDefault()
    if (q.trim()) onAsk(q.trim())
  }
  return (
    <Card>
      <form onSubmit={submit} className="flex items-end gap-3">
        <div className="min-w-0 flex-1">
          <label htmlFor="ask" className="text-[15px] font-semibold text-muted">
            Frag {BRAND_NAME}
          </label>
          <input
            id="ask"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="z. B. monatlich 50 € in nachhaltige Firmen aus Europa"
            className="mt-1 h-11 w-full bg-transparent text-[17px] text-navy placeholder:text-muted"
          />
        </div>
        <button
          type="submit"
          aria-label="Frage senden"
          className="grid size-12 shrink-0 place-items-center rounded-full bg-blue text-white"
        >
          <ArrowRight size={22} aria-hidden="true" />
        </button>
      </form>
    </Card>
  )
}

/** Übersicht: depot value, 3-month curve, positions and a way into the chat. */
export function HomeScreen() {
  const { current } = usePersona()
  const navigate = useNavigate()
  const { data: p, loading, error } = useLoad(current?.id ?? null, () => api.getPortfolio(current!.id))
  const ask = (q: string) => navigate(`/chat?q=${encodeURIComponent(q)}`)
  const spark = p ? p.series.slice(-63) : []
  const down = p ? p.change_3m_pct < 0 : false

  return (
    <div>
      <ScreenHeader back={false} title="Invest">
        <div className="mt-2">
          <PersonaSwitcher />
        </div>
        <p className="mt-5 text-[17px] opacity-90">Depotwert{p ? `, ${current?.name}` : ''}</p>
        {loading && !p ? (
          <Skeleton className="mt-2 h-14 w-56" />
        ) : (
          p && (
            <>
              <p className="mt-1 text-[44px] font-extrabold leading-none tracking-wide" data-testid="depot-value">
                {eur(p.total_value_eur, 2)}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <span className={cn('rounded-full px-3 py-2 text-[15px] font-bold', down ? 'bg-red-soft text-red' : 'bg-green-soft text-green')}>
                  {signedPct(p.change_3m_pct)} in 3 Monaten
                </span>
                <span className="text-[15px] opacity-90">ohne Einzahlungen gerechnet</span>
              </div>
              <div className="-mx-4 mt-3 h-16" role="img" aria-label="Depotwert der letzten drei Monate">
                <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 390, height: 64 }}>
                  <AreaChart data={spark} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
                    <YAxis hide domain={['dataMin', 'dataMax']} />
                    <Area dataKey="value_eur" stroke="#fff" strokeWidth={2.5} fill="rgba(255,255,255,.16)" isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </>
          )
        )}
      </ScreenHeader>

      <Overlap>
        <AskCard onAsk={ask} />
        <ul className="flex flex-wrap gap-2" aria-label="Beispielfragen">
          {EXAMPLES.map((e) => (
            <li key={e}>
              <button
                type="button"
                onClick={() => ask(e)}
                className="min-h-11 rounded-[22px] border border-line bg-white px-4 py-2 text-left text-[15px] text-navy"
              >
                {e}
              </button>
            </li>
          ))}
        </ul>
      </Overlap>

      <Section className="mt-4 pb-4">
        {error && <ErrorNote message={error} />}
        {p && (
          <Card className="space-y-1">
            <h2 className="text-[17px] font-bold text-navy">Deine Positionen</h2>
            <ul className="divide-y divide-line">
              {p.positions.map((pos) => (
                <li key={pos.product_id}>
                  <Link to={`/produkt/${pos.product_id}`} className="block py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-[17px] font-semibold leading-snug text-navy">{pos.name}</p>
                        <p className="text-[13px] text-muted">
                          {ASSET_CLASS_LABEL[pos.asset_class]} · Risiko {pos.sri} von 7
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="text-[17px] font-bold text-navy">{eur(pos.value_eur, 2)}</p>
                        <p className="text-[13px] text-muted">{pct(pos.weight, 0)} vom Depot</p>
                      </div>
                    </div>
                    <div className="mt-2 h-1.5 rounded bg-ground">
                      <div className="h-full rounded bg-blue" style={{ width: `${pos.weight * 100}%` }} />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
            <p className="pt-2 text-[13px] text-muted">Dazu {eur(p.cash_eur, 2)} auf dem Verrechnungskonto.</p>
          </Card>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Link to="/depot" className="flex min-h-20 flex-col justify-between rounded-[20px] bg-card p-4 shadow-[var(--shadow-card)]">
            <ChartPie size={22} className="text-blue" aria-hidden="true" />
            <span className="text-[15px] font-bold text-navy">Depot & Röntgen</span>
          </Link>
          <Link to="/simulator" className="flex min-h-20 flex-col justify-between rounded-[20px] bg-card p-4 shadow-[var(--shadow-card)]">
            <TrendingUp size={22} className="text-blue" aria-hidden="true" />
            <span className="text-[15px] font-bold text-navy">Was wäre, wenn …</span>
          </Link>
        </div>
        <Disclaimer className="pb-2" />
      </Section>
    </div>
  )
}
