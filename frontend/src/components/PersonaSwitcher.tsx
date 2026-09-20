import { usePersona } from '../state/persona'
import { cn } from '../lib/format'

/** Anna, Markus or Elif: the active persona drives portfolio, suitability and chat context. */
export function PersonaSwitcher() {
  const { customers, current, setPersona } = usePersona()
  if (customers.length === 0) return null
  return (
    <div role="radiogroup" aria-label="Persona wechseln" className="flex gap-2">
      {customers.map((c) => {
        const active = c.id === current?.id
        return (
          <button
            key={c.id}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setPersona(c.id)}
            className={cn(
              'min-h-11 flex-1 rounded-full px-3 text-[15px] font-semibold',
              active ? 'bg-white text-blue-ink' : 'bg-white/15 text-white',
            )}
          >
            {c.name}
          </button>
        )
      })}
    </div>
  )
}
