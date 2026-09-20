const BRAND_NAME = import.meta.env.VITE_BRAND_NAME ?? 'Invest Copilot'

/** M1 skeleton: the real shell, screens and blocks arrive in M5. */
export default function App() {
  return (
    <main className="mx-auto max-w-[390px] min-h-screen bg-ground">
      <header className="bg-blue px-4 pt-6 pb-20 text-white">
        <h1 className="text-[28px] font-extrabold leading-tight">{BRAND_NAME}</h1>
        <p className="mt-2 text-[15px] opacity-90">Die KI macht daraus Filter. Entscheiden tust du.</p>
      </header>
      <section className="-mt-10 mx-4 rounded-[20px] bg-card p-4 shadow-[var(--shadow-card)]">
        <span className="rounded-full bg-ai-soft px-2 py-1 text-[13px] font-semibold text-ai">KI</span>
        <p className="mt-3 text-[15px] text-ink-2">Skeleton, Bildschirme folgen.</p>
      </section>
      <footer className="px-4 py-6 text-[13px] text-muted">KI-generiert · Beispieldaten · keine Anlageberatung</footer>
    </main>
  )
}
