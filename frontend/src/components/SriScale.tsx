import { cn } from '../lib/format'

export const SRI_WORDS: Record<number, string> = {
  1: 'niedrigstes Risiko',
  2: 'niedriges Risiko',
  3: 'niedriges bis mittleres Risiko',
  4: 'mittleres Risiko',
  5: 'mittleres bis hohes Risiko',
  6: 'hohes Risiko',
  7: 'höchstes Risiko',
}

/** The 1-7 risk scale of the KID with the product's class highlighted (design/03). */
export function SriScale({ sri }: { sri: number }) {
  return (
    <div>
      <div role="img" aria-label={`Risikoklasse ${sri} von 7`} className="grid grid-cols-7 gap-2">
        {[1, 2, 3, 4, 5, 6, 7].map((n) => (
          <div
            key={n}
            className={cn(
              'grid h-10 place-items-center rounded-[10px] text-[15px] font-semibold',
              n === sri ? 'bg-blue text-white shadow-[0_4px_12px_rgba(36,99,235,.35)]' : 'bg-ground text-muted',
            )}
          >
            {n}
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-between text-[13px] text-muted">
        <span>geringer</span>
        <span>höher</span>
      </div>
    </div>
  )
}

/** Seven small bars for lists (design/11: "Risiko ▬▬▬▬▬▬▬"). */
export function SriBars({ sri }: { sri: number }) {
  return (
    <span role="img" aria-label={`Risiko ${sri} von 7`} className="inline-flex gap-[3px]">
      {[1, 2, 3, 4, 5, 6, 7].map((n) => (
        <span key={n} className={cn('h-[7px] w-[13px] rounded-[2px]', n <= sri ? 'bg-navy' : 'bg-line')} />
      ))}
    </span>
  )
}
