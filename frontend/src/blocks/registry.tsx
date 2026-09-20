/**
 * One React component per UIBlock type. Blocks come from the server (already hydrated from tool results); the
 * registry renders the ones it knows and silently ignores unknown types, so a newer server never breaks the page.
 */
import type { ReactNode } from 'react'
import { UI_BLOCK_TYPES, type UIBlock } from '../types/contracts'
import { AttributionBlockView } from './AttributionBlock'
import { CitationsBlockView } from './CitationsBlock'
import { CostBreakdownBlockView } from './CostBreakdownBlock'
import { ExposureBarsBlockView } from './ExposureBarsBlock'
import { FanChartBlockView } from './FanChartBlock'
import { HandoffBlockView } from './HandoffBlock'
import { OverlapMatrixBlockView } from './OverlapMatrixBlock'
import { ProductCardsBlockView } from './ProductCardsBlock'
import { RiskMeterBlockView } from './RiskMeterBlock'
import { SuitabilityBlockView } from './SuitabilityBlock'
import { TextBlockView } from './TextBlock'

type Renderers = { [T in UIBlock['type']]: (block: Extract<UIBlock, { type: T }>) => ReactNode }

const RENDERERS: Renderers = {
  text: (b) => <TextBlockView block={b} />,
  product_cards: (b) => <ProductCardsBlockView block={b} />,
  risk_meter: (b) => <RiskMeterBlockView block={b} />,
  fan_chart: (b) => <FanChartBlockView block={b} />,
  exposure_bars: (b) => <ExposureBarsBlockView block={b} />,
  overlap_matrix: (b) => <OverlapMatrixBlockView block={b} />,
  attribution: (b) => <AttributionBlockView block={b} />,
  cost_breakdown: (b) => <CostBreakdownBlockView block={b} />,
  suitability: (b) => <SuitabilityBlockView block={b} />,
  handoff: (b) => <HandoffBlockView block={b} />,
  citations: (b) => <CitationsBlockView block={b} />,
}

export const KNOWN_BLOCK_TYPES: readonly string[] = UI_BLOCK_TYPES

export function isKnownBlock(block: unknown): block is UIBlock {
  return typeof block === 'object' && block !== null && KNOWN_BLOCK_TYPES.includes((block as { type?: string }).type ?? '')
}

/** Renders one block, or nothing for an unknown type. */
export function renderBlock(block: unknown): ReactNode {
  if (!isKnownBlock(block)) return null
  const render = RENDERERS[block.type] as (b: UIBlock) => ReactNode
  return render(block)
}

/** A stack of blocks; unknown types are skipped. */
export function BlockList({ blocks }: { blocks: unknown[] }) {
  return (
    <div className="space-y-3">
      {blocks.map((block, i) => {
        const node = renderBlock(block)
        return node === null ? null : <div key={i}>{node}</div>
      })}
    </div>
  )
}
