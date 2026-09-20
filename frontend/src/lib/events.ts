import type { MarketEvent } from '../types/contracts'

function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d + days))
  return dt.toISOString().slice(0, 10)
}

/**
 * The window used to ask "what did this event do to my depot": the day before the shock to the day after it ends.
 * Mirrors `event_window` in backend/app/portfolio_view.py, which builds the fixtures. Keep both in sync.
 */
export function eventWindow(ev: Pick<MarketEvent, 'date' | 'duration_days'>): { start: string; end: string } {
  return { start: addDays(ev.date, -1), end: addDays(ev.date, ev.duration_days) }
}
