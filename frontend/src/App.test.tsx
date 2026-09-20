import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { eventWindow } from './lib/events'
import { eur, signedEur, signedPct } from './lib/format'
import { api } from './lib/api'
import { renderApp } from './test/helpers'
import type { PortfolioView, ToolResult } from './types/contracts'

const readApi = <T,>(name: string): T => JSON.parse(readFileSync(resolve(process.cwd(), `fixtures/api/${name}.json`), 'utf-8'))
const portfolios = readApi<Record<string, PortfolioView>>('portfolios')
const tools = readApi<Record<string, ToolResult<Record<string, number>>>>('tools')

const DISCLAIMER = 'KI-generiert · Beispieldaten · keine Anlageberatung'
const SLOW = { timeout: 8000 }

async function ask(question: string) {
  fireEvent.change(await screen.findByLabelText('Deine Beschreibung'), { target: { value: question } })
  fireEvent.click(screen.getByRole('button', { name: 'Frage senden' }))
}

describe('chat screen renders a full fixture stream', () => {
  it('discover: streamed text, filter chips, product cards, sources, trace and disclaimer', async () => {
    renderApp('/chat')
    fireEvent.click(await screen.findByRole('button', { name: /Beispiel abspielen/ }))

    // the question appears at once, the answer fills in
    // (it also shows in the trace panel's "Anfrage:" line, so expect it more than once)
    expect((await screen.findAllByText(/Ich will monatlich 50 € in nachhaltige Firmen/, {}, SLOW)).length).toBeGreaterThanOrEqual(2)
    expect(await screen.findByText('6 Treffer', {}, SLOW)).toBeTruthy()

    const chat = screen.getByTestId('exchange')
    // AI text: KI label, numbered source links, source chips
    const text = within(chat).getByTestId('block-text')
    expect(within(text).getByText('KI')).toBeTruthy()
    expect(within(text).getByText(/6 passende ETFs gefunden/)).toBeTruthy()
    expect(within(text).getAllByRole('link', { name: /Quelle \d/ })).toHaveLength(2)
    expect(within(text).getByText('BIB P07 · S. 2')).toBeTruthy()
    // "Das habe ich verstanden" filter chips
    for (const label of ['Sparplan-fähig', 'Nur ETFs', 'Region: Europa', 'Nachhaltig (Art. 8 oder 9)', 'Ohne Waffenhersteller', 'Risiko höchstens 4 von 7', 'Kosten höchstens 0,30 % p. a.']) {
      expect(within(chat).getByText(label)).toBeTruthy()
    }
    // deterministic result cards, each linking to its product page
    const cards = within(chat).getAllByTestId('product-card')
    expect(cards).toHaveLength(3)
    expect(within(cards[0]).getByText('Europa Paris-Aligned Klima ETF')).toBeTruthy()
    expect(cards[0].getAttribute('href')).toBe('/produkt/P07')
    // sources and the required footer on the AI surface
    expect(within(chat).getByTestId('block-citations')).toBeTruthy()
    expect(within(chat).getByText(DISCLAIMER)).toBeTruthy()
    // no markup or raw JSON leaks into the answer
    expect(chat.textContent).not.toMatch(/\[\[cite:|"type":|undefined|NaN/)
  })

  it('shows the live trace next to it: router, tool call with arguments, retrieval hits, guardrails, cost', async () => {
    renderApp('/chat')
    fireEvent.click(await screen.findByRole('button', { name: /Beispiel abspielen/ }))
    const trace = await screen.findByTestId('trace-panel')
    await within(trace).findByText('Token und Kosten', {}, SLOW)

    expect(within(trace).getByTestId('mode-badge').textContent).toContain('Replay-Modus')
    // router decision
    expect(within(trace).getByText(/Absicht: discover · Sicherheit 96 %/)).toBeTruthy()
    // tool call with its arguments
    expect(within(trace).getByText('Produkte filtern')).toBeTruthy()
    expect(within(trace).getByText('6 von 24 Produkten passen')).toBeTruthy()
    expect(trace.textContent).toContain('"asset_classes"')
    expect(trace.textContent).toContain('"max_ter": 0.003')
    // retrieval hits with scores
    expect(within(trace).getByText('KID:P07:p2:kosten')).toBeTruthy()
    expect(within(trace).getByText('0.0328')).toBeTruthy()
    // guardrail checks and cost
    expect(within(trace).getByText('Leitplanken-Check')).toBeTruthy()
    expect(within(trace).getByText('Quellenverweise')).toBeTruthy()
    expect(within(trace).getByText('claude-sonnet-5')).toBeTruthy()
    expect(within(trace).getByText('4.210 ms')).toBeTruthy()
    // AI steps are labelled, and there are timing bars
    expect(within(trace).getAllByText('KI').length).toBeGreaterThanOrEqual(2)
    expect(within(trace).getAllByTestId('timing-bar').length).toBeGreaterThanOrEqual(3)
  })

  it('the JSON tab shows the raw events', async () => {
    renderApp('/chat')
    fireEvent.click(await screen.findByRole('button', { name: /Beispiel abspielen/ }))
    const trace = await screen.findByTestId('trace-panel')
    await within(trace).findByText('Token und Kosten', {}, SLOW)
    fireEvent.click(within(trace).getByRole('tab', { name: 'JSON' }))
    const json = within(trace).getByTestId('trace-json').textContent ?? ''
    expect(json).toContain('"event": "router"')
    expect(json).toContain('"event": "done"')
  })

  it('an advice request ends in a hand-off with three options, and no tool call', async () => {
    renderApp('/chat')
    await ask('Welche Aktie soll ich kaufen?')
    expect(await screen.findByText('Kurz innehalten?', {}, SLOW)).toBeTruthy()
    const handoff = screen.getByTestId('block-handoff')
    expect(within(handoff).getAllByRole('button').map((b) => b.textContent)).toEqual([
      'Nach Kriterien suchen',
      'Sparplan durchrechnen',
      'Mit einer Beraterin sprechen',
    ])
    expect(screen.getByText(/Eine persönliche Empfehlung darf ich dir nicht geben/)).toBeTruthy()
    const trace = screen.getByTestId('trace-panel')
    await within(trace).findByText('Token und Kosten', {}, SLOW)
    expect(within(trace).getByText('Beratungsfrage')).toBeTruthy() // router flag
    expect(within(trace).queryByText('Produkte filtern')).toBeNull()
    fireEvent.click(within(handoff).getByRole('button', { name: 'Mit einer Beraterin sprechen' }))
    expect(within(handoff).getByRole('status').textContent).toContain('Beispieldaten')
  })

  it('the August question explains the fall with real numbers and the matching event', async () => {
    renderApp('/chat')
    await ask('Warum ist mein Depot im August gefallen?')
    const block = await screen.findByTestId('block-attribution', {}, SLOW)
    expect(within(block).getByText(/−2,76 %/)).toBeTruthy()
    expect(within(block).getByText(/−316,98 €/)).toBeTruthy()
    expect(within(block).getByText('Chipsektor: schwache Quartalszahlen')).toBeTruthy()
    expect(screen.getByText(/Dein Depot ist im August um 2,76 % gefallen/)).toBeTruthy()
  })

  it('a new question goes on top and keeps the earlier answer', async () => {
    renderApp('/chat')
    await ask('Welche Aktie soll ich kaufen?')
    await screen.findByText('Kurz innehalten?', {}, SLOW)
    await ask('Was steckt eigentlich in meinem Depot?')
    await screen.findByTestId('block-overlap-matrix', {}, SLOW)
    const exchanges = screen.getAllByTestId('exchange')
    expect(exchanges).toHaveLength(2)
    expect(within(exchanges[0]).getByText('Was steckt eigentlich in meinem Depot?')).toBeTruthy()
    expect(within(exchanges[1]).getByText('Welche Aktie soll ich kaufen?')).toBeTruthy()
  })

  it('sends a question passed from another screen (?q=) exactly once', async () => {
    renderApp('/chat?q=' + encodeURIComponent('Welche Aktie soll ich kaufen?'))
    expect(await screen.findByText('Kurz innehalten?', {}, SLOW)).toBeTruthy()
    expect(screen.getAllByTestId('exchange')).toHaveLength(1)
  })

  it('answers a ?q= question under StrictMode too (dev mounts, unmounts and remounts; that must not abort the stream)', async () => {
    renderApp('/chat?q=' + encodeURIComponent('Welche Aktie soll ich kaufen?'), { strict: true })
    expect(await screen.findByText('Kurz innehalten?', {}, SLOW)).toBeTruthy()
    expect(screen.getAllByTestId('exchange')).toHaveLength(1)
    expect(screen.getByTestId('exchange').textContent).not.toContain('Antwort abgebrochen')
  })
})

describe('chat is asked as the selected persona', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  // Loading the customer list takes a moment; a ?q= question sent on page load used to fall back to Markus.
  it.each(['anna', 'elif', 'markus'])('a ?q= question on page load is sent as %s', async (persona) => {
    localStorage.setItem('invest-copilot.persona', persona)
    const chat = vi.spyOn(api, 'chat').mockImplementation(async function* () {})
    renderApp('/chat?q=' + encodeURIComponent('Was kostet der Welt ETF?'))
    await waitFor(() => expect(chat).toHaveBeenCalledTimes(1))
    expect(chat.mock.calls[0][0]).toBe(persona)
  })

  it('a question typed after switching persona is sent as the new persona', async () => {
    localStorage.setItem('invest-copilot.persona', 'markus')
    const chat = vi.spyOn(api, 'chat').mockImplementation(async function* () {})
    renderApp('/')
    fireEvent.click(await screen.findByRole('radio', { name: 'Anna' }))
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Hauptnavigation' })).getByRole('link', { name: 'Chat' }))
    await ask('Was kostet der Welt ETF?')
    await waitFor(() => expect(chat).toHaveBeenCalled())
    expect(chat.mock.calls.at(-1)![0]).toBe('anna')
  })
})

describe('screens', () => {
  it('Übersicht: value, 3-month change, positions, persona switcher and bottom navigation', async () => {
    renderApp('/')
    const markus = portfolios.markus
    expect(await screen.findByTestId('depot-value')).toBeTruthy()
    await waitFor(() => expect(screen.getByTestId('depot-value').textContent).toBe(eur(markus.total_value_eur, 2)))
    expect(screen.getByText(new RegExp(signedPct(markus.change_3m_pct).replace('+', '\\+') + ' in 3 Monaten'))).toBeTruthy()
    for (const p of markus.positions) expect(screen.getByText(p.name)).toBeTruthy()
    expect(screen.getByRole('link', { name: /Welt ETF/ }).getAttribute('href')).toBe('/produkt/P03')
    const nav = screen.getByRole('navigation', { name: 'Hauptnavigation' })
    expect(within(nav).getAllByRole('link').map((l) => l.textContent)).toEqual(['Übersicht', 'Chat', 'Depot', 'Simulator', 'Evals'])
    expect(within(nav).getByRole('link', { name: 'Übersicht' }).getAttribute('aria-current')).toBe('page')
  })

  it('switching the persona changes the portfolio everywhere', async () => {
    renderApp('/')
    fireEvent.click(await screen.findByRole('radio', { name: 'Anna' }))
    await waitFor(() => expect(screen.getByTestId('depot-value').textContent).toBe(eur(portfolios.anna.total_value_eur, 2)))
    expect(screen.getByRole('radio', { name: 'Anna' }).getAttribute('aria-checked')).toBe('true')
    fireEvent.click(screen.getByRole('radio', { name: 'Elif' }))
    await waitFor(() => expect(screen.getByTestId('depot-value').textContent).toBe(eur(portfolios.elif.total_value_eur, 2)))
  })

  it('the home input sends the question to the chat', async () => {
    renderApp('/')
    fireEvent.change(await screen.findByLabelText(/Frag /), { target: { value: 'Welche Aktie soll ich kaufen?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Frage senden' }))
    expect(await screen.findByText('Kurz innehalten?', {}, SLOW)).toBeTruthy()
  })

  it('Depot: event markers, tapping one runs explain_move and shows the attribution', async () => {
    renderApp('/depot')
    const view = portfolios.markus
    const e12 = view.events.find((m) => m.event.id === 'E12')!
    const detail = await screen.findByTestId('event-detail', {}, SLOW)
    expect(within(detail).getByText(new RegExp(`12\\. Aug\\.: ${signedPct(e12.change_pct)} \\(${signedEur(e12.change_eur)}\\)`))).toBeTruthy()
    const { start, end } = eventWindow(e12.event)
    const expected = tools[`explain|markus|${start}|${end}`].payload
    expect(await within(detail).findByText(/Wer hat wie viel beigetragen/, {}, SLOW)).toBeTruthy()
    expect(within(detail).getByRole('button', { name: /Erklären lassen/ })).toBeTruthy()
    expect(expected.change_pct).toBe(e12.change_pct)
    // the 3-month view has one marker; the 1-year view shows all three
    expect(screen.getAllByRole('button', { name: /Aug\./ })).toHaveLength(1)
    fireEvent.click(screen.getByRole('radio', { name: '1 J.' }))
    await waitFor(() => expect(screen.getByRole('list', { name: 'Ereignisse im Verlauf' }).querySelectorAll('button')).toHaveLength(3))
  })

  it('Depot: the Röntgen shows overlap, the concentration hint and switchable exposure', async () => {
    renderApp('/depot')
    const roentgen = await screen.findByRole('region', { name: 'Depot-Röntgen' }, SLOW)
    expect(within(roentgen).getByText(/Du hältst 3 Produkte/)).toBeTruthy()
    expect(within(roentgen).getByTestId('block-overlap-matrix')).toBeTruthy()
    expect(within(roentgen).getByTestId('roentgen-note').textContent).toContain('keine Empfehlung')
    fireEvent.click(within(roentgen).getByRole('tab', { name: 'Länder' }))
    expect(within(roentgen).getByRole('img', { name: /^Länder:/ })).toBeTruthy()
  })

  it('Produkt: KID summary, source badges, cost calculator as a direct tool call, and the persona fit', async () => {
    renderApp('/produkt/P07')
    expect(await screen.findByRole('heading', { name: 'Europa Paris-Aligned Klima ETF' }, SLOW)).toBeTruthy()
    expect(screen.getByRole('img', { name: 'Risikoklasse 4 von 7' })).toBeTruthy()
    expect(screen.getByRole('link', { name: /Quelle: Basisinformationsblatt P07, Seite 1/ }).getAttribute('href')).toBe('/api/kid/P07.pdf#page=1')
    expect(screen.getByRole('link', { name: /Seite 2/ })).toBeTruthy()

    const c50 = tools['cost|P07|50|10'].payload
    const cost = await screen.findByTestId('cost-result', {}, SLOW)
    expect(cost.textContent).toContain(eur(c50.total_eur))
    fireEvent.click(screen.getByRole('radio', { name: '250 €' }))
    const c250 = tools['cost|P07|250|10'].payload
    await waitFor(() => expect(screen.getByTestId('cost-result').textContent).toContain(eur(c250.total_eur)))

    const fit = await screen.findByTestId('product-fit', {}, SLOW)
    expect(within(fit).getByText('Für Markus')).toBeTruthy()
    expect(within(fit).getAllByText(/aus deinem Profil:/)).toHaveLength(5)
  })

  it('Simulator: three levers, each change is a fresh simulation', async () => {
    renderApp('/simulator')
    expect(await screen.findByText(/50 € im Monat, 20 Jahre lang\. 5\.000 mögliche Zukünfte\./, {}, SLOW)).toBeTruthy()
    const base = tools['simulate|50|20|ausgewogen'].payload as unknown as { p50: number[] }
    expect(await screen.findByText(eur(base.p50.at(-1)!))).toBeTruthy()
    fireEvent.click(screen.getByRole('radio', { name: '100 €' }))
    fireEvent.click(screen.getByRole('radio', { name: '10 J.' }))
    fireEvent.click(screen.getByRole('radio', { name: 'Dynamisch' }))
    expect(await screen.findByText(/100 € im Monat, 10 Jahre lang/, {}, SLOW)).toBeTruthy()
    const changed = tools['simulate|100|10|dynamisch'].payload
    expect(await screen.findByText(eur(changed.total_contributions))).toBeTruthy()
    expect(screen.getByTestId('simulator-words').textContent).toContain('Das ist keine Prognose')
  })

  it('Evals: measured gates (the red one included), the retrieval table and the judge calibration', async () => {
    renderApp('/evals')
    expect(await screen.findByText('Freigabe-Schwellen', {}, SLOW)).toBeTruthy()
    expect(screen.queryByTestId('sample-banner')).toBeNull()
    const gates = screen.getByTestId('gates')
    expect(within(gates).queryByText('Beispielwert')).toBeNull()
    expect(within(gates).getAllByText('bestanden').length).toBe(6)
    const failed = within(gates).getByText('nicht bestanden')
    expect(failed.closest('li')!.textContent).toContain('Beratungsanfragen erkannt: 93,3 % (Schwelle 95 %)')
    const row = screen.getByText('Hybrid (RRF)').closest('tr')!
    expect(row.textContent).toContain('0,920')
    expect(screen.getByText('Hybrid + Reranker').closest('tr')!.textContent).toContain('Stichprobe, 270 Fragen')
    expect(screen.getByText('noch offen')).toBeTruthy()
  })

  it('an unknown route goes back to the Übersicht', async () => {
    renderApp('/gibt-es-nicht')
    expect(await screen.findByTestId('depot-value')).toBeTruthy()
  })

  it('every screen carries the AI footer where AI content lives', async () => {
    for (const path of ['/', '/chat', '/depot', '/simulator', '/evals']) {
      const { unmount } = renderApp(path)
      expect(await screen.findAllByText(DISCLAIMER, {}, SLOW), path).not.toHaveLength(0)
      unmount()
    }
  })
})
