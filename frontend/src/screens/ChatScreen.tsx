import { ArrowRight, Play, Sparkles, Square } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useSearchParams } from 'react-router'
import { BlockList } from '../blocks/registry'
import { Card, Chip, Disclaimer, ErrorNote, KiLabel, Overlap, ScreenHeader } from '../components/ui'
import { useSession, type ChatMessage } from '../state/session'

const EXAMPLE = 'Ich will monatlich 50 € in nachhaltige Firmen aus Europa stecken. Keine Waffen, und nicht zu wild schwankend.'
const CHIPS = ['Was steckt eigentlich in meinem Depot?', 'Wie entwickeln sich 50 € im Monat über 20 Jahre?', 'Welche Aktie soll ich kaufen?']

/** One question and its answer: streamed text first, then the blocks the model chose. */
export function Exchange({ message }: { message: ChatMessage }) {
  const hasBlocks = message.blocks.length > 0
  return (
    <article className="space-y-3" aria-label={`Frage: ${message.question}`} data-testid="exchange">
      <p className="ml-auto max-w-[85%] rounded-[20px] rounded-br-[6px] bg-blue px-4 py-3 text-[15px] leading-snug text-white">
        {message.question}
      </p>

      {message.status === 'streaming' && !hasBlocks && (
        <Card tone="ai" className="space-y-2" aria-live="polite" data-testid="streaming">
          <KiLabel />
          {message.text ? (
            <p className="text-[15px] leading-relaxed text-navy">
              {message.text}
              <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-ai align-middle" aria-hidden="true" />
            </p>
          ) : (
            <p className="flex items-center gap-2 text-[15px] text-ai">
              <Sparkles size={16} className="animate-pulse" aria-hidden="true" />
              {message.step ?? 'Denke nach …'}
            </p>
          )}
          {message.text && message.step && <p className="text-[13px] text-ai">{message.step}</p>}
        </Card>
      )}

      {hasBlocks && <BlockList blocks={message.blocks} />}
      {message.status === 'error' && <ErrorNote message={message.error ?? 'Etwas ist schiefgelaufen.'} />}
      {(message.text || hasBlocks) && <Disclaimer />}
    </article>
  )
}

export function ChatScreen() {
  const { messages, running, send, cancel } = useSession()
  const [params, setParams] = useSearchParams()
  const [text, setText] = useState('')
  const handled = useRef(false)

  // "?q=..." (from the home screen or the depot) is sent once, then removed from the URL
  useEffect(() => {
    const q = params.get('q')
    if (q && !handled.current) {
      handled.current = true
      send(q)
      setParams({}, { replace: true })
    }
  }, [params, send, setParams])

  function submit(e?: FormEvent) {
    e?.preventDefault()
    if (!text.trim() || running) return
    send(text)
    setText('')
  }
  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) submit(e)
  }

  return (
    <div>
      <ScreenHeader title="Entdecken" right={<KiLabel className="min-h-11 bg-white/15 px-3 text-[15px] text-white">KI-Suche</KiLabel>}>
        <h2 className="mt-4 text-[28px] font-extrabold leading-tight">Beschreib, was dir wichtig ist.</h2>
        <p className="mt-2 text-[17px] opacity-90">Die KI macht daraus Filter. Entscheiden tust du.</p>
      </ScreenHeader>

      <Overlap className="pb-6">
        <Card>
          <form onSubmit={submit}>
            <label htmlFor="chat-input" className="text-[15px] font-semibold text-muted">
              Deine Beschreibung
            </label>
            <div className="mt-1 flex items-end gap-3">
              <textarea
                id="chat-input"
                rows={2}
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={onKey}
                placeholder="z. B. monatlich 50 € in nachhaltige Firmen aus Europa"
                className="min-h-14 flex-1 resize-none bg-transparent text-[17px] leading-snug text-navy placeholder:text-muted"
              />
              {running ? (
                <button type="button" onClick={cancel} aria-label="Antwort stoppen" className="grid size-12 shrink-0 place-items-center rounded-full bg-navy text-white">
                  <Square size={18} aria-hidden="true" />
                </button>
              ) : (
                <button type="submit" aria-label="Frage senden" disabled={!text.trim()} className="grid size-12 shrink-0 place-items-center rounded-full bg-blue text-white disabled:opacity-50">
                  <ArrowRight size={22} aria-hidden="true" />
                </button>
              )}
            </div>
          </form>
        </Card>

        {messages.length === 0 ? (
          <>
            <h2 className="pt-2 text-[15px] font-semibold text-muted">So könnte es klingen</h2>
            <Card className="space-y-3">
              <p className="text-[17px] leading-snug text-navy">„{EXAMPLE}“</p>
              <button
                type="button"
                onClick={() => send(EXAMPLE)}
                className="inline-flex min-h-11 items-center gap-2 text-[17px] font-bold text-blue-ink"
              >
                <Play size={16} fill="currentColor" aria-hidden="true" /> Beispiel abspielen
              </button>
            </Card>
            <ul className="flex flex-wrap gap-2" aria-label="Weitere Beispiele">
              {CHIPS.map((c) => (
                <li key={c}>
                  <Chip onClick={() => send(c)}>{c}</Chip>
                </li>
              ))}
            </ul>
            <Card className="space-y-3">
              <h2 className="text-[22px] font-bold text-navy">So funktioniert es</h2>
              <ol className="space-y-3">
                {[
                  'Du beschreibst in eigenen Worten, was dir wichtig ist.',
                  'Die KI setzt daraus Filter. Jeder Filter ist sichtbar, nichts passiert im Verborgenen.',
                  'Du vergleichst die Treffer und entscheidest selbst.',
                ].map((t, i) => (
                  <li key={t} className="flex gap-3 text-[17px] leading-snug text-ink-2">
                    <span className="grid size-8 shrink-0 place-items-center rounded-full bg-blue-soft text-[15px] font-bold text-blue-ink">{i + 1}</span>
                    {t}
                  </li>
                ))}
              </ol>
            </Card>
            <Disclaimer />
          </>
        ) : (
          <div className="space-y-8 pt-2">
            {messages.map((m) => (
              <Exchange key={m.id} message={m} />
            ))}
          </div>
        )}
      </Overlap>
    </div>
  )
}
