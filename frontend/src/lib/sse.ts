/**
 * Server-sent events over POST. `EventSource` cannot POST, so this reads a `fetch` response body with a
 * `ReadableStream` and parses the `event:` / `data:` lines itself.
 *
 * Layers:
 *   SSEParser   text chunks -> raw messages (handles lines split anywhere, CRLF, multi-line data, comments)
 *   readSSE     ReadableStream<Uint8Array> -> raw messages (UTF-8 safe across chunk boundaries)
 *   toEvent     raw message -> typed SSEEvent (malformed input becomes an `error` event, never a throw)
 *   postSSE     fetch + the above, HTTP and network failures become `error` events
 */
import { SSE_EVENT_NAMES, type SSEEvent } from '../types/contracts'

export interface SSEMessage {
  event: string
  data: string
}

export class SSEParser {
  private buffer = ''
  private event = ''
  private data: string[] = []

  /** Feed a text chunk; returns the messages that are complete. A trailing partial line is kept for the next call. */
  push(chunk: string): SSEMessage[] {
    this.buffer += chunk
    // A lone "\r" at the very end may be the first half of "\r\n": keep it until more data arrives.
    const lines = this.buffer.split(/\r\n|\n|\r(?!$)/)
    this.buffer = lines.pop() ?? ''
    const out: SSEMessage[] = []
    for (const line of lines) this.line(line, out)
    return out
  }

  /** End of stream: process a last unterminated line and dispatch a pending event. */
  flush(): SSEMessage[] {
    const out: SSEMessage[] = []
    if (this.buffer !== '') {
      this.line(this.buffer.replace(/\r$/, ''), out)
      this.buffer = ''
    }
    this.dispatch(out)
    return out
  }

  private line(line: string, out: SSEMessage[]): void {
    if (line === '') return this.dispatch(out)
    if (line.startsWith(':')) return // comment / keep-alive
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') this.event = value
    else if (field === 'data') this.data.push(value)
    // `id` and `retry` are not used by this API
  }

  private dispatch(out: SSEMessage[]): void {
    if (this.data.length > 0) out.push({ event: this.event || 'message', data: this.data.join('\n') })
    this.event = ''
    this.data = []
  }
}

export async function* readSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<SSEMessage> {
  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8') // stream: true below keeps multi-byte characters intact across chunks
  const parser = new SSEParser()
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      yield* parser.push(decoder.decode(value, { stream: true }))
    }
    yield* parser.push(decoder.decode())
    yield* parser.flush()
  } finally {
    reader.releaseLock()
  }
}

const KNOWN = new Set<string>(SSE_EVENT_NAMES)

function errorEvent(code: string, message: string): SSEEvent {
  return { event: 'error', data: { code, message } }
}

/** Raw message -> typed event. Unknown event names and invalid JSON become `error` events. */
export function toEvent(msg: SSEMessage): SSEEvent {
  if (!KNOWN.has(msg.event)) return errorEvent('unknown_event', `Unbekanntes Ereignis „${msg.event}“`)
  try {
    return { event: msg.event, data: JSON.parse(msg.data) } as SSEEvent
  } catch {
    return errorEvent('bad_event', `Ereignis „${msg.event}“ enthält kein gültiges JSON`)
  }
}

export interface PostSSEOptions {
  signal?: AbortSignal
  fetchImpl?: typeof fetch
  headers?: Record<string, string>
}

/** POST `body` as JSON and stream the typed events. Never throws: failures arrive as `error` events. */
export async function* postSSE(url: string, body: unknown, opts: PostSSEOptions = {}): AsyncGenerator<SSEEvent> {
  const doFetch = opts.fetchImpl ?? fetch
  let res: Response
  try {
    res = await doFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...opts.headers },
      body: JSON.stringify(body),
      signal: opts.signal,
    })
  } catch (e) {
    if (isAbort(e)) return
    yield errorEvent('network', 'Keine Verbindung zum Server.')
    return
  }
  if (!res.ok || !res.body) {
    yield errorEvent(`http_${res.status}`, `Der Server hat mit ${res.status} geantwortet.`)
    return
  }
  try {
    for await (const msg of readSSE(res.body)) yield toEvent(msg)
  } catch (e) {
    if (isAbort(e)) return
    yield errorEvent('stream_interrupted', 'Die Verbindung wurde unterbrochen.')
  }
}

function isAbort(e: unknown): boolean {
  return e instanceof DOMException ? e.name === 'AbortError' : (e as { name?: string })?.name === 'AbortError'
}
