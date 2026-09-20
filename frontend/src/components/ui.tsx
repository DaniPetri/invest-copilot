import { AlertTriangle, ArrowLeft, Check, Sparkles, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { cn } from '../lib/format'
import type { Verdict } from '../types/contracts'

export const BRAND_NAME: string = import.meta.env.VITE_BRAND_NAME ?? 'Invest Copilot'
export const DISCLAIMER = 'KI-generiert · Beispieldaten · keine Anlageberatung'

/** White surface with the design's 20 px radius and soft shadow. Deterministic results use this neutral card. */
export function Card({
  children,
  className,
  tone = 'plain',
  as: Tag = 'section',
  ...rest
}: {
  children: ReactNode
  className?: string
  tone?: 'plain' | 'ai' | 'amber' | 'blue'
  as?: 'section' | 'div' | 'article'
} & React.HTMLAttributes<HTMLElement>) {
  const tones = {
    plain: 'bg-card',
    ai: 'bg-ai-soft',
    amber: 'bg-amber-soft text-amber-ink',
    blue: 'bg-blue text-white',
  }
  return (
    <Tag className={cn('rounded-[20px] p-4 shadow-[var(--shadow-card)]', tones[tone], className)} {...rest}>
      {children}
    </Tag>
  )
}

/** The purple "KI" label on every AI-generated surface. */
export function KiLabel({ children = 'KI', className }: { children?: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full bg-ai-soft px-2 py-1 text-[13px] font-semibold leading-none text-ai',
        className,
      )}
    >
      <Sparkles size={14} aria-hidden="true" />
      {children}
    </span>
  )
}

export function Disclaimer({ className }: { className?: string }) {
  return <p className={cn('px-1 text-[13px] leading-snug text-muted', className)}>{DISCLAIMER}</p>
}

export function Chip({
  children,
  active,
  tone = 'plain',
  className,
  ...rest
}: { children: ReactNode; active?: boolean; tone?: 'plain' | 'blue' | 'ai' } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const tones = {
    plain: 'border-line bg-white text-navy',
    blue: 'border-blue/25 bg-blue-soft text-blue-ink',
    ai: 'border-ai/25 bg-ai-soft text-ai',
  }
  return (
    <button
      type="button"
      className={cn(
        'inline-flex min-h-11 items-center gap-2 rounded-full border px-4 py-2 text-left text-[15px] font-medium',
        tones[tone],
        active && 'border-blue ring-2 ring-blue/30',
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  )
}

/** Gray track with a white selected tab (design/05 "Regionen | Branchen | Top-Titel"). */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div role="tablist" aria-label={label} className="flex rounded-[12px] bg-ground p-1">
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          type="button"
          aria-selected={o.value === value}
          onClick={() => onChange(o.value)}
          className={cn(
            'min-h-11 flex-1 rounded-[10px] px-3 text-[15px] font-semibold',
            o.value === value ? 'bg-white text-navy shadow-sm' : 'text-muted',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** Separate outlined buttons, the selected one filled navy (design/06 levers and design/03 rates). */
export function ChoiceButtons<T extends string | number>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className="grid gap-2" style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}>
      {options.map((o) => (
        <button
          key={String(o.value)}
          role="radio"
          type="button"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={cn(
            'min-h-11 rounded-[14px] border px-2 text-[15px] font-semibold',
            o.value === value ? 'border-navy bg-navy text-white' : 'border-line bg-white text-navy',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** Blue header band. The first card below overlaps it by 40 px (`<Overlap>`). */
export function ScreenHeader({
  title,
  back = true,
  right,
  children,
}: {
  title?: string
  back?: boolean
  right?: ReactNode
  children?: ReactNode
}) {
  const navigate = useNavigate()
  return (
    <header className="bg-blue px-4 pb-16 pt-[max(16px,env(safe-area-inset-top))] text-white">
      <div className="flex min-h-11 items-center justify-between gap-3">
        {back ? (
          <button
            type="button"
            aria-label="Zurück"
            onClick={() => navigate(-1)}
            className="grid size-11 shrink-0 place-items-center rounded-full bg-white/15 text-white"
          >
            <ArrowLeft size={22} aria-hidden="true" />
          </button>
        ) : (
          <span className="size-11 shrink-0" />
        )}
        {title && <h1 className="flex-1 text-center text-[17px] font-bold">{title}</h1>}
        <div className="flex min-w-11 shrink-0 justify-end">{right}</div>
      </div>
      {children}
    </header>
  )
}

/** Pulls its content up over the blue header band. */
export function Overlap({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('relative z-10 -mt-10 space-y-3 px-4', className)}>{children}</div>
}

export function Section({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('space-y-3 px-4', className)}>{children}</div>
}

export function StatusIcon({ status, size = 18 }: { status: Verdict | 'flag'; size?: number }) {
  if (status === 'pass') return <Check size={size} className="text-green" aria-label="passt" />
  if (status === 'fail') return <X size={size} className="text-red" aria-label="passt nicht" />
  return <AlertTriangle size={size} className="text-amber-ink" aria-label="Hinweis" />
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn('animate-pulse rounded-[20px] bg-white/70', className)} />
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <Card tone="amber" role="alert" className="flex items-start gap-2 text-[15px]">
      <AlertTriangle size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
      <span>{message}</span>
    </Card>
  )
}

/** "Quelle: S. 1" badge next to a heading, linking to the KID PDF page. */
export function SourceBadge({ productId, page, href }: { productId: string; page: number; href: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      aria-label={`Quelle: Basisinformationsblatt ${productId}, Seite ${page}`}
      className="relative inline-flex min-h-8 shrink-0 items-center whitespace-nowrap rounded-[10px] bg-ground px-3 text-[13px] font-semibold text-ink-2 after:absolute after:-inset-1.5 after:content-['']"
    >
      Quelle: S. {page}
    </a>
  )
}
