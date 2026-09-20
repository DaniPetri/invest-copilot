import { Card, StatusIcon } from '../components/ui'
import type { SuitabilityBlock, Verdict } from '../types/contracts'

const VERDICT: Record<Verdict, { label: string; className: string }> = {
  pass: { label: 'Passt zu deinem Profil', className: 'bg-green-soft text-green' },
  warn: { label: 'Passt mit Einschränkungen', className: 'bg-amber-soft text-amber-ink' },
  fail: { label: 'Passt nicht zu deinem Profil', className: 'bg-red-soft text-red' },
}

const FIELD_LABEL: Record<string, string> = {
  risk_class: 'Risikoklasse',
  horizon_years: 'Anlagehorizont',
  sustainability_preference: 'Nachhaltigkeitspräferenz',
  knowledge: 'Kenntnisse',
  experience: 'Erfahrung',
}

export const fieldLabel = (field: string) => FIELD_LABEL[field.split('.')[0]] ?? field

/** Result of the rule-based suitability check: a verdict and one reason per rule, naming the profile field. */
export function SuitabilityBlockView({ block }: { block: SuitabilityBlock }) {
  const v = VERDICT[block.verdict]
  return (
    <Card className="space-y-3" data-testid="block-suitability">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[17px] font-bold text-navy">Passt das zu dir?</h3>
        <span className={`rounded-full px-3 py-1 text-[13px] font-bold ${v.className}`}>{v.label}</span>
      </div>
      <ul className="space-y-3">
        {block.reasons.map((r) => (
          <li key={r.rule} className="flex gap-3">
            <span className="mt-0.5 shrink-0">
              <StatusIcon status={r.status} />
            </span>
            <div>
              <p className="text-[15px] leading-snug text-navy">{r.text}</p>
              <p className="mt-0.5 text-[13px] text-muted">aus deinem Profil: {fieldLabel(r.profile_field)}</p>
            </div>
          </li>
        ))}
      </ul>
      <p className="text-[13px] text-muted">Das ist eine Regelprüfung und keine Empfehlung.</p>
    </Card>
  )
}
