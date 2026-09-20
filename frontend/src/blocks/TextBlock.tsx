import type { ReactNode } from 'react'
import { api, parseChunkId } from '../lib/api'
import type { TextBlock } from '../types/contracts'
import { Card, KiLabel } from '../components/ui'

/** Source chip in the design's "BIB P07 · S. 2" style. */
export function SourceChip({ chunkId }: { chunkId: string }) {
  const c = parseChunkId(chunkId)
  if (!c) return null
  return (
    <a
      href={api.kidUrl(c.productId, c.page)}
      target="_blank"
      rel="noreferrer"
      className="inline-flex min-h-8 items-center rounded-full border border-ai/25 bg-white px-3 text-[13px] font-semibold text-ai"
    >
      BIB {c.productId} · S. {c.page}
    </a>
  )
}

/** Inline markup used by the model: **bold** and [[cite:CHUNK_ID]] (rendered as numbered source links). */
export function renderInline(text: string, order: string[]): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|\[\[cite:[^\]]+\]\])/).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={i}>{part.slice(2, -2)}</strong>
    const cite = /^\[\[cite:([^\]]+)\]\]$/.exec(part)
    if (cite) {
      const parsed = parseChunkId(cite[1])
      if (!parsed) return null
      if (!order.includes(cite[1])) order.push(cite[1])
      const n = order.indexOf(cite[1]) + 1
      return (
        <a
          key={i}
          href={api.kidUrl(parsed.productId, parsed.page)}
          target="_blank"
          rel="noreferrer"
          aria-label={`Quelle ${n}: Basisinformationsblatt ${parsed.productId}, Seite ${parsed.page}`}
          className="ml-0.5 align-super text-[11px] font-bold text-ai"
        >
          [{n}]
        </a>
      )
    }
    return part
  })
}

/** AI-written text: purple surface, KI label, source chips for every cited chunk. */
export function TextBlockView({ block }: { block: TextBlock }) {
  const order: string[] = []
  const paragraphs = block.markdown.split(/\n{2,}/).map((p, i) => (
    <p key={i} className="text-[15px] leading-relaxed text-navy">
      {renderInline(p, order)}
    </p>
  ))
  const cited = [...new Set([...order, ...block.citations])]
  return (
    <Card tone="ai" className="space-y-3" data-testid="block-text">
      <KiLabel />
      <div className="space-y-2">{paragraphs}</div>
      {cited.length > 0 && (
        <div className="flex flex-wrap gap-2" aria-label="Quellen">
          {cited.map((id) => (
            <SourceChip key={id} chunkId={id} />
          ))}
        </div>
      )}
    </Card>
  )
}
