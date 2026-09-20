import { ChartPie, ClipboardCheck, House, Sparkles, TrendingUp, X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router'
import { cn } from '../lib/format'
import { useSession } from '../state/session'
import { TracePanel } from './TracePanel'
import { BRAND_NAME } from './ui'

const NAV = [
  { to: '/', label: 'Übersicht', icon: House, end: true },
  { to: '/chat', label: 'Chat', icon: Sparkles, end: false },
  { to: '/depot', label: 'Depot', icon: ChartPie, end: false },
  { to: '/simulator', label: 'Simulator', icon: TrendingUp, end: false },
  { to: '/evals', label: 'Evals', icon: ClipboardCheck, end: false },
] as const

export function BottomNav() {
  return (
    <nav aria-label="Hauptnavigation" className="shrink-0 border-t border-line bg-white pb-[env(safe-area-inset-bottom)]">
      <ul className="grid grid-cols-5">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'mx-1 my-1 flex min-h-14 flex-col items-center justify-center gap-0.5 rounded-[14px] text-[12px] font-semibold',
                  isActive ? 'bg-blue-soft text-blue-ink' : 'text-muted',
                )
              }
            >
              <Icon size={22} aria-hidden="true" />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}

/** Trace panel as a bottom sheet on screens too narrow to show it next to the phone. */
function TraceSheet() {
  const { traceSheetOpen, setTraceSheetOpen } = useSession()
  const close = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!traceSheetOpen) return
    close.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setTraceSheetOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [traceSheetOpen, setTraceSheetOpen])
  if (!traceSheetOpen) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end bg-navy/50 min-[1100px]:hidden" onClick={() => setTraceSheetOpen(false)}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Unter der Haube"
        className="max-h-[88dvh] w-full overflow-y-auto rounded-t-[28px] bg-ground p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          ref={close}
          type="button"
          onClick={() => setTraceSheetOpen(false)}
          aria-label="Schließen"
          className="mb-2 ml-auto grid size-11 place-items-center rounded-full bg-white"
        >
          <X size={20} aria-hidden="true" />
        </button>
        <TracePanel />
      </div>
    </div>
  )
}

/**
 * Below 1100 px the app fills the screen like a phone app. From 1100 px it sits in a 390 px phone frame with the
 * "Unter der Haube" panel next to it (design/11).
 */
export function AppLayout() {
  const scroller = useRef<HTMLDivElement>(null)
  const { pathname } = useLocation()
  useEffect(() => {
    scroller.current?.scrollTo?.({ top: 0 })
  }, [pathname])

  return (
    <div className="min-h-dvh bg-ground min-[1100px]:min-h-screen">
      <div className="hidden items-center justify-between border-b border-line bg-white px-8 py-3 min-[1100px]:flex">
        <div className="flex items-center gap-3">
          <span aria-hidden="true" className="grid size-10 place-items-center rounded-[10px] bg-blue text-[20px] font-extrabold text-white">
            {BRAND_NAME.charAt(0)}
          </span>
          <div>
            <p className="text-[17px] font-bold leading-tight text-navy">{BRAND_NAME} · KI-Suche</p>
            <p className="text-[13px] text-muted">Live-Demo mit erfundenen Beispielprodukten</p>
          </div>
        </div>
        <nav aria-label="Bereiche" className="flex gap-1 text-[17px] font-semibold">
          {[
            { to: '/', label: 'Demo', end: true },
            { to: '/evals', label: 'Auswertung', end: false },
          ].map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) => cn('rounded-[12px] px-4 py-2', isActive ? 'bg-blue-soft text-blue-ink' : 'text-ink-2')}
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
      </div>

      <div className="min-[1100px]:mx-auto min-[1100px]:flex min-[1100px]:max-w-[1180px] min-[1100px]:items-start min-[1100px]:justify-center min-[1100px]:gap-8 min-[1100px]:px-6 min-[1100px]:py-8">
        <div
          data-testid="phone-frame"
          className={cn(
            'flex h-dvh w-full flex-col overflow-hidden bg-ground',
            'min-[1100px]:sticky min-[1100px]:top-6 min-[1100px]:h-[min(844px,calc(100vh-7rem))] min-[1100px]:w-[390px] min-[1100px]:shrink-0',
            'min-[1100px]:rounded-[44px] min-[1100px]:border-[10px] min-[1100px]:border-navy min-[1100px]:shadow-[0_24px_60px_rgba(15,30,61,.25)]',
          )}
        >
          <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            <Outlet />
          </div>
          <BottomNav />
        </div>

        <div className="hidden min-w-0 max-w-[720px] flex-1 min-[1100px]:block">
          <TracePanel />
        </div>
      </div>
      <TraceSheet />
    </div>
  )
}
