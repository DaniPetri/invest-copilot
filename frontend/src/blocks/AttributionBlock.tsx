import { Bar, BarChart, Cell, LabelList, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { Card } from '../components/ui'
import { dayLong, signedEur, signedPct } from '../lib/format'
import type { AttributionBlock, AttributionRow, MarketEvent } from '../types/contracts'

/** Who contributed how much to the move, as diverging bars (design/04 "Wer hat wie viel beigetragen"). */
export function AttributionBars({ rows }: { rows: AttributionRow[] }) {
  const data = rows.map((r) => ({ name: r.name, pnl: r.pnl_eur }))
  const lo = Math.min(0, ...data.map((d) => d.pnl))
  const hi = Math.max(0, ...data.map((d) => d.pnl))
  const pad = (hi - lo) * 0.35 || 1
  const height = data.length * 44 + 8
  return (
    <div role="img" aria-label={`Beiträge: ${rows.map((r) => `${r.name} ${signedEur(r.pnl_eur)}`).join(', ')}`}>
      <ResponsiveContainer width="100%" height={height} initialDimension={{ width: 320, height }}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 0 }}>
          <XAxis type="number" hide domain={[lo - pad, hi + pad]} />
          <YAxis type="category" dataKey="name" width={112} tickLine={false} axisLine={false} interval={0} tick={{ fontSize: 14, fill: 'var(--navy)' }} />
          <ReferenceLine x={0} stroke="var(--line)" />
          <Bar dataKey="pnl" barSize={14} radius={4} isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.name} fill={d.pnl < 0 ? 'var(--red)' : 'var(--green)'} />
            ))}
            <LabelList dataKey="pnl" position="right" formatter={(v: unknown) => signedEur(Number(v))} style={{ fontSize: 14, fontWeight: 700, fill: 'var(--navy)' }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function EventCard({ event }: { event: MarketEvent }) {
  return (
    <article className="rounded-[14px] bg-ground px-3 py-3" data-testid="event-card">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-[15px] font-semibold text-navy">{event.name}</h4>
        <span className={`shrink-0 text-[13px] font-bold ${event.shock_pct < 0 ? 'text-red' : 'text-green'}`}>
          {signedPct(event.shock_pct)}
        </span>
      </div>
      <p className="mt-0.5 text-[13px] text-muted">
        {dayLong(event.date)} · {event.sectors.length ? event.sectors.join(', ') : 'ganzer Markt'}
      </p>
      <p className="mt-1 text-[14px] leading-snug text-ink-2">{event.description}</p>
    </article>
  )
}

export function AttributionBlockView({ block }: { block: AttributionBlock }) {
  const negative = block.change_eur < 0
  return (
    <Card className="space-y-4" data-testid="block-attribution">
      <div>
        <h3 className="text-[17px] font-bold text-navy">Wer hat wie viel beigetragen</h3>
        <p className={`mt-1 text-[22px] font-extrabold ${negative ? 'text-red' : 'text-green'}`}>
          {signedPct(block.change_pct, 2)} ({signedEur(block.change_eur, 2)})
        </p>
      </div>
      <AttributionBars rows={block.rows} />
      <ul className="space-y-1 text-[13px] text-muted">
        {block.rows.map((r) => (
          <li key={r.product_id}>
            {r.name}: {signedPct(r.pnl_pct)} der Position, {signedPct(r.contribution_pct, 2)} Punkte am Depot
          </li>
        ))}
      </ul>
      {block.events.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-[15px] font-bold text-navy">Passende Ereignisse</h4>
          {block.events.map((e) => (
            <EventCard key={e.id} event={e} />
          ))}
        </div>
      )}
      <p className="text-[13px] text-muted">Berechnet aus deinen Positionen und den Kursen. Einzahlungen im Zeitraum zählen nicht als Gewinn.</p>
    </Card>
  )
}
