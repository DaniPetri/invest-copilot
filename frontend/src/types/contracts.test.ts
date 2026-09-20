// @vitest-environment node
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { validate, type Schema } from '../lib/schema'
import { SSE_EVENT_NAMES, UI_BLOCK_TYPES, type FixtureLine } from './contracts'

const contractsDir = fileURLToPath(new URL('../../../contracts/', import.meta.url))
const fixtureDir = fileURLToPath(new URL('../../fixtures/sse/', import.meta.url))

const load = (name: string) => JSON.parse(readFileSync(contractsDir + name, 'utf-8')) as Schema
const sse = load('sse_event.schema.json')
const uiBlock = load('ui_block.schema.json')
const tools = load('tools.schema.json')

const fixtures = readdirSync(fixtureDir)
  .filter((f) => f.endsWith('.jsonl'))
  .sort()
  .map((file) => ({
    file,
    lines: readFileSync(fixtureDir + file, 'utf-8')
      .split('\n')
      .filter((l) => l.trim())
      .map((l) => JSON.parse(l) as FixtureLine),
  }))

function stripDelay(line: FixtureLine) {
  const { delay_ms: _delay, ...event } = line
  return event
}

describe('contracts: drift between contracts.ts and the exported schemas', () => {
  it('SSE_EVENT_NAMES equals the schema discriminator mapping', () => {
    const mapping = (sse.discriminator as { mapping: Record<string, string> }).mapping
    expect([...SSE_EVENT_NAMES].sort()).toEqual(Object.keys(mapping).sort())
  })

  it('UI_BLOCK_TYPES equals the ui_block discriminator mapping', () => {
    const mapping = (uiBlock.discriminator as { mapping: Record<string, string> }).mapping
    expect([...UI_BLOCK_TYPES].sort()).toEqual(Object.keys(mapping).sort())
  })
})

describe('contracts: fixture streams validate against the schemas', () => {
  it('finds the five fixture streams', () => {
    expect(fixtures.map((f) => f.file)).toEqual([
      'advice_refusal.jsonl',
      'depot_august.jsonl',
      'discover.jsonl',
      'roentgen.jsonl',
      'simulate.jsonl',
    ])
  })

  for (const { file, lines } of fixtures) {
    it(`${file}: every event is valid`, () => {
      const errors = lines.flatMap((line, i) =>
        validate(sse, stripDelay(line)).map((e) => `line ${i + 1} (${line.event}): ${e}`),
      )
      expect(errors).toEqual([])
    })

    it(`${file}: has a delay on every line`, () => {
      expect(lines.every((l) => Number.isInteger(l.delay_ms) && l.delay_ms >= 0)).toBe(true)
    })

    it(`${file}: order is trace, router ... done`, () => {
      const names = lines.map((l) => l.event)
      expect(names[0]).toBe('trace')
      expect(names[1]).toBe('router')
      expect(names.at(-1)).toBe('done')
      expect(names.indexOf('text_delta')).toBeLessThan(names.indexOf('ui'))
    })
  }

  it('product_cards items validate against the tools schema ScreenItem', () => {
    const ui = fixtures.flatMap((f) => f.lines).find((l) => l.event === 'ui' && l.data.blocks.some((b) => b.type === 'product_cards'))
    const cards = ui?.event === 'ui' ? ui.data.blocks.find((b) => b.type === 'product_cards') : undefined
    expect(cards?.type).toBe('product_cards')
    if (cards?.type !== 'product_cards') return
    for (const item of cards.items) {
      expect(validate({ $ref: '#/$defs/ScreenItem' }, item, tools)).toEqual([])
    }
  })
})

describe('contracts: invalid input is rejected', () => {
  const trace = { event: 'trace', data: { trace_id: 't', started_at: '2026-09-20T00:00:00Z', mode: 'replay' } }

  it('accepts a minimal valid event', () => {
    expect(validate(sse, trace)).toEqual([])
  })

  it('rejects an unknown event name', () => {
    expect(validate(sse, { event: 'mystery', data: {} })).not.toEqual([])
  })

  it('rejects an extra field', () => {
    expect(validate(sse, { ...trace, data: { ...trace.data, extra: 1 } })).not.toEqual([])
  })

  it('rejects a wrong enum value', () => {
    expect(validate(sse, { ...trace, data: { ...trace.data, mode: 'turbo' } })).not.toEqual([])
  })

  it('rejects an unknown UI block type', () => {
    expect(validate(uiBlock, { type: 'iframe', src: 'https://evil.example' })).not.toEqual([])
  })

  it('rejects out-of-range SRI', () => {
    expect(validate(uiBlock, { type: 'risk_meter', sri: 8 })).not.toEqual([])
    expect(validate(uiBlock, { type: 'risk_meter', sri: 4 })).toEqual([])
  })
})


// ── the API fixtures (frontend/fixtures/api) against the exported schemas ───

const apiDir = fileURLToPath(new URL('../../fixtures/api/', import.meta.url))
const loadApi = (name: string) => JSON.parse(readFileSync(apiDir + name, 'utf-8'))
const products = load('products.schema.json')
const portfolio = load('portfolio.schema.json')
const evals = load('evals.schema.json')

describe('contracts: API fixtures validate against the schemas', () => {
  it('customers.json is a list of Customer', () => {
    const customers = loadApi('customers.json') as unknown[]
    expect(customers).toHaveLength(3)
    customers.forEach((c, i) => expect(validate({ $ref: '#/$defs/Customer' }, c, portfolio), `customer ${i}`).toEqual([]))
  })

  it('products.json is a list of 40 Product', () => {
    const list = loadApi('products.json') as unknown[]
    expect(list).toHaveLength(40)
    list.forEach((p, i) => expect(validate({ $ref: '#/$defs/Product' }, p, products), `product ${i}`).toEqual([]))
  })

  it('portfolios.json maps every persona to a PortfolioView', () => {
    const views = loadApi('portfolios.json') as Record<string, unknown>
    expect(Object.keys(views).sort()).toEqual(['anna', 'elif', 'markus'])
    for (const [id, v] of Object.entries(views)) {
      expect(validate({ $ref: '#/$defs/PortfolioView' }, v, portfolio), id).toEqual([])
    }
  })

  it('every tools.json entry is a ToolResult whose payload matches its output schema', () => {
    const outputs: Record<string, string> = {
      explain: 'ExplainMoveOutput',
      lookthrough: 'LookthroughOutput',
      simulate: 'SimulateOutput',
      cost: 'CostProjectionOutput',
      suitability: 'SuitabilityOutput',
    }
    const results = loadApi('tools.json') as Record<string, { payload: unknown; ok: boolean; result_id: string }>
    const seen = new Set<string>()
    for (const [key, result] of Object.entries(results)) {
      const kind = key.split('|')[0]
      seen.add(kind)
      expect(result.ok && result.result_id === 'r1', key).toBe(true)
      expect(validate({ $ref: `#/$defs/${outputs[kind]}` }, result.payload, tools), key).toEqual([])
    }
    expect([...seen].sort()).toEqual(Object.keys(outputs).sort())
  })

  it('evals.json is an EvalReport', () => {
    expect(validate({ $ref: '#/$defs/EvalReport' }, loadApi('evals.json'), evals)).toEqual([])
  })

  it('a bad payload is rejected (the check has teeth)', () => {
    const view = structuredClone(loadApi('portfolios.json').markus)
    view.positions[0].sri = 9
    expect(validate({ $ref: '#/$defs/PortfolioView' }, view, portfolio)).not.toEqual([])
  })
})
