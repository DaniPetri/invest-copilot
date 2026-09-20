/** German number and date formatting (1.234,56 €). Numbers themselves always come from tool results. */

const MINUS = '−' // typographic minus, as in the designs

const cache = new Map<string, Intl.NumberFormat>()
function nf(decimals: number): Intl.NumberFormat {
  let f = cache.get(String(decimals))
  if (!f) {
    f = new Intl.NumberFormat('de-DE', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
    cache.set(String(decimals), f)
  }
  return f
}

/** 1234.5, 2 -> "1.234,50" (negative numbers get a typographic minus). */
export function num(x: number, decimals = 0): string {
  const rounded = Number(Math.abs(x).toFixed(decimals))
  const s = nf(decimals).format(rounded)
  return x < 0 && rounded !== 0 ? MINUS + s : s
}

/** 1234.5 -> "1.234,50 €" */
export function eur(x: number, decimals = 0): string {
  return `${num(x, decimals)} €`
}

/** Explicitly signed: "+2,6 %" / "−3,4 %". `value` is already a percentage. */
export function signedPct(value: number, decimals = 1): string {
  const n = num(value, decimals)
  return `${value > 0 && !n.startsWith(MINUS) ? '+' : ''}${n} %`
}

export function signedEur(x: number, decimals = 0): string {
  const n = num(x, decimals)
  return `${x > 0 && !n.startsWith(MINUS) ? '+' : ''}${n} €`
}

/** A fraction as percent: 0.0015 -> "0,15 %" */
export function pct(fraction: number, decimals = 1): string {
  return `${num(fraction * 100, decimals)} %`
}

const shortDate = new Intl.DateTimeFormat('de-DE', { day: 'numeric', month: 'short' })
const longDate = new Intl.DateTimeFormat('de-DE', { day: 'numeric', month: 'long', year: 'numeric' })
const monthOnly = new Intl.DateTimeFormat('de-DE', { month: 'long' })

/** ISO date (2026-08-12) -> Date at local noon, immune to time zone shifts. */
export function parseDay(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d, 12)
}

export const dayShort = (iso: string) => shortDate.format(parseDay(iso)) // "12. Aug."
export const dayLong = (iso: string) => longDate.format(parseDay(iso)) // "12. August 2026"
export const monthName = (iso: string) => monthOnly.format(parseDay(iso)) // "August"

export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ')
}

/** The `n` heaviest holdings, largest first. The API does not promise an order (bond and money-market funds list
 *  their issuers unsorted), so never rely on it. Ties keep their listed order. */
export function topHoldings<T extends { weight: number }>(holdings: readonly T[], n: number): T[] {
  return [...holdings].sort((a, b) => b.weight - a.weight).slice(0, n)
}
