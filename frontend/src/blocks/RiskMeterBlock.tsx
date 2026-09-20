import { Card } from '../components/ui'
import { SRI_WORDS, SriScale } from '../components/SriScale'
import type { RiskMeterBlock } from '../types/contracts'

export function RiskMeterBlockView({ block }: { block: RiskMeterBlock }) {
  return (
    <Card className="space-y-3" data-testid="block-risk-meter">
      <h3 className="text-[17px] font-bold text-navy">Wie riskant?</h3>
      <SriScale sri={block.sri} />
      <p className="text-[15px] leading-relaxed text-ink-2">
        Stufe {block.sri} von 7 laut Hersteller, also {SRI_WORDS[block.sri]}. Der Wert kann schwanken, Verluste sind
        möglich.
      </p>
    </Card>
  )
}
