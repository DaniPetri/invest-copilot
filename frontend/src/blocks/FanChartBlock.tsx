import { Area, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card } from '../components/ui'
import { eur } from '../lib/format'
import type { FanChartBlock } from '../types/contracts'

interface Point {
  year: number
  band90: [number, number]
  band50: [number, number]
  median: number
  paid: number
}

function toPoints(b: FanChartBlock): Point[] {
  const origin: Point = { year: 0, band90: [0, 0], band50: [0, 0], median: 0, paid: 0 }
  return [
    origin,
    ...b.years.map((year, i) => ({
      year,
      band90: [b.p5[i], b.p95[i]] as [number, number],
      band50: [b.p25[i], b.p75[i]] as [number, number],
      median: b.p50[i],
      paid: b.contributions[i],
    })),
  ]
}

function FanTooltip({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  const p = payload?.[0]?.payload
  if (!active || !p || p.year === 0) return null
  return (
    <div className="rounded-[12px] bg-navy px-3 py-2 text-[13px] text-white shadow-lg">
      <div className="font-semibold">Nach {p.year} Jahren</div>
      <div>Mitte: {eur(p.median)}</div>
      <div>
        9 von 10: {eur(p.band90[0])} bis {eur(p.band90[1])}
      </div>
      <div>Eingezahlt: {eur(p.paid)}</div>
    </div>
  )
}

/** Fan chart of the simulation (design/06): median, the 25-75 % and 5-95 % bands, and the amount paid in. */
export function FanChartBlockView({ block }: { block: FanChartBlock }) {
  const data = toPoints(block)
  const last = block.years.length - 1
  const horizon = block.years[last]
  const ticks = [0, Math.round(horizon / 2), horizon]
  return (
    <div className="space-y-3" data-testid="block-fan-chart">
      <Card>
        <div role="img" aria-label={`Fächerdiagramm über ${horizon} Jahre: Mitte ${eur(block.p50[last])}, eingezahlt ${eur(block.contributions[last])}`}>
          <ResponsiveContainer width="100%" height={220} initialDimension={{ width: 320, height: 220 }}>
            <ComposedChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
              <XAxis
                dataKey="year"
                type="number"
                domain={[0, horizon]}
                ticks={ticks}
                interval={0}
                tickFormatter={(y: number) => (y === 0 ? 'heute' : `in ${y} Jahren`)}
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 13, fill: 'var(--muted)' }}
              />
              <YAxis hide domain={[0, 'auto']} />
              <Tooltip content={<FanTooltip />} />
              <Area dataKey="band90" stroke="none" fill="#C7D6FA" fillOpacity={0.55} isAnimationActive={false} />
              <Area dataKey="band50" stroke="none" fill="#8FB0F5" fillOpacity={0.6} isAnimationActive={false} />
              <Line dataKey="paid" stroke="var(--navy)" strokeDasharray="4 4" strokeWidth={1.5} dot={false} isAnimationActive={false} />
              <Line dataKey="median" stroke="var(--blue)" strokeWidth={3} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-ink-2">
          <li className="flex items-center gap-2">
            <span className="h-[3px] w-4 rounded bg-blue" /> mittlerer Verlauf
          </li>
          <li className="flex items-center gap-2">
            <span className="h-3 w-4 rounded-sm bg-[#C7D6FA]" /> 9 von 10 Verläufen
          </li>
          <li className="flex items-center gap-2">
            <span className="w-4 border-t-2 border-dashed border-navy" /> eingezahlt
          </li>
        </ul>
      </Card>
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Eingezahlt" value={eur(block.contributions[last])} />
        <Stat label="Mittlerer Verlauf" value={eur(block.p50[last])} accent />
        <Stat label="1 von 20 schlechter als" value={eur(block.p5[last])} />
      </div>
    </div>
  )
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-[20px] bg-card p-3 shadow-[var(--shadow-card)]">
      <div className="text-[13px] leading-tight text-muted">{label}</div>
      <div className={`mt-2 text-[17px] font-extrabold leading-tight ${accent ? 'text-blue' : 'text-navy'}`}>{value}</div>
    </div>
  )
}
