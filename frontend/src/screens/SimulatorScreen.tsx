import { useState } from 'react'
import { FanChartBlockView } from '../blocks/FanChartBlock'
import { Card, ChoiceButtons, Disclaimer, ErrorNote, Overlap, ScreenHeader, Skeleton } from '../components/ui'
import { api } from '../lib/api'
import { eur, num, pct } from '../lib/format'
import { MIX_IDS, MIXES, RATES, YEARS, type MixId } from '../lib/mixes'
import { useLoad } from '../lib/useLoad'

/** Was wäre, wenn …: savings plan simulation with three levers; every change is a direct tool call (design/06). */
export function SimulatorScreen() {
  const [rate, setRate] = useState<number>(50)
  const [years, setYears] = useState<number>(20)
  const [mix, setMix] = useState<MixId>('ausgewogen')
  const { data, loading, error } = useLoad(`${rate}|${years}|${mix}`, () => api.simulate(rate, years, mix))
  const s = data?.payload

  return (
    <div>
      <ScreenHeader title="Was wäre, wenn …">
        <h2 className="mt-4 text-[28px] font-extrabold leading-tight" aria-live="polite">
          {eur(rate)} im Monat, {years} Jahre lang.{s ? ` ${num(s.n_paths)} mögliche Zukünfte.` : ''}
        </h2>
      </ScreenHeader>

      <Overlap className="pb-6">
        {error && <ErrorNote message={error} />}
        {s ? (
          <FanChartBlockView
            block={{ type: 'fan_chart', years: s.years, p5: s.p5, p25: s.p25, p50: s.p50, p75: s.p75, p95: s.p95, contributions: s.contributions }}
          />
        ) : (
          loading && <Skeleton className="h-72 bg-white" />
        )}

        <Card className="space-y-4">
          <div>
            <p className="mb-2 text-[15px] font-semibold text-muted">Rate pro Monat</p>
            <ChoiceButtons label="Rate pro Monat" value={rate} onChange={setRate} options={RATES.map((r) => ({ value: r as number, label: eur(r) }))} />
          </div>
          <div>
            <p className="mb-2 text-[15px] font-semibold text-muted">Dauer</p>
            <ChoiceButtons label="Dauer" value={years} onChange={setYears} options={YEARS.map((y) => ({ value: y as number, label: `${y} J.` }))} />
          </div>
          <div>
            <p className="mb-2 text-[15px] font-semibold text-muted">Mischung</p>
            <ChoiceButtons label="Mischung" value={mix} onChange={setMix} options={MIX_IDS.map((m) => ({ value: m, label: MIXES[m].label }))} />
            <p className="mt-2 text-[13px] text-muted">{MIXES[mix].description}</p>
          </div>
        </Card>

        {s && (
          <Card className="space-y-2" data-testid="simulator-words">
            <h2 className="text-[17px] font-bold text-navy">In einfachen Worten</h2>
            <p className="text-[15px] leading-relaxed text-ink-2">
              Nach {years} Jahren liegen 9 von 10 Verläufen zwischen {eur(s.p5[s.p5.length - 1])} und {eur(s.p95[s.p95.length - 1])}. Du hast dann{' '}
              {eur(s.total_contributions)} eingezahlt. In {pct(s.prob_below_contributions, 1)} der Verläufe ist am Ende weniger da als eingezahlt.
            </p>
            <p className="text-[13px] leading-snug text-muted">
              Explizite Kosten {eur(s.total_costs)} (Sparplan-Entgelt und Einstiegskosten), geschätzte Kapitalertragsteuer auf den mittleren Verlauf{' '}
              {eur(s.kest_estimate)}. Gerechnet mit {num(s.n_paths)} zufälligen Verläufen aus fünf Jahren simulierter Kursdaten. Das ist
              keine Prognose.
            </p>
          </Card>
        )}
        <Disclaimer />
      </Overlap>
    </div>
  )
}
