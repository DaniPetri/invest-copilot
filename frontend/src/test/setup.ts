import { afterEach } from 'vitest'

// Files that opt into `@vitest-environment node` have no DOM: only set up jsdom-based tests.
if (typeof window !== 'undefined') {
  // jsdom lacks these; recharts and the layout use them
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver
  Element.prototype.scrollTo ??= () => {}
  window.scrollTo ??= () => {}
  window.matchMedia ??= ((query: string) => ({
    matches: false,
    media: query,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
    onchange: null,
  })) as unknown as typeof window.matchMedia

  afterEach(async () => {
    const { cleanup } = await import('@testing-library/react')
    cleanup()
    try {
      localStorage.clear()
    } catch {
      /* ignore */
    }
  })
}
