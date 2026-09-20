import { Card } from '../components/ui'
import { pct } from '../lib/format'
import type { OverlapMatrixBlock } from '../types/contracts'

/** How much of each product is also in each other product (sum of the smaller weights per company). */
export function OverlapMatrixBlockView({ block }: { block: OverlapMatrixBlock }) {
  return (
    <Card className="space-y-3" data-testid="block-overlap-matrix">
      <h3 className="text-[17px] font-bold text-navy">Wo sich deine Produkte überschneiden</h3>
      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-1 text-[13px]">
          <thead>
            <tr>
              <th scope="col">
                <span className="sr-only">Produkt</span>
              </th>
              {block.products.map((p) => (
                <th key={p.product_id} scope="col" className="px-1 pb-1 text-left font-semibold leading-tight text-ink-2">
                  {p.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.matrix.map((row, i) => (
              <tr key={block.products[i].product_id}>
                <th scope="row" className="pr-2 text-left font-semibold leading-tight text-ink-2">
                  {block.products[i].name}
                </th>
                {row.map((v, j) => (
                  <td
                    key={block.products[j].product_id}
                    className="h-11 min-w-16 rounded-[10px] text-center font-semibold"
                    style={{
                      background: i === j ? 'var(--ground)' : `rgba(36, 99, 235, ${0.08 + v * 0.85})`,
                      color: i !== j && v > 0.4 ? '#fff' : 'var(--navy)',
                    }}
                  >
                    {i === j ? '–' : pct(v, 0)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[13px] leading-snug text-muted">
        Je dunkler das Feld, desto mehr gleiche Unternehmen stecken in beiden Produkten.
      </p>
    </Card>
  )
}
