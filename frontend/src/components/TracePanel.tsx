/**
 * "Unter der Haube" (design/11): what happened for the latest request, built live from the SSE events.
 * AI steps are purple, deterministic steps neutral. Timing bars show when each step ran within the request.
 */
import { Check, ShieldCheck, X } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { useFixtures } from '../lib/api'
import { cn, eur, num, pct } from '../lib/format'
import { useSession, type TraceEntry } from '../state/session'
import type { GuardrailCheck, RetrievalChunk, SSEEvent, ToolName } from '../types/contracts'
import { Card, KiLabel, Segmented } from './ui'

type Event<K extends SSEEvent['event']> = Extract<SSEEvent, { event: K }>['data']

const TOOL_LABEL: Record<ToolName, string> = {
  screen_products: 'Produkte filtern',
  search_kid: 'Basisinformationsblätter durchsuchen',
  portfolio_lookthrough: 'Depot durchleuchten',
  explain_move: 'Depotbewegung erklären',
  simulate_savings_plan: 'Sparplan simulieren',
  cost_projection: 'Kosten berechnen',
  suitability_check: 'Eignung prüfen',
}

const CHECK_LABEL: Record<string, string> = {
  pii: 'Personenbezogene Daten',
  quarantine: 'Quarantäne',
  citations: 'Quellenverweise',
  numeric_grounding: 'Zahlen belegt',
  advice_language: 'Keine Empfehlungssprache',
  ai_label: 'KI-Kennzeichnung',
}

interface Step {
  key: string
  title: string
  ai: boolean
  sub?: string
  /** when the step started and how long it took, in ms since the request began */
  start: number
  duration: number
  body?: ReactNode
}

const FLAG_LABEL = {
  advice_request: 'Beratungsfrage',
  injection_suspected: 'Prompt-Injection vermutet',
  pii_present: 'Personenbezogene Daten',
} as const

export function buildSteps(trace: TraceEntry[]): Step[] {
  const steps: Step[] = []
  const starts = new Map<string, TraceEntry>()
  let firstDelta: TraceEntry | undefined
  let textChars = 0
  const usage: Event<'usage'>[] = []

  trace.forEach((entry, i) => {
    const { event, t } = entry
    switch (event.event) {
      case 'router': {
        const d = event.data
        const flags = (Object.keys(FLAG_LABEL) as (keyof typeof FLAG_LABEL)[]).filter((k) => d.flags[k])
        steps.push({
          key: `router-${i}`,
          title: 'Verstehen',
          ai: true,
          sub: `Absicht: ${d.intent} · Sicherheit ${pct(d.confidence, 0)} · ${d.model}`,
          start: Math.max(0, t - d.latency_ms),
          duration: d.latency_ms,
          body: flags.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-2">
              {flags.map((f) => (
                <li key={f} className="rounded-full bg-amber-soft px-2 py-1 text-[13px] font-semibold text-amber-ink">
                  {FLAG_LABEL[f]}
                </li>
              ))}
            </ul>
          ),
        })
        break
      }
      case 'tool_start':
        starts.set(event.data.call_id, entry)
        break
      case 'tool_end': {
        const d = event.data
        const begin = starts.get(d.call_id)
        const args = begin && begin.event.event === 'tool_start' ? begin.event.data.args : {}
        steps.push({
          key: `tool-${d.call_id}`,
          title: TOOL_LABEL[d.name] ?? d.name,
          ai: false,
          sub: d.summary,
          start: Math.max(0, t - d.duration_ms),
          duration: d.duration_ms,
          body: (
            <details open className="mt-2">
              <summary className="cursor-pointer text-[13px] font-semibold text-muted">
                <code>{d.name}</code>
                {d.ok ? '' : ' · Fehler'} · Argumente
              </summary>
              <pre className="mt-1 max-h-44 overflow-auto rounded-[12px] bg-navy p-3 text-[12px] leading-snug text-white">
                {JSON.stringify(args, null, 2)}
              </pre>
            </details>
          ),
        })
        break
      }
      case 'retrieval': {
        const d = event.data
        steps.push({
          key: `retrieval-${i}`,
          title: 'Erklären (RAG)',
          ai: false,
          sub: `„${d.query}“ · Modus ${d.mode} · ${d.chunks.length} Abschnitte`,
          start: t,
          duration: 0,
          body: <RetrievalHits chunks={d.chunks} />,
        })
        break
      }
      case 'text_delta':
        firstDelta ??= entry
        textChars += event.data.text.length
        break
      case 'ui': {
        const kinds = event.data.blocks.map((b) => b.type)
        const begin = firstDelta?.t ?? t
        steps.push({
          key: `answer-${i}`,
          title: 'Antwort formulieren',
          ai: true,
          sub: `${num(textChars)} Zeichen gestreamt · ${kinds.length} Bausteine: ${kinds.join(', ')}`,
          start: begin,
          duration: Math.max(0, t - begin),
        })
        break
      }
      case 'guardrail':
        steps.push({
          key: `guardrail-${i}`,
          title: 'Leitplanken-Check',
          ai: false,
          sub: 'Quellen vorhanden, Zahlen belegt, keine Empfehlungssprache',
          start: t,
          duration: 0,
          body: <Checks checks={event.data.checks} />,
        })
        break
      case 'usage':
        usage.push(event.data)
        break
      case 'error':
        steps.push({ key: `error-${i}`, title: 'Fehler', ai: false, sub: `${event.data.code}: ${event.data.message}`, start: t, duration: 0 })
        break
    }
  })

  if (usage.length > 0) {
    const last = trace.at(-1)?.t ?? 0
    steps.push({
      key: 'usage',
      title: 'Token und Kosten',
      ai: false,
      start: last,
      duration: 0,
      body: <Usage rows={usage} />,
    })
  }
  return steps
}

function RetrievalHits({ chunks }: { chunks: RetrievalChunk[] }) {
  const max = Math.max(...chunks.map((c) => c.score), 1e-9)
  return (
    <ul className="mt-2 space-y-1.5" aria-label="Treffer">
      {chunks.map((c) => {
        const quarantined = c.flags.includes('possible_injection')
        return (
          <li key={c.id} className="flex items-center gap-2 text-[12px]">
            <code className={cn('w-44 shrink-0 truncate', quarantined && 'text-red')} title={c.id}>
              {c.id}
            </code>
            <span className="h-1.5 flex-1 rounded bg-ground">
              <span className={cn('block h-full rounded', quarantined ? 'bg-red' : 'bg-blue')} style={{ width: `${(c.score / max) * 100}%` }} />
            </span>
            <span className="w-14 shrink-0 text-right tabular-nums text-muted">{c.score.toFixed(4)}</span>
            {quarantined && <span className="rounded-full bg-red-soft px-2 py-0.5 font-semibold text-red">Quarantäne</span>}
          </li>
        )
      })}
    </ul>
  )
}

function Checks({ checks }: { checks: GuardrailCheck[] }) {
  return (
    <ul className="mt-2 space-y-1">
      {checks.map((c) => (
        <li key={c.name} className="flex items-start gap-2 text-[13px]" title={c.detail}>
          {c.status === 'pass' ? (
            <Check size={16} className="mt-0.5 shrink-0 text-green" aria-label="bestanden" />
          ) : c.status === 'fail' ? (
            <X size={16} className="mt-0.5 shrink-0 text-red" aria-label="durchgefallen" />
          ) : (
            <ShieldCheck size={16} className="mt-0.5 shrink-0 text-amber-ink" aria-label="auffällig" />
          )}
          <span>
            <span className="font-semibold text-navy">{CHECK_LABEL[c.name] ?? c.name}</span>
            <span className="text-muted"> · {c.detail}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

function Usage({ rows }: { rows: Event<'usage'>[] }) {
  const total = rows.reduce((s, r) => s + r.cost_eur, 0)
  return (
    <table className="mt-2 w-full text-[13px]">
      <thead className="text-left text-muted">
        <tr>
          <th className="font-semibold">Modell</th>
          <th className="text-right font-semibold">Eingabe</th>
          <th className="text-right font-semibold">Ausgabe</th>
          <th className="text-right font-semibold">Kosten</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td className="py-0.5 pr-2 font-mono text-[12px]">{r.model}</td>
            <td className="text-right tabular-nums">{num(r.input_tokens)}</td>
            <td className="text-right tabular-nums">{num(r.output_tokens)}</td>
            <td className="text-right tabular-nums">{eur(r.cost_eur, 4)}</td>
          </tr>
        ))}
        <tr className="border-t border-line font-bold text-navy">
          <td className="pt-1" colSpan={3}>
            Summe
          </td>
          <td className="pt-1 text-right tabular-nums">{eur(total, 4)}</td>
        </tr>
      </tbody>
    </table>
  )
}

export function ModeBadge({ mode }: { mode: string | undefined }) {
  const label = mode === 'live' ? 'Live-Modus' : mode === 'record' ? 'Aufnahme-Modus' : 'Replay-Modus'
  return (
    <span
      data-testid="mode-badge"
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[13px] font-bold',
        mode === 'live' ? 'bg-green-soft text-green' : 'bg-ai-soft text-ai',
      )}
    >
      <span className="size-2 rounded-full bg-current" aria-hidden="true" />
      {label}
    </span>
  )
}

export function TracePanel() {
  const { trace, messages, running } = useSession()
  const [tab, setTab] = useState<'flow' | 'json'>('flow')
  const steps = useMemo(() => buildSteps(trace), [trace])
  const traceEvent = trace.find((e) => e.event.event === 'trace')?.event
  const mode = traceEvent?.event === 'trace' ? traceEvent.data.mode : useFixtures() ? 'replay' : undefined
  const done = trace.find((e) => e.event.event === 'done')?.event
  const totalMs = done?.event === 'done' ? done.data.total_ms : (trace.at(-1)?.t ?? 0)
  const question = messages[0]?.question

  return (
    <aside aria-label="Unter der Haube" className="space-y-4" data-testid="trace-panel">
      <Card className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="text-[22px] font-extrabold text-navy">Unter der Haube</h2>
            <p className="mt-1 text-[15px] text-ink-2">Was bei jeder Anfrage passiert. Die KI-Schritte sind lila markiert.</p>
          </div>
          <ModeBadge mode={mode} />
        </div>
        {question && (
          <p className="rounded-[12px] bg-ground px-3 py-2 text-[14px] text-ink-2">
            <span className="font-semibold text-navy">Anfrage: </span>„{question}“
          </p>
        )}
        {(done?.event === 'done' || traceEvent?.event === 'trace') && (
          <dl className="grid grid-cols-3 gap-2 text-[13px]">
            <Meta label="Trace" value={traceEvent?.event === 'trace' ? traceEvent.data.trace_id.replace('tr_', '') : '–'} />
            <Meta label="Dauer" value={done?.event === 'done' ? `${num(done.data.total_ms)} ms` : running ? 'läuft …' : '–'} />
            <Meta label="Kosten" value={done?.event === 'done' ? eur(done.data.cost_eur, 4) : '–'} />
          </dl>
        )}
      </Card>

      <Card className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-[22px] font-extrabold text-navy">Ablauf</h2>
          <div className="w-52">
            <Segmented
              label="Ansicht"
              value={tab}
              onChange={setTab}
              options={[
                { value: 'flow', label: 'Ablauf' },
                { value: 'json', label: 'JSON' },
              ]}
            />
          </div>
        </div>
        {trace.length === 0 ? (
          <p className="text-[15px] text-muted">
            Stelle im Chat eine Frage. Dann siehst du hier jeden Schritt: Absicht, Werkzeuge, Quellen, Leitplanken und
            Kosten.
          </p>
        ) : tab === 'flow' ? (
          <ol className="divide-y divide-line">
            {steps.map((s, i) => (
              <StepRow key={s.key} n={i + 1} step={s} total={totalMs} />
            ))}
          </ol>
        ) : (
          <pre className="max-h-[520px] overflow-auto rounded-[14px] bg-navy p-4 text-[12px] leading-snug text-white" data-testid="trace-json">
            {JSON.stringify(
              trace.map((e) => ({ seq: e.seq, t: e.t, ...e.event })),
              null,
              2,
            )}
          </pre>
        )}
      </Card>
    </aside>
  )
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[12px] bg-ground px-3 py-2">
      <dt className="text-muted">{label}</dt>
      <dd className="mt-0.5 truncate font-semibold text-navy">{value}</dd>
    </div>
  )
}

function StepRow({ n, step, total }: { n: number; step: Step; total: number }) {
  const left = total > 0 ? (step.start / total) * 100 : 0
  const width = total > 0 ? Math.max((step.duration / total) * 100, step.duration > 0 ? 1.5 : 0) : 0
  return (
    <li className="py-3" data-testid="trace-step">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            'grid size-8 shrink-0 place-items-center rounded-full text-[15px] font-bold',
            step.ai ? 'border-2 border-ai bg-ai-soft text-ai' : 'bg-green-soft text-green',
          )}
        >
          {n}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <h3 className="flex items-center gap-2 text-[17px] font-bold text-navy">
              {step.title}
              {step.ai && <KiLabel />}
            </h3>
            <span className="shrink-0 text-[13px] tabular-nums text-muted">{step.duration > 0 ? `${num(step.duration)} ms` : ''}</span>
          </div>
          {step.sub && <p className="mt-0.5 text-[14px] leading-snug text-ink-2">{step.sub}</p>}
          {step.duration > 0 && (
            <div className="mt-2 h-1.5 rounded bg-ground" aria-hidden="true" data-testid="timing-bar">
              <div className={cn('h-full rounded', step.ai ? 'bg-ai' : 'bg-blue')} style={{ marginLeft: `${left}%`, width: `${width}%` }} />
            </div>
          )}
          {step.body}
        </div>
      </div>
    </li>
  )
}
