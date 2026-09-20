import { FileText } from 'lucide-react'
import { Card } from '../components/ui'
import { api, parseChunkId } from '../lib/api'
import type { CitationsBlock } from '../types/contracts'

/** The passages an answer is based on, each linking to its page in the KID PDF. */
export function CitationsBlockView({ block }: { block: CitationsBlock }) {
  return (
    <Card tone="ai" className="space-y-3" data-testid="block-citations">
      <h3 className="text-[17px] font-bold text-navy">Quellen</h3>
      <ul className="space-y-3">
        {block.items.map((c) => {
          const id = parseChunkId(c.chunk_id)
          return (
            <li key={c.chunk_id}>
              <a
                href={id ? api.kidUrl(id.productId, c.page) : undefined}
                target="_blank"
                rel="noreferrer"
                className="flex min-h-11 gap-3 rounded-[14px] bg-white px-3 py-2"
              >
                <FileText size={20} className="mt-0.5 shrink-0 text-ai" aria-hidden="true" />
                <span>
                  <span className="block text-[15px] font-semibold text-navy">{c.product_name}</span>
                  <span className="block text-[13px] text-muted">
                    Basisinformationsblatt, S. {c.page} · {c.section}
                  </span>
                  <span className="mt-1 block text-[14px] leading-snug text-ink-2">„{c.snippet}“</span>
                </span>
              </a>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
