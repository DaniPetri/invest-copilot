/**
 * The chat session: messages that fill in as SSE events arrive, plus the trace of the latest run that the
 * "Unter der Haube" panel shows. Lives above the routes, so leaving /chat and coming back keeps everything.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type ReactNode,
} from 'react'
import { api } from '../lib/api'
import type { SSEEvent, ToolName, UIBlock } from '../types/contracts'
import { usePersona } from './persona'

export interface TraceEntry {
  seq: number
  /** ms since the request started, taken when the event arrived in the browser */
  t: number
  event: SSEEvent
}

export interface ChatMessage {
  id: number
  question: string
  status: 'streaming' | 'done' | 'error'
  /** Text streamed so far; replaced by the `ui` blocks when they arrive */
  text: string
  blocks: UIBlock[]
  /** What the assistant is doing right now, e.g. "Filtere Produkte …" */
  step: string | null
  error: string | null
}

export const TOOL_STEP: Record<ToolName, string> = {
  screen_products: 'Filtere Produkte …',
  search_kid: 'Lese die Basisinformationsblätter …',
  portfolio_lookthrough: 'Durchleuchte dein Depot …',
  explain_move: 'Suche nach Ursachen für die Bewegung …',
  simulate_savings_plan: 'Rechne den Sparplan durch …',
  cost_projection: 'Rechne die Kosten aus …',
  suitability_check: 'Prüfe, was zu deinem Profil passt …',
}

export interface State {
  messages: ChatMessage[]
  trace: TraceEntry[]
  runId: number
}

export type Action =
  | { type: 'start'; question: string }
  | { type: 'event'; id: number; entry: TraceEntry }
  | { type: 'end'; id: number }
  | { type: 'reset' }

export const initialState: State = { messages: [], trace: [], runId: 0 }

function applyEvent(m: ChatMessage, ev: SSEEvent): ChatMessage {
  switch (ev.event) {
    case 'router':
      return { ...m, step: 'Verstehe deine Frage …' }
    case 'tool_start':
      return { ...m, step: TOOL_STEP[ev.data.name] ?? 'Arbeite …' }
    case 'text_delta':
      return { ...m, text: m.text + ev.data.text, step: null }
    case 'ui':
      return { ...m, blocks: ev.data.blocks, step: null }
    case 'done':
      return { ...m, status: 'done', step: null }
    case 'error':
      return { ...m, status: 'error', step: null, error: ev.data.message }
    default:
      return m
  }
}

export function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'start': {
      const id = state.runId + 1
      const message: ChatMessage = { id, question: action.question, status: 'streaming', text: '', blocks: [], step: null, error: null }
      return { messages: [message, ...state.messages], trace: [], runId: id }
    }
    case 'event':
      return {
        ...state,
        messages: state.messages.map((m) => (m.id === action.id ? applyEvent(m, action.entry.event) : m)),
        trace: action.id === state.runId ? [...state.trace, action.entry] : state.trace,
      }
    case 'end':
      // a stream that ends without `done` or `error` (aborted) must not stay "streaming"
      return {
        ...state,
        messages: state.messages.map((m) => (m.id === action.id && m.status === 'streaming' ? { ...m, status: 'done', step: null } : m)),
      }
    case 'reset':
      return { ...initialState, runId: state.runId }
  }
}

interface Session {
  /** Newest first */
  messages: ChatMessage[]
  trace: TraceEntry[]
  running: boolean
  send: (question: string) => void
  cancel: () => void
  reset: () => void
  /** Bottom-sheet with the trace panel on narrow screens */
  traceSheetOpen: boolean
  setTraceSheetOpen: (open: boolean) => void
}

const SessionContext = createContext<Session | null>(null)

export function SessionProvider({ children, speed }: { children: ReactNode; speed?: number }) {
  const { currentId } = usePersona()
  const [state, dispatch] = useReducer(reducer, initialState)
  const abort = useRef<AbortController | null>(null)
  const [sheet, setSheet] = useReducer((_: boolean, v: boolean) => v, false)
  const runIdRef = useRef(0)

  const send = useCallback(
    (question: string) => {
      const text = question.trim()
      if (!text) return
      abort.current?.abort()
      const controller = new AbortController()
      abort.current = controller
      const id = runIdRef.current + 1
      runIdRef.current = id
      dispatch({ type: 'start', question: text })
      const t0 = performance.now()
      void (async () => {
        let seq = 0
        try {
          for await (const event of api.chat(currentId, text, { signal: controller.signal, speed })) {
            dispatch({ type: 'event', id, entry: { seq: seq++, t: Math.round(performance.now() - t0), event } })
          }
        } finally {
          dispatch({ type: 'end', id })
        }
      })()
    },
    [currentId, speed],
  )

  // Stop the stream when the provider really unmounts. StrictMode (dev) unmounts and remounts synchronously, and
  // aborting on that first cleanup killed the request a `?q=` question had just started (the answer never came).
  const mounted = useRef(false)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      setTimeout(() => {
        if (!mounted.current) abort.current?.abort()
      }, 0)
    }
  }, [])

  const value = useMemo<Session>(
    () => ({
      messages: state.messages,
      trace: state.trace,
      running: state.messages[0]?.status === 'streaming',
      send,
      cancel: () => abort.current?.abort(),
      reset: () => {
        abort.current?.abort()
        dispatch({ type: 'reset' })
      },
      traceSheetOpen: sheet,
      setTraceSheetOpen: setSheet,
    }),
    [state, send, sheet],
  )
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): Session {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession must be used inside <SessionProvider>')
  return ctx
}
