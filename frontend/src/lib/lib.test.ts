import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { readStream } from '../test/helpers'
import type { Customer, FixtureLine, PortfolioView, Product, ToolResult } from '../types/contracts'
import { parseChunkId } from './api'
import { eventWindow } from './events'
import { dayLong, dayShort, eur, num, pct, signedEur, signedPct, topHoldings } from './format'
import { loadApi, pickChatFixture, replay, toolFixture, toolKey } from './fixtures'
import { MIX_IDS, MIXES, RATES, YEARS } from './mixes'

const readApi = (name: string) => JSON.parse(readFileSync(resolve(process.cwd(), `fixtures/api/${name}.json`), 'utf-8'))

describe('German formatting', () => {
  it('uses German separators and a typographic minus', () => {
    expect(num(1234.5, 2)).toBe('1.234,50')
    expect(num(-3.4, 1)).toBe('−3,4')
    expect(eur(11252.28, 2)).toBe('11.252,28 €')
    expect(eur(12000)).toBe('12.000 €')
    expect(pct(0.0015, 2)).toBe('0,15 %')
  })

  it('never shows a negative zero', () => {
    expect(num(-0.004, 2)).toBe('0,00')
    expect(signedPct(-0.001, 1)).toBe('0,0 %')
  })

  it('signs percentages and amounts explicitly', () => {
    expect(signedPct(2.6)).toBe('+2,6 %')
    expect(signedPct(-3.4)).toBe('−3,4 %')
    expect(signedEur(-316.98, 2)).toBe('−316,98 €')
    expect(signedEur(41)).toBe('+41 €')
  })

  it('formats dates in German without time-zone drift', () => {
    expect(dayShort('2026-08-12')).toBe('12. Aug.')
    expect(dayLong('2026-08-12')).toBe('12. August 2026')
    expect(dayShort('2026-01-01')).toBe('1. Jan.')
  })
})

describe('topHoldings', () => {
  const rows = [
    { id: 'a', weight: 0.1 },
    { id: 'b', weight: 0.4 },
    { id: 'c', weight: 0.25 },
    { id: 'd', weight: 0.25 },
  ]

  it('returns the heaviest first, whatever order the API listed them in', () => {
    expect(topHoldings(rows, 3).map((h) => h.id)).toEqual(['b', 'c', 'd'])
  })

  it('does not reorder the input', () => {
    const copy = rows.map((r) => r.id)
    topHoldings(rows, 2)
    expect(rows.map((r) => r.id)).toEqual(copy)
  })
})

describe('eventWindow', () => {
  it('matches the backend rule (day before the shock to the day after it ends)', () => {
    expect(eventWindow({ date: '2026-08-12', duration_days: 2 })).toEqual({ start: '2026-08-11', end: '2026-08-14' })
    expect(eventWindow({ date: '2026-03-01', duration_days: 3 })).toEqual({ start: '2026-02-28', end: '2026-03-04' })
  })

  it('finds an explain_move fixture for every event marker of every persona', async () => {
    const views = readApi('portfolios') as Record<string, PortfolioView>
    for (const [cid, view] of Object.entries(views)) {
      for (const m of view.events) {
        const { start, end } = eventWindow(m.event)
        const hit = await toolFixture<{ change_pct: number }>(toolKey.explain(cid, start, end))
        expect(hit.payload.change_pct).toBe(m.change_pct)
      }
    }
  })
})

describe('fixture coverage for everything the UI can ask', () => {
  type Entry = ToolResult & { request?: { weights: { product_id: string; weight: number }[] } }
  const tools = readApi('tools') as Record<string, Entry>

  it('has a simulation for every rate, duration and mix the buttons offer', () => {
    for (const rate of RATES) {
      for (const years of YEARS) {
        for (const mix of MIX_IDS) {
          expect(tools[toolKey.simulate(rate, years, mix)], `${rate}/${years}/${mix}`).toBeTruthy()
        }
      }
    }
  })

  it('the mixes in mixes.ts are exactly the ones the simulations were built with', () => {
    for (const mix of MIX_IDS) {
      const entry = tools[toolKey.simulate(50, 20, mix)]
      expect(entry.request?.weights).toEqual(MIXES[mix].weights)
      expect(MIXES[mix].weights.reduce((s, w) => s + w.weight, 0)).toBeCloseTo(1)
    }
  })

  it('has costs for every product and rate, and suitability for every persona and product', async () => {
    const products = (await loadApi<Product[]>('products')).map((p) => p.id)
    const customers = (await loadApi<Customer[]>('customers')).map((c) => c.id)
    expect(products).toHaveLength(40)
    for (const p of products) {
      for (const r of RATES) expect(tools[toolKey.cost(p, r, 10)], `cost ${p} ${r}`).toBeTruthy()
      for (const c of customers) expect(tools[toolKey.suitability(c, p)], `suit ${c} ${p}`).toBeTruthy()
    }
    for (const c of customers) expect(tools[toolKey.lookthrough(c)]).toBeTruthy()
  })

  it('reports a missing fixture with a clear message', async () => {
    await expect(toolFixture(toolKey.simulate(77, 3, 'dynamisch'))).rejects.toThrow(/keine aufgezeichnete Antwort/)
  })
})

describe('fixture chat routing', () => {
  it.each([
    ['Ich will monatlich 50 € in nachhaltige Firmen aus Europa stecken. Keine Waffen', 'discover'],
    ['Welche Aktie soll ich kaufen?', 'advice_refusal'],
    ['Soll ich meinen Tech-ETF verkaufen?', 'advice_refusal'],
    ['Warum ist mein Depot im August gefallen?', 'depot_august'],
    ['Was steckt eigentlich in meinem Depot?', 'roentgen'],
    ['Wie entwickeln sich 50 € im Monat über 20 Jahre?', 'simulate'],
    ['Dividenden aus Österreich', 'discover'],
  ])('%s -> %s', (question, expected) => {
    expect(pickChatFixture(question)).toBe(expected)
  })
})

describe('replay', () => {
  const lines = readStream('advice_refusal')

  it('yields every recorded event in order, without the delay field', async () => {
    const out = []
    for await (const ev of replay(lines, { speed: 0 })) out.push(ev)
    expect(out.map((e) => e.event)).toEqual(lines.map((l) => l.event))
    expect(out.every((e) => !('delay_ms' in e))).toBe(true)
  })

  it('stops when aborted', async () => {
    const controller = new AbortController()
    const out: string[] = []
    for await (const ev of replay(lines, { speed: 0, signal: controller.signal })) {
      out.push(ev.event)
      if (out.length === 2) controller.abort()
    }
    expect(out).toHaveLength(2)
  })

  it('honours the recorded delays', async () => {
    const two: FixtureLine[] = [
      { event: 'text_delta', data: { text: 'a' }, delay_ms: 60 },
      { event: 'text_delta', data: { text: 'b' }, delay_ms: 60 },
    ]
    const t0 = performance.now()
    for await (const ev of replay(two, { speed: 1 })) void ev
    expect(performance.now() - t0).toBeGreaterThanOrEqual(100)
  })
})

describe('parseChunkId', () => {
  it('reads product, page and section', () => {
    expect(parseChunkId('KID:P07:p2:kosten')).toEqual({ productId: 'P07', page: 2, section: 'kosten' })
    expect(parseChunkId('KID:P13:p2:sonstige_informationen:2')).toEqual({
      productId: 'P13',
      page: 2,
      section: 'sonstige_informationen',
    })
  })

  it('rejects anything else', () => {
    for (const bad of ['', 'P07', 'KID:P7:p2:kosten', 'DOC:P07:p2:kosten', 'KID:P07:p2:Kosten']) {
      expect(parseChunkId(bad)).toBeNull()
    }
  })
})
