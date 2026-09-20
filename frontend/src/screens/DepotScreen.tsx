import { AlertTriangle, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { Area, AreaChart, ReferenceDot, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { AttributionBlockView, EventCard } from '../blocks/AttributionBlock'
import { ExposureBars } from '../blocks/ExposureBarsBlock'
import { OverlapMatrixBlockView } from '../blocks/OverlapMatrixBlock'
import { Card, Disclaimer, ErrorNote, ScreenHeader, Segmented, Skeleton } from '../components/ui'
import { api } from '../lib/api'
import { eventWindow } from '../lib/events'
import { cn, dayLong, dayShort, eur, monthName, pct, signedEur, signedPct } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import { usePersona } from '../state/persona'
import type { EventMarker, LookthroughPayload, PortfolioView } from '../types/contracts'

type Range = '3M' | '1J'
type Dimension = 'country' | 'sector' | 'company'

function DepotChart({
  series,
  markers,
  selected,
  onSelect,
}: {
  series: PortfolioView['series']
  markers: EventMarker[]
  selected: string | null
  onSelect: (id: string) => void
}) {
  const ticks = useMemo(() => {
    const firsts: string[] = []
    let last = ''
    for (const p of series) {
      const m = p.date.slice(0, 7)
      if (m !== last) firsts.push(p.date), (last = m)
    }
    return firsts.length > 4 ? firsts.filter((_, i) => i % Math.ceil(firsts.length / 4) === 0) : firsts
  }, [series])
  const byDate = new Map(series.map((p) => [p.date, p.value_eur]))
  const sel = markers.find((m) => m.event.id === selected)
  return (
    <div className="-mx-4 h-[190px]" role="img" aria-label="Depotwert im Verlauf, mit Ereignissen markiert">
      <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 390, height: 190 }}>
        <AreaChart data={series} margin={{ top: 16, right: 16, bottom: 0, left: 16 }}>
          <XAxis
            dataKey="date"
            ticks={ticks}
            tickFormatter={(d: string) => monthName(d)}
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 15, fill: '#fff' }}
            interval={0}
          />
          <YAxis hide domain={['dataMin - 40', 'dataMax + 40']} />
          {sel && <ReferenceLine x={sel.event.date} stroke="#fff" strokeDasharray="3 4" />}
          <Area dataKey="value_eur" stroke="#fff" strokeWidth={2.5} fill="rgba(255,255,255,.16)" isAnimationActive={false} />
          {markers.map((m) => {
            const y = byDate.get(m.event.date)
            if (y === undefined) return null
            const on = m.event.id === selected
            return (
              <ReferenceDot
                key={m.event.id}
                x={m.event.date}
                y={y}
                r={on ? 9 : 7}
                fill={on ? '#E0533F' : '#2463EB'}
                stroke="#fff"
                strokeWidth={3}
                onClick={() => onSelect(m.event.id)}
                style={{ cursor: 'pointer' }}
              />
            )
          })}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Depot-Röntgen: what is inside the products, and how much they overlap (design/05). */
function Roentgen({ data }: { data: LookthroughPayload }) {
  const [dim, setDim] = useState<Dimension>('sector')
  const rows = dim === 'country' ? data.by_country : dim === 'sector' ? data.by_sector : data.by_company
  const products = useMemo(() => {
    const ids = [...new Set(data.overlaps.flatMap((o) => [o.product_a, o.product_b]))].sort()
    return ids
  }, [data.overlaps])
  const { data: names } = useLoad('names', () => api.getProducts())
  const nameOf = (id: string) => names?.find((p) => p.id === id)?.name ?? id
  const matrix = products.map((a) => products.map((b) => (a === b ? 1 : (data.overlaps.find((o) => (o.product_a === a && o.product_b === b) || (o.product_a === b && o.product_b === a))?.overlap ?? 0))))
  const top1 = data.by_company[0]

  return (
    <section id="roentgen" aria-labelledby="roentgen-title" className="space-y-3">
      <h2 id="roentgen-title" className="text-[22px] font-bold text-navy">
        Depot-Röntgen
      </h2>
      <p className="text-[17px] leading-snug text-ink-2">
        Du hältst {data.n_products} Produkte. Darin stecken {data.n_companies} Positionen.
      </p>
      {products.length > 1 && (
        <OverlapMatrixBlockView block={{ type: 'overlap_matrix', products: products.map((id) => ({ product_id: id, name: nameOf(id) })), matrix }} />
      )}
      {data.flags.length > 0 && (
        <Card tone="amber" className="space-y-1" data-testid="roentgen-note">
          <p className="flex items-center gap-2 text-[15px] font-bold">
            <AlertTriangle size={18} aria-hidden="true" /> Hinweis
          </p>
          <p className="text-[17px] font-bold leading-snug">
            {pct(data.top10_share, 0)} deines Depots hängen an den zehn größten Positionen.
          </p>
          <p className="text-[15px] leading-snug">
            {data.flags.includes('single_company_over_5pct') && top1
              ? `Die größte Einzelposition, ${top1.label}, macht ${pct(top1.weight, 1)} aus. `
              : ''}
            Das ist keine Empfehlung, nur ein Blick hinein.
          </p>
        </Card>
      )}
      <Card className="space-y-3">
        <Segmented
          label="Aufteilung"
          value={dim}
          onChange={setDim}
          options={[
            { value: 'country', label: 'Länder' },
            { value: 'sector', label: 'Branchen' },
            { value: 'company', label: 'Top-Titel' },
          ]}
        />
        <ExposureBars dimension={dim} rows={rows.slice(0, 8)} />
      </Card>
    </section>
  )
}

export function DepotScreen() {
  const { current } = usePersona()
  const navigate = useNavigate()
  const [range, setRange] = useState<Range>('3M')
  const [selected, setSelected] = useState<string | null>(null)
  const id = current?.id ?? null

  const portfolio = useLoad(id, () => api.getPortfolio(id!))
  const p = portfolio.data
  const series = useMemo(() => (p ? (range === '3M' ? p.series.slice(-63) : p.series) : []), [p, range])
  const markers = useMemo(
    () => (p ? p.events.filter((m) => m.event.date >= (series[0]?.date ?? '')) : []),
    [p, series],
  )

  // the newest event is selected by default; switching persona or range keeps the selection only if still visible
  useEffect(() => {
    setSelected((cur) => {
      if (markers.length === 0) return null
      return cur && markers.some((m) => m.event.id === cur) ? cur : markers[markers.length - 1].event.id
    })
  }, [markers])

  const marker = markers.find((m) => m.event.id === selected)
  const win = marker ? eventWindow(marker.event) : null
  const explain = useLoad(marker && id ? `${id}|${marker.event.id}` : null, () => api.explainMove(id!, win!.start, win!.end))
  const look = useLoad(id, () => api.lookthrough(id!))
  const startValue = series[0]?.value_eur
  const down = p ? p.change_3m_pct < 0 : false

  return (
    <div>
      <ScreenHeader title="Mein Depot">
        <p className="mt-4 text-[17px] opacity-90">Depotwert, letzte {range === '3M' ? '3 Monate' : '12 Monate'}</p>
        {!p ? (
          <Skeleton className="mt-2 h-14 w-56" />
        ) : (
          <>
            <p className="mt-1 text-[44px] font-extrabold leading-none tracking-wide">{eur(p.total_value_eur, 2)}</p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <span className={cn('rounded-full px-3 py-2 text-[15px] font-bold', down ? 'bg-red-soft text-red' : 'bg-green-soft text-green')}>
                {signedPct(p.change_3m_pct)} in 3 Monaten
              </span>
              <span className="text-[15px] opacity-90">Tippe auf einen Punkt im Verlauf</span>
            </div>
            <DepotChart series={series} markers={markers} selected={selected} onSelect={setSelected} />
            <div role="radiogroup" aria-label="Zeitraum" className="mt-1 flex gap-2">
              {(['3M', '1J'] as Range[]).map((r) => (
                <button
                  key={r}
                  type="button"
                  role="radio"
                  aria-checked={range === r}
                  onClick={() => setRange(r)}
                  className={cn('min-h-11 min-w-16 rounded-full px-4 text-[15px] font-semibold', range === r ? 'bg-white text-blue-ink' : 'bg-white/15 text-white')}
                >
                  {r === '3M' ? '3 M.' : '1 J.'}
                </button>
              ))}
            </div>
          </>
        )}
      </ScreenHeader>

      <div className="relative z-10 -mt-10 rounded-t-[28px] bg-ground px-4 pt-4">
        <div className="space-y-3">
          {portfolio.error && <ErrorNote message={portfolio.error} />}
          {markers.length > 0 && (
            <ul className="grid gap-3" style={{ gridTemplateColumns: `repeat(${Math.min(markers.length, 3)}, minmax(0, 1fr))` }} aria-label="Ereignisse im Verlauf">
              {markers.slice(-3).map((m) => {
                const on = m.event.id === selected
                return (
                  <li key={m.event.id}>
                    <button
                      type="button"
                      onClick={() => setSelected(m.event.id)}
                      aria-pressed={on}
                      className={cn('min-h-16 w-full rounded-[16px] bg-white px-2 py-2 text-center', on ? 'border-2 border-blue' : 'border-2 border-transparent')}
                    >
                      <span className="block text-[15px] text-muted">{dayShort(m.event.date)}</span>
                      <span className={cn('block text-[17px] font-extrabold', m.change_pct < 0 ? 'text-red' : 'text-green')}>{signedPct(m.change_pct)}</span>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}

          {marker && (
            <div className="space-y-3" aria-live="polite" data-testid="event-detail">
              <Card className="space-y-2">
                <h2 className="text-[22px] font-extrabold leading-tight text-navy">
                  {dayShort(marker.event.date)}: {signedPct(marker.change_pct)} ({signedEur(marker.change_eur)})
                </h2>
                <EventCard event={marker.event} />
                <button
                  type="button"
                  onClick={() => navigate(`/chat?q=${encodeURIComponent(`Warum hat sich mein Depot am ${dayLong(marker.event.date)} bewegt?`)}`)}
                  className="inline-flex min-h-11 items-center gap-2 rounded-[14px] bg-ai px-4 text-[15px] font-bold text-white"
                >
                  <Sparkles size={16} aria-hidden="true" /> Erklären lassen
                </button>
              </Card>
              {explain.loading && <Skeleton className="h-40 bg-white" />}
              {explain.error && <ErrorNote message={explain.error} />}
              {explain.data && (
                <AttributionBlockView
                  block={{
                    type: 'attribution',
                    rows: explain.data.payload.rows,
                    events: [],
                    change_eur: explain.data.payload.change_eur,
                    change_pct: explain.data.payload.change_pct,
                  }}
                />
              )}
            </div>
          )}
          {p && markers.length === 0 && <Card className="text-[15px] text-ink-2">In diesem Zeitraum gab es keine Ereignisse, die dein Depot betroffen haben.</Card>}

          {look.data && <Roentgen data={look.data.payload} />}
          {look.error && <ErrorNote message={look.error} />}
          {startValue !== undefined && <Disclaimer className="pb-4" />}
        </div>
      </div>
    </div>
  )
}

