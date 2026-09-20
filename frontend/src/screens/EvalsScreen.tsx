import { Info } from 'lucide-react'
import type { ReactNode } from 'react'
import { Card, Disclaimer, ErrorNote, ScreenHeader, Skeleton, StatusIcon } from '../components/ui'
import { api } from '../lib/api'
import { cn, dayLong, num, pct } from '../lib/format'
import { useLoad } from '../lib/useLoad'
import type { EvalReport, JudgeScore, RetrievalRow } from '../types/contracts'

const MODE_LABEL: Record<RetrievalRow['mode'], string> = {
  bm25: 'BM25 (Wörter)',
  dense: 'Dense (Bedeutung)',
  hybrid: 'Hybrid (RRF)',
  hybrid_rerank: 'Hybrid + Reranker',
}

function SampleTag({ show }: { show: boolean }) {
  return show ? (
    <span className="rounded-full bg-amber-soft px-2 py-0.5 text-[12px] font-bold text-amber-ink">Beispielwert</span>
  ) : (
    <span className="rounded-full bg-green-soft px-2 py-0.5 text-[12px] font-bold text-green">gemessen</span>
  )
}

function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[300px] text-[14px] tabular-nums">
        <thead className="text-left text-[13px] text-muted">
          <tr>
            {head.map((h, i) => (
              <th key={h} className={cn('pb-2 font-semibold', i > 0 && 'text-right')}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
    </div>
  )
}

/** Green when good, red when bad: the colour coding of design/12. */
function Score({ value, good, digits = 1, percent = true }: { value: number; good: boolean; digits?: number; percent?: boolean }) {
  return <span className={cn('font-bold', good ? 'text-green' : 'text-red')}>{percent ? pct(value, digits) : num(value, digits)}</span>
}

function Judge({ label, s }: { label: string; s: JudgeScore }) {
  const w = ((s.mean - 1) / 4) * 100
  return (
    <li className="space-y-1">
      <div className="flex justify-between text-[15px]">
        <span className="text-navy">{label}</span>
        <span className="font-bold text-navy">
          {num(s.mean, 1)} <span className="font-normal text-muted">({num(s.ci_low, 1)} bis {num(s.ci_high, 1)})</span>
        </span>
      </div>
      <div className="relative h-2 rounded bg-ground" aria-hidden="true">
        <div className="absolute h-full rounded bg-blue" style={{ width: `${w}%` }} />
        <div className="absolute top-[-2px] h-3 w-0.5 bg-navy" style={{ left: `${((s.ci_low - 1) / 4) * 100}%` }} />
        <div className="absolute top-[-2px] h-3 w-0.5 bg-navy" style={{ left: `${((s.ci_high - 1) / 4) * 100}%` }} />
      </div>
    </li>
  )
}

function Report({ r }: { r: EvalReport }) {
  const anySample = r.gates.some((g) => g.sample)
  return (
    <div className="space-y-3">
      {anySample && (
        <Card tone="amber" className="flex items-start gap-2 text-[15px]" data-testid="sample-banner">
          <Info size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            Nur die Retrieval-Zahlen sind gemessen. Router, Antworten, Red Team und Judge sind Beispielwerte, bis die Läufe
            in Meilenstein 7 laufen.
          </span>
        </Card>
      )}

      <Card className="space-y-2">
        <h2 className="text-[17px] font-bold text-navy">Freigabe-Schwellen</h2>
        <ul className="divide-y divide-line" data-testid="gates">
          {r.gates.map((g) => (
            <li key={g.name} className="flex items-center gap-3 py-2.5">
              <StatusIcon status={g.passed ? 'pass' : 'fail'} />
              <div className="min-w-0 flex-1">
                <p className="text-[15px] font-semibold text-navy">
                  {g.name} <SampleTag show={g.sample} />
                </p>
                <p className="text-[13px] text-muted">
                  {g.metric}: {g.value <= 1 && g.threshold <= 1 && g.threshold > 0 ? pct(g.value, 1) : num(g.value, g.value % 1 ? 1 : 0)} (Schwelle {g.threshold <= 1 && g.threshold > 0 ? pct(g.threshold, 0) : num(g.threshold, g.threshold % 1 ? 1 : 0)})
                </p>
              </div>
              <span className={cn('rounded-full px-2 py-1 text-[13px] font-bold', g.passed ? 'bg-green-soft text-green' : 'bg-red-soft text-red')}>
                {g.passed ? 'bestanden' : 'nicht bestanden'}
              </span>
            </li>
          ))}
        </ul>
      </Card>

      <Card className="space-y-3">
        <h2 className="flex items-center justify-between text-[17px] font-bold text-navy">
          Retrieval im Vergleich <SampleTag show={r.retrieval.sample} />
        </h2>
        <Table head={['Modus', 'Recall@1', 'Recall@5', 'MRR@10', 'nDCG@5', 'p50']}>
          {r.retrieval.rows.map((row) => (
            <tr key={row.mode} className={row.mode === 'hybrid' ? 'bg-blue-soft/60' : ''}>
              <td className="py-2 pr-2 font-semibold text-navy">
                {MODE_LABEL[row.mode]}
                {row.n_questions < 1000 && <span className="block text-[12px] font-normal text-muted">Stichprobe, {num(row.n_questions)} Fragen</span>}
              </td>
              <td className="text-right">{num(row.recall_at_1, 3)}</td>
              <td className="text-right">
                <Score value={row.recall_at_5} good={row.recall_at_5 >= 0.85} digits={3} percent={false} />
              </td>
              <td className="text-right">{num(row.mrr_at_10, 3)}</td>
              <td className="text-right">{num(row.ndcg_at_5, 3)}</td>
              <td className="text-right">{row.p50_ms >= 100 ? `${num(row.p50_ms)} ms` : `${num(row.p50_ms, 1)} ms`}</td>
            </tr>
          ))}
        </Table>
        <p className="text-[13px] text-muted">Hybrid soll mindestens 0,85 bei Recall@5 erreichen. Der Reranker braucht auf der CPU gut eine Sekunde pro Frage.</p>
      </Card>

      <Card className="space-y-2">
        <h2 className="flex items-center justify-between text-[17px] font-bold text-navy">
          Router <SampleTag show={r.router.sample} />
        </h2>
        <Table head={['Kennzahl', 'Wert']}>
          <tr>
            <td className="py-2">Trefferquote Entwicklung ({r.router.n_dev} Sätze)</td>
            <td className="text-right"><Score value={r.router.accuracy_dev} good={r.router.accuracy_dev >= 0.8} /></td>
          </tr>
          <tr>
            <td className="py-2">Trefferquote Blind ({r.router.n_blind} Sätze)</td>
            <td className="text-right"><Score value={r.router.accuracy_blind} good={r.router.accuracy_blind >= 0.8} /></td>
          </tr>
          <tr>
            <td className="py-2">Macro-F1</td>
            <td className="text-right">{num(r.router.macro_f1, 2)}</td>
          </tr>
          <tr>
            <td className="py-2">Beratungsfragen erkannt</td>
            <td className="text-right"><Score value={r.router.advice_recall} good={r.router.advice_recall >= 0.95} /></td>
          </tr>
          <tr>
            <td className="py-2">Fehlalarme</td>
            <td className="text-right"><Score value={r.router.false_alarm_rate} good={r.router.false_alarm_rate <= 0.1} /></td>
          </tr>
        </Table>
      </Card>

      <Card className="space-y-3">
        <h2 className="flex items-center justify-between text-[17px] font-bold text-navy">
          Antworten ({r.answers.n} Fragen) <SampleTag show={r.answers.sample} />
        </h2>
        <ul className="space-y-1 text-[15px]">
          <li className="flex justify-between"><span>Quellenverweise gültig</span><Score value={r.answers.citation_validity} good={r.answers.citation_validity >= 0.95} /></li>
          <li className="flex justify-between"><span>Zahlen belegt</span><Score value={r.answers.numeric_grounding} good={r.answers.numeric_grounding >= 0.9} /></li>
          <li className="flex justify-between"><span>Keine Empfehlungssprache</span><Score value={r.answers.advice_language_absent} good={r.answers.advice_language_absent >= 0.99} /></li>
        </ul>
        <div>
          <p className="mb-2 text-[13px] font-semibold text-muted">LLM-Judge, 1 bis 5, mit 95-%-Intervall</p>
          <ul className="space-y-3">
            <Judge label="Treue zur Quelle" s={r.answers.faithfulness} />
            <Judge label="Vollständigkeit" s={r.answers.completeness} />
            <Judge label="Klarheit" s={r.answers.clarity} />
            <Judge label="Beratungsgrenze" s={r.answers.boundary} />
          </ul>
        </div>
      </Card>

      <Card className="space-y-2">
        <h2 className="flex items-center justify-between text-[17px] font-bold text-navy">
          Red Team <SampleTag show={r.redteam.sample} />
        </h2>
        <Table head={['Kategorie', 'Angriffe', 'Erfolgreich']}>
          {r.redteam.rows.map((row) => (
            <tr key={row.category}>
              <td className="py-2 pr-2">{row.category}</td>
              <td className="text-right">{row.attacks}</td>
              <td className="text-right"><span className={cn('font-bold', row.successes === 0 ? 'text-green' : 'text-red')}>{row.successes}</span></td>
            </tr>
          ))}
        </Table>
      </Card>

      <Card className="space-y-1">
        <h2 className="flex items-center justify-between text-[17px] font-bold text-navy">
          Judge gegen Mensch <SampleTag show={r.judge_calibration.sample} />
        </h2>
        <p className="text-[15px] text-ink-2">
          Cohens Kappa über {r.judge_calibration.n} von Hand bewertete Antworten:{' '}
          <strong className="text-navy">{r.judge_calibration.kappa === null ? 'noch offen' : num(r.judge_calibration.kappa, 2)}</strong>
        </p>
      </Card>
    </div>
  )
}

/** /evals: the latest evaluation report (gates, retrieval ablation, router, answers, red team, judge). */
export function EvalsScreen() {
  const { data, loading, error } = useLoad('latest', () => api.getEvals())
  return (
    <div>
      <ScreenHeader title="Auswertung">
        <h2 className="mt-4 text-[28px] font-extrabold leading-tight">Wie gut arbeitet der Copilot wirklich?</h2>
        {data && <p className="mt-2 text-[15px] opacity-90">Stand {dayLong(data.generated_at.slice(0, 10))}</p>}
      </ScreenHeader>
      <div className="relative z-10 -mt-10 space-y-3 px-4 pb-6">
        {error && <ErrorNote message={error} />}
        {loading && !data && <Skeleton className="h-48 bg-white" />}
        {data && <Report r={data} />}
        <Disclaimer />
      </div>
    </div>
  )
}
