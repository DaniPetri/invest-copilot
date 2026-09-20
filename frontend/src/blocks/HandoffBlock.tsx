import { ChevronRight, HandHelping } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { Card } from '../components/ui'
import type { HandoffBlock } from '../types/contracts'

/**
 * Hand-off to a human adviser plus alternatives that stay information, not advice (design/09: three options of
 * equal weight). Known actions navigate; `book_advisor` is a stub because there is no booking system in this demo.
 */
export function HandoffBlockView({ block }: { block: HandoffBlock }) {
  const navigate = useNavigate()
  const [booked, setBooked] = useState(false)

  function run(id: string) {
    if (id === 'filter_search') navigate('/chat')
    else if (id === 'simulate') navigate('/simulator')
    else if (id === 'book_advisor') setBooked(true)
  }

  return (
    <Card className="space-y-3" data-testid="block-handoff">
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-blue-soft text-blue">
          <HandHelping size={20} aria-hidden="true" />
        </span>
        <div>
          <h3 className="text-[22px] font-bold leading-tight text-navy">Kurz innehalten?</h3>
          <p className="mt-1 text-[15px] leading-snug text-ink-2">{block.reason} Die Entscheidung bleibt bei dir.</p>
        </div>
      </div>
      <div className="space-y-2">
        {block.actions.map((a) => (
          <button
            key={a.id}
            type="button"
            onClick={() => run(a.id)}
            className="flex min-h-14 w-full items-center justify-between gap-3 rounded-[14px] border border-line bg-white px-4 text-left text-[17px] font-bold text-navy"
          >
            {a.label}
            <ChevronRight size={20} className="shrink-0 text-muted" aria-hidden="true" />
          </button>
        ))}
      </div>
      {booked && (
        <p role="status" className="rounded-[12px] bg-blue-soft px-3 py-2 text-[15px] text-blue-ink">
          Beispieldaten: An dieser Stelle würde ein Termin mit einer Beraterin oder einem Berater vereinbart.
        </p>
      )}
    </Card>
  )
}
