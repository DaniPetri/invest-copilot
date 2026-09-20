import { render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { PersonaProvider } from '../state/persona'
import { SessionProvider } from '../state/session'
import { STREAM_NAMES, blocksOf } from '../test/helpers'
import { UI_BLOCK_TYPES, type UIBlock } from '../types/contracts'
import { BlockList, KNOWN_BLOCK_TYPES, isKnownBlock, renderBlock } from './registry'

function Wrap({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter>
      <PersonaProvider>
        <SessionProvider speed={0}>{children}</SessionProvider>
      </PersonaProvider>
    </MemoryRouter>
  )
}

const testId = (type: string) => `block-${type.replaceAll('_', '-')}`
const all = STREAM_NAMES.flatMap((s) => blocksOf(s).map((b) => ({ stream: s, block: b })))
const first = <T extends UIBlock['type']>(type: T) =>
  all.find((x) => x.block.type === type)!.block as Extract<UIBlock, { type: T }>

describe('block registry', () => {
  it('has a renderer for exactly the eleven contract block types', () => {
    expect([...KNOWN_BLOCK_TYPES].sort()).toEqual([...UI_BLOCK_TYPES].sort())
    expect(UI_BLOCK_TYPES).toHaveLength(11)
  })

  it('the fixture streams together contain every block type', () => {
    expect(new Set(all.map((x) => x.block.type))).toEqual(new Set(UI_BLOCK_TYPES))
  })

  it.each(all.map((x, i) => [`${x.stream} / ${x.block.type} #${i}`, x.block] as const))(
    'renders fixture block %s',
    (_name, block) => {
      const { container } = render(<Wrap>{renderBlock(block)}</Wrap>)
      expect(container.querySelector(`[data-testid="${testId(block.type)}"]`)).not.toBeNull()
      expect(container.textContent?.trim().length).toBeGreaterThan(0) // charts draw their labels as SVG
    },
  )

  it('ignores unknown or malformed blocks instead of throwing', () => {
    for (const bad of [{ type: 'iframe', src: 'https://evil.example' }, { type: 'text_v2' }, {}, null, undefined, 'text', 42]) {
      expect(isKnownBlock(bad)).toBe(false)
      expect(renderBlock(bad)).toBeNull()
    }
    const known = first('risk_meter')
    const { container } = render(
      <Wrap>
        <BlockList blocks={[{ type: 'hologram' }, known, null, { type: 'iframe' }]} />
      </Wrap>,
    )
    expect(container.querySelectorAll('[data-testid^="block-"]')).toHaveLength(1)
  })

  it('renders an empty list without crashing', () => {
    const { container } = render(
      <Wrap>
        <BlockList blocks={[]} />
      </Wrap>,
    )
    expect(container.querySelectorAll('[data-testid^="block-"]')).toHaveLength(0)
  })
})

describe('block content', () => {
  it('text: KI label, numbered source links and source chips for the cited chunks', () => {
    const block = blocksOf('discover')[0]
    if (block.type !== 'text') throw new Error('expected text')
    render(<Wrap>{renderBlock(block)}</Wrap>)
    const card = screen.getByTestId('block-text')
    expect(within(card).getByText('KI')).toBeTruthy()
    const links = within(card).getAllByRole('link', { name: /Quelle \d/ })
    expect(links.map((l) => l.textContent)).toEqual(['[1]', '[2]'])
    expect(links[0].getAttribute('href')).toBe('/api/kid/P07.pdf#page=2')
    expect(within(card).getByText('BIB P07 · S. 2')).toBeTruthy()
    expect(within(card).getByText('BIB P07 · S. 1')).toBeTruthy()
    expect(card.textContent).not.toContain('[[cite:') // markup never leaks to the user
  })

  it('text: **bold** is rendered and unknown chunk IDs are dropped', () => {
    render(<Wrap>{renderBlock({ type: 'text', markdown: 'Das ist **wichtig** [[cite:kaputt]]', citations: [] })}</Wrap>)
    expect(screen.getByText('wichtig').tagName).toBe('STRONG')
    expect(screen.getByTestId('block-text').textContent).not.toContain('kaputt')
  })

  it('product_cards: filter chips, hit count and one linked card per item', () => {
    const block = first('product_cards')
    render(<Wrap>{renderBlock(block)}</Wrap>)
    const root = screen.getByTestId('block-product-cards')
    expect(within(root).getByText('Das habe ich verstanden')).toBeTruthy()
    for (const f of block.filters) expect(within(root).getByText(f.label)).toBeTruthy()
    expect(within(root).getByText(`${block.total_matches} Treffer`)).toBeTruthy()
    const cards = within(root).getAllByTestId('product-card')
    expect(cards).toHaveLength(block.items.length)
    expect(cards[0].getAttribute('href')).toBe(`/produkt/${block.items[0].product_id}`)
    expect(within(cards[0]).getByText(/Passt, weil: Sparplan ab 25 €/)).toBeTruthy()
    expect(within(cards[0]).getByText('0,15 % p. a.')).toBeTruthy()
  })

  it('attribution: signed totals, one row per position and the matched event', () => {
    const block = first('attribution')
    render(<Wrap>{renderBlock(block)}</Wrap>)
    const root = screen.getByTestId('block-attribution')
    expect(within(root).getByText(/−2,76 %/)).toBeTruthy()
    expect(within(root).getByText(/−316,98 €/)).toBeTruthy()
    for (const r of block.rows) expect(within(root).getAllByText(new RegExp(r.name)).length).toBeGreaterThan(0)
    expect(within(root).getByText('Chipsektor: schwache Quartalszahlen')).toBeTruthy()
  })

  it('handoff: three options and a stubbed booking that says so', () => {
    render(<Wrap>{renderBlock(first('handoff'))}</Wrap>)
    const root = screen.getByTestId('block-handoff')
    expect(within(root).getByText('Kurz innehalten?')).toBeTruthy()
    expect(within(root).getAllByRole('button')).toHaveLength(3)
  })

  it('suitability: verdict badge and a reason per rule that names the profile field', () => {
    const block = first('suitability')
    render(<Wrap>{renderBlock(block)}</Wrap>)
    const root = screen.getByTestId('block-suitability')
    expect(within(root).getByText(/Passt mit Einschränkungen|Passt zu deinem Profil|Passt nicht zu deinem Profil/)).toBeTruthy()
    expect(within(root).getAllByText(/aus deinem Profil:/)).toHaveLength(block.reasons.length)
    expect(within(root).getByText('Das ist eine Regelprüfung und keine Empfehlung.')).toBeTruthy()
  })

  it('cost_breakdown: total, share of the payments and both cost rows', () => {
    const block = first('cost_breakdown')
    render(<Wrap>{renderBlock(block)}</Wrap>)
    const root = screen.getByTestId('block-cost-breakdown')
    for (const r of block.rows) expect(within(root).getByText(r.label)).toBeTruthy()
    expect(within(root).getByText(/deiner Einzahlungen/)).toBeTruthy()
  })

  it('risk_meter: the class is highlighted and explained', () => {
    render(<Wrap>{renderBlock({ type: 'risk_meter', sri: 5 })}</Wrap>)
    const root = screen.getByTestId('block-risk-meter')
    expect(within(root).getByRole('img', { name: 'Risikoklasse 5 von 7' })).toBeTruthy()
    expect(within(root).getByText(/Stufe 5 von 7 laut Hersteller, also mittleres bis hohes Risiko/)).toBeTruthy()
  })

  it('overlap_matrix: a labelled table with a cell for every product pair', () => {
    const block = first('overlap_matrix')
    render(<Wrap>{renderBlock(block)}</Wrap>)
    const root = screen.getByTestId('block-overlap-matrix')
    const table = within(root).getByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(block.products.length + 1)
    expect(within(table).getAllByRole('cell')).toHaveLength(block.products.length ** 2)
  })

  it('fan_chart and exposure_bars: accessible summary of the chart', () => {
    render(<Wrap>{renderBlock(first('fan_chart'))}</Wrap>)
    expect(screen.getByRole('img', { name: /Fächerdiagramm über 20 Jahre/ })).toBeTruthy()
    expect(screen.getByText('1 von 20 schlechter als')).toBeTruthy()
    render(<Wrap>{renderBlock(first('exposure_bars'))}</Wrap>)
    expect(screen.getAllByRole('img', { name: /^(Branchen|Länder):/ }).length).toBeGreaterThan(0)
  })

  it('citations: every source links to its KID page', () => {
    const block = first('citations')
    render(<Wrap>{renderBlock(block)}</Wrap>)
    const links = within(screen.getByTestId('block-citations')).getAllByRole('link')
    expect(links).toHaveLength(block.items.length)
    expect(links[0].getAttribute('href')).toBe('/api/kid/P07.pdf#page=2')
  })
})
