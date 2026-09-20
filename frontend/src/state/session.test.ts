import { describe, expect, it } from 'vitest'
import { replay } from '../lib/fixtures'
import { readStream } from '../test/helpers'
import type { SSEEvent } from '../types/contracts'
import { initialState, reducer, type State } from './session'

async function play(stream: string): Promise<{ state: State; events: SSEEvent[] }> {
  let state = reducer(initialState, { type: 'start', question: 'Frage' })
  const events: SSEEvent[] = []
  let seq = 0
  for await (const event of replay(readStream(stream), { speed: 0 })) {
    events.push(event)
    state = reducer(state, { type: 'event', id: 1, entry: { seq: seq++, t: seq * 10, event } })
  }
  return { state, events }
}

describe('session reducer', () => {
  it('starts a streaming message at the top of the list', () => {
    const s1 = reducer(initialState, { type: 'start', question: 'Erste' })
    const s2 = reducer(s1, { type: 'start', question: 'Zweite' })
    expect(s2.messages.map((m) => m.question)).toEqual(['Zweite', 'Erste'])
    expect(s2.messages[0]).toMatchObject({ status: 'streaming', text: '', blocks: [], id: 2 })
    expect(s2.trace).toEqual([]) // the trace panel shows the latest run only
  })

  it('appends text deltas as they arrive, then swaps in the blocks', () => {
    let state = reducer(initialState, { type: 'start', question: 'Frage' })
    const push = (event: SSEEvent) => (state = reducer(state, { type: 'event', id: 1, entry: { seq: 0, t: 0, event } }))
    push({ event: 'text_delta', data: { text: 'Hallo ' } })
    push({ event: 'text_delta', data: { text: 'Welt' } })
    expect(state.messages[0].text).toBe('Hallo Welt')
    expect(state.messages[0].status).toBe('streaming')
    push({ event: 'ui', data: { blocks: [{ type: 'risk_meter', sri: 3 }] } })
    expect(state.messages[0].blocks).toEqual([{ type: 'risk_meter', sri: 3 }])
    push({ event: 'done', data: { trace_id: 't', total_ms: 5, cost_eur: 0 } })
    expect(state.messages[0].status).toBe('done')
  })

  it('shows which step is running while tools work', () => {
    let state = reducer(initialState, { type: 'start', question: 'Frage' })
    state = reducer(state, { type: 'event', id: 1, entry: { seq: 0, t: 0, event: { event: 'tool_start', data: { call_id: 'c', name: 'simulate_savings_plan', args: {} } } } })
    expect(state.messages[0].step).toBe('Rechne den Sparplan durch …')
  })

  it('replays a whole recorded conversation into a finished message and a full trace', async () => {
    const { state, events } = await play('discover')
    const [m] = state.messages
    expect(m.status).toBe('done')
    expect(m.text).toContain('6 passende ETFs')
    expect(m.blocks.map((b) => b.type)).toEqual(['text', 'product_cards', 'citations'])
    expect(state.trace).toHaveLength(events.length)
    expect(state.trace.map((e) => e.seq)).toEqual(events.map((_, i) => i))
  })

  it('the streamed text equals the final text block (no lost or duplicated deltas)', async () => {
    for (const name of ['discover', 'depot_august', 'advice_refusal', 'simulate', 'roentgen']) {
      const { state } = await play(name)
      const text = state.messages[0].blocks[0]
      expect(text.type === 'text' && text.markdown).toBe(state.messages[0].text)
    }
  })

  it('an error event ends the message with the server message', () => {
    let state = reducer(initialState, { type: 'start', question: 'Frage' })
    state = reducer(state, { type: 'event', id: 1, entry: { seq: 0, t: 0, event: { event: 'error', data: { code: 'llm_unavailable', message: 'Modell nicht erreichbar' } } } })
    expect(state.messages[0]).toMatchObject({ status: 'error', error: 'Modell nicht erreichbar' })
  })

  it('a stream that just ends does not stay "streaming" forever', () => {
    let state = reducer(initialState, { type: 'start', question: 'Frage' })
    state = reducer(state, { type: 'end', id: 1 })
    expect(state.messages[0].status).toBe('done')
  })

  it('events of an older run do not touch the newer trace', () => {
    let state = reducer(initialState, { type: 'start', question: 'Alt' })
    state = reducer(state, { type: 'start', question: 'Neu' })
    state = reducer(state, { type: 'event', id: 1, entry: { seq: 0, t: 0, event: { event: 'text_delta', data: { text: 'spät' } } } })
    expect(state.trace).toEqual([])
    expect(state.messages.find((m) => m.id === 1)?.text).toBe('spät')
    expect(state.messages.find((m) => m.id === 2)?.text).toBe('')
  })

  it('reset clears messages and trace', async () => {
    const { state } = await play('advice_refusal')
    expect(reducer(state, { type: 'reset' })).toMatchObject({ messages: [], trace: [] })
  })
})
