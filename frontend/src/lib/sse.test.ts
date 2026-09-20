// @vitest-environment node
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { postSSE, readSSE, SSEParser, toEvent, type SSEMessage } from './sse'
import type { FixtureLine, SSEEvent } from '../types/contracts'

const enc = new TextEncoder()

function parseAll(chunks: string[]): SSEMessage[] {
  const p = new SSEParser()
  return [...chunks.flatMap((c) => p.push(c)), ...p.flush()]
}

function streamOf(chunks: (string | Uint8Array)[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(typeof c === 'string' ? enc.encode(c) : c)
      controller.close()
    },
  })
}

async function collect<T>(gen: AsyncGenerator<T>): Promise<T[]> {
  const out: T[] = []
  for await (const x of gen) out.push(x)
  return out
}

describe('SSEParser', () => {
  it('parses event and data lines', () => {
    expect(parseAll(['event: trace\ndata: {"a":1}\n\n'])).toEqual([{ event: 'trace', data: '{"a":1}' }])
  })

  it('handles several events in one chunk and defaults the event name to "message"', () => {
    const out = parseAll(['data: eins\n\nevent: done\ndata: zwei\n\n'])
    expect(out).toEqual([
      { event: 'message', data: 'eins' },
      { event: 'done', data: 'zwei' },
    ])
  })

  it('gives the same result when the stream is split at every possible position (chunks split mid-line)', () => {
    const text = 'event: router\ndata: {"intent":"discover"}\n\nevent: text_delta\ndata: {"text":"Grüße"}\n\n'
    const whole = parseAll([text])
    expect(whole).toHaveLength(2)
    for (let i = 1; i < text.length; i++) {
      expect(parseAll([text.slice(0, i), text.slice(i)])).toEqual(whole)
    }
    expect(parseAll([...text].map((c) => c))).toEqual(whole) // one character at a time
  })

  it('joins multi-line data with newlines', () => {
    const out = parseAll(['event: ui\ndata: {\ndata:   "blocks": []\ndata: }\n\n'])
    expect(out[0].data).toBe('{\n  "blocks": []\n}')
    expect(JSON.parse(out[0].data)).toEqual({ blocks: [] })
  })

  it('accepts CRLF and CR line endings, also when "\\r" and "\\n" arrive in different chunks', () => {
    const expected = [{ event: 'done', data: '{}' }]
    expect(parseAll(['event: done\r\ndata: {}\r\n\r\n'])).toEqual(expected)
    expect(parseAll(['event: done\rdata: {}\r\r'])).toEqual(expected)
    expect(parseAll(['event: done\r', '\ndata: {}\r', '\n\r', '\n'])).toEqual(expected)
  })

  it('ignores comments and unknown fields, and strips exactly one leading space', () => {
    const out = parseAll([': keep-alive\nid: 7\nretry: 100\nevent: text_delta\ndata:  zwei Leerzeichen\n\n'])
    expect(out).toEqual([{ event: 'text_delta', data: ' zwei Leerzeichen' }])
    expect(parseAll(['data:ohne Leerzeichen\n\n'])[0].data).toBe('ohne Leerzeichen')
  })

  it('does not dispatch events without data, and does not carry state over', () => {
    expect(parseAll(['event: orphan\n\ndata: x\n\n'])).toEqual([{ event: 'message', data: 'x' }])
  })

  it('flushes a last event that has no blank line after it', () => {
    const p = new SSEParser()
    expect(p.push('event: done\ndata: {"ok":true}')).toEqual([])
    expect(p.flush()).toEqual([{ event: 'done', data: '{"ok":true}' }])
    expect(p.flush()).toEqual([])
  })

  it('keeps an empty data line as an empty string', () => {
    expect(parseAll(['event: text_delta\ndata:\n\n'])).toEqual([{ event: 'text_delta', data: '' }])
  })
})

describe('readSSE', () => {
  it('decodes UTF-8 characters that are cut in the middle of their bytes', async () => {
    const bytes = enc.encode('event: text_delta\ndata: {"text":"Ärger über 5 € Gebühr"}\n\n')
    const chunks = Array.from(bytes, (b) => Uint8Array.of(b)) // one byte per chunk splits ä, ü and €
    const out = await collect(readSSE(streamOf(chunks)))
    expect(out).toHaveLength(1)
    expect(JSON.parse(out[0].data).text).toBe('Ärger über 5 € Gebühr')
  })

  it('flushes an unterminated final event at the end of the stream', async () => {
    const out = await collect(readSSE(streamOf(['event: done\ndata: {"trace_id":"t"}'])))
    expect(out).toEqual([{ event: 'done', data: '{"trace_id":"t"}' }])
  })
})

describe('toEvent', () => {
  it('parses a known event', () => {
    expect(toEvent({ event: 'text_delta', data: '{"text":"Hallo"}' })).toEqual({
      event: 'text_delta',
      data: { text: 'Hallo' },
    })
  })

  it('passes a server-sent error event through unchanged', () => {
    const msg = { event: 'error', data: '{"code":"llm_unavailable","message":"Modell nicht erreichbar"}' }
    expect(toEvent(msg)).toEqual({
      event: 'error',
      data: { code: 'llm_unavailable', message: 'Modell nicht erreichbar' },
    })
  })

  it('turns invalid JSON into an error event instead of throwing', () => {
    const ev = toEvent({ event: 'ui', data: '{"blocks": [' })
    expect(ev.event).toBe('error')
    expect(ev.event === 'error' && ev.data.code).toBe('bad_event')
  })

  it('turns an unknown event name into an error event', () => {
    const ev = toEvent({ event: 'mystery', data: '{}' })
    expect(ev.event === 'error' && ev.data.code).toBe('unknown_event')
  })
})

describe('postSSE', () => {
  const fixture = readFileSync(fileURLToPath(new URL('../../fixtures/sse/discover.jsonl', import.meta.url)), 'utf-8')
    .split('\n')
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as FixtureLine)
  const wire = fixture.map((l) => `event: ${l.event}\ndata: ${JSON.stringify(l.data)}\n\n`).join('')

  const respond = (chunks: (string | Uint8Array)[], init?: ResponseInit) =>
    (async () => new Response(streamOf(chunks), { status: 200, ...init })) as typeof fetch

  it('streams a full recorded conversation, however the bytes are chunked', async () => {
    const bytes = enc.encode(wire)
    const sizes = [1, 3, 7, 64, 500]
    for (const size of sizes) {
      const chunks: Uint8Array[] = []
      for (let i = 0; i < bytes.length; i += size) chunks.push(bytes.slice(i, i + size))
      const events = await collect(postSSE('/api/chat', { message: 'x' }, { fetchImpl: respond(chunks) }))
      expect(events.map((e) => e.event)).toEqual(fixture.map((l) => l.event))
      expect(events[0]).toEqual({ event: 'trace', data: fixture[0].data })
    }
  })

  it('sends the body as JSON with a POST', async () => {
    let seen: { url: string; init: RequestInit } | undefined
    const fetchImpl = (async (url: string, init: RequestInit) => {
      seen = { url, init }
      return new Response(streamOf([]), { status: 200 })
    }) as unknown as typeof fetch
    await collect(postSSE('/api/chat', { customer_id: 'anna', message: 'Hallo' }, { fetchImpl }))
    expect(seen?.url).toBe('/api/chat')
    expect(seen?.init.method).toBe('POST')
    expect(JSON.parse(String(seen?.init.body))).toEqual({ customer_id: 'anna', message: 'Hallo' })
    expect((seen?.init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('reports an HTTP error as an error event', async () => {
    const events = await collect(postSSE('/api/chat', {}, { fetchImpl: respond([], { status: 500 }) }))
    expect(events).toEqual<SSEEvent[]>([
      { event: 'error', data: { code: 'http_500', message: 'Der Server hat mit 500 geantwortet.' } },
    ])
  })

  it('reports a network failure as an error event', async () => {
    const fetchImpl = (async () => {
      throw new TypeError('Failed to fetch')
    }) as unknown as typeof fetch
    const events = await collect(postSSE('/api/chat', {}, { fetchImpl }))
    expect(events).toHaveLength(1)
    expect(events[0].event === 'error' && events[0].data.code).toBe('network')
  })

  it('reports a dropped connection mid-stream and keeps the events received before', async () => {
    let pulls = 0
    const stream = new ReadableStream<Uint8Array>({
      pull(c) {
        // first read delivers one event, the second read fails like a dropped connection
        if (pulls++ === 0) c.enqueue(enc.encode('event: trace\ndata: {"trace_id":"t","started_at":"x","mode":"replay"}\n\n'))
        else c.error(new Error('connection reset'))
      },
    })
    const fetchImpl = (async () => new Response(stream, { status: 200 })) as unknown as typeof fetch
    const events = await collect(postSSE('/api/chat', {}, { fetchImpl }))
    expect(events.map((e) => e.event)).toEqual(['trace', 'error'])
    expect(events[1].event === 'error' && events[1].data.code).toBe('stream_interrupted')
  })

  it('ends quietly when the request is aborted', async () => {
    const controller = new AbortController()
    controller.abort()
    const fetchImpl = (async (_: string, init: RequestInit) => {
      if (init.signal?.aborted) throw new DOMException('aborted', 'AbortError')
      return new Response(streamOf([]))
    }) as unknown as typeof fetch
    expect(await collect(postSSE('/api/chat', {}, { fetchImpl, signal: controller.signal }))).toEqual([])
  })

  it('keeps going after a malformed event in the middle of the stream', async () => {
    const chunks = [
      'event: text_delta\ndata: {"text":"a"}\n\n',
      'event: ui\ndata: not json\n\n',
      'event: done\ndata: {"trace_id":"t","total_ms":1,"cost_eur":0}\n\n',
    ]
    const events = await collect(postSSE('/api/chat', {}, { fetchImpl: respond(chunks) }))
    expect(events.map((e) => e.event)).toEqual(['text_delta', 'error', 'done'])
  })
})
