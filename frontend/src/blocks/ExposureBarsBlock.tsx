import { Bar, BarChart, LabelList, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { Card } from '../components/ui'
import { pct } from '../lib/format'
import type { ExposureBarsBlock } from '../types/contracts'

const TITLES: Record<ExposureBarsBlock['dimension'], string> = {
  sector: 'Branchen',
  country: 'Länder',
  company: 'Größte Positionen',
}

/** Horizontal bars of look-through exposure (design/05 "Regionen | Branchen | Top-Titel"). */
export function ExposureBars({ dimension, rows }: Pick<ExposureBarsBlock, 'dimension' | 'rows'>) {
  const data = rows.map((r) => ({ label: r.label, weight: r.weight }))
  const max = Math.max(...data.map((d) => d.weight), 0.01)
  const height = data.length * 38 + 8
  return (
    <div
      role="img"
      aria-label={`${TITLES[dimension]}: ${data.map((d) => `${d.label} ${pct(d.weight, 0)}`).join(', ')}`}
    >
      <ResponsiveContainer width="100%" height={height} initialDimension={{ width: 320, height }}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 44, bottom: 0, left: 0 }}>
          <XAxis type="number" hide domain={[0, max * 1.05]} />
          <YAxis
            type="category"
            dataKey="label"
            width={128}
            tickLine={false}
            axisLine={false}
            interval={0}
            tick={{ fontSize: 14, fill: 'var(--navy)' }}
          />
          <Bar dataKey="weight" fill="var(--blue)" barSize={12} radius={[0, 6, 6, 0]} isAnimationActive={false} background={{ fill: 'var(--ground)', radius: 6 }}>
            <LabelList dataKey="weight" position="right" formatter={(v: unknown) => pct(Number(v), 1)} style={{ fontSize: 14, fontWeight: 600, fill: 'var(--navy)' }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ExposureBarsBlockView({ block }: { block: ExposureBarsBlock }) {
  return (
    <Card className="space-y-2" data-testid="block-exposure-bars">
      <h3 className="text-[17px] font-bold text-navy">{TITLES[block.dimension]}</h3>
      <ExposureBars dimension={block.dimension} rows={block.rows} />
    </Card>
  )
}
