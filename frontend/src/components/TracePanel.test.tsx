import { describe, expect, it } from 'vitest'
import { readStream } from '../test/helpers'
import type { SSEEvent } from '../types/contracts'
import type { TraceEntry } from '../state/session'
import { buildSteps } from './TracePanel'

/** Trace entries for a recorded stream, timed by the recorded delays. */
function entries(stream: string): TraceEntry[] {
  let t = 0
  return readStream(stream).map(({ delay_ms, ...event }, seq) => ({ seq, t: (t += delay_ms), event: event as SSEEvent }))
}

describe('buildSteps', () => {
  it('turns the discover conversation into the numbered pipeline of design/11', () => {
    const steps = buildSteps(entries('discover'))
    expect(steps.map((s) => s.title)).toEqual([
      'Verstehen',
      'Produkte filtern',
      'Erklären (RAG)',
      'Basisinformationsblätter durchsuchen',
      'Antwort formulieren',
      'Leitplanken-Check',
      'Token und Kosten',
    ])
  })

  it('marks the model steps as AI and the deterministic ones as not', () => {
    const steps = buildSteps(entries('discover'))
    const ai = steps.filter((s) => s.ai).map((s) => s.title)
    expect(ai).toEqual(['Verstehen', 'Antwort formulieren'])
  })

  it('shows the router decision with intent, confidence and model', () => {
    const [router] = buildSteps(entries('discover'))
    expect(router.sub).toBe('Absicht: discover · Sicherheit 96 % · claude-haiku-4-5-20251001')
    expect(router.duration).toBe(412)
  })

  it('shows a tool step with the tool summary, its duration and a start time before its end', () => {
    const trace = entries('discover')
    const tool = buildSteps(trace).find((s) => s.title === 'Produkte filtern')!
    expect(tool.sub).toBe('6 von 24 Produkten passen')
    expect(tool.duration).toBe(3)
    const end = trace.find((e) => e.event.event === 'tool_end')!
    expect(tool.start).toBe(end.t - 3)
  })

  it('an advice request has no tool steps: router, answer, guardrails, cost', () => {
    const steps = buildSteps(entries('advice_refusal'))
    expect(steps.map((s) => s.title)).toEqual(['Verstehen', 'Antwort formulieren', 'Leitplanken-Check', 'Token und Kosten'])
  })

  it('reports an error event as a step', () => {
    const steps = buildSteps([{ seq: 0, t: 5, event: { event: 'error', data: { code: 'network', message: 'Keine Verbindung' } } }])
    expect(steps).toHaveLength(1)
    expect(steps[0]).toMatchObject({ title: 'Fehler', sub: 'network: Keine Verbindung' })
  })

  it('is empty for an empty trace', () => {
    expect(buildSteps([])).toEqual([])
  })

  it('every timed step starts inside the request', () => {
    for (const stream of ['discover', 'depot_august', 'simulate', 'roentgen']) {
      const trace = entries(stream)
      const total = trace.at(-1)!.t
      for (const s of buildSteps(trace)) {
        expect(s.start).toBeGreaterThanOrEqual(0)
        expect(s.start + s.duration).toBeLessThanOrEqual(total)
      }
    }
  })
})
