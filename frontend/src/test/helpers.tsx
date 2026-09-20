import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { render } from '@testing-library/react'
import { StrictMode } from 'react'
import { MemoryRouter } from 'react-router'
import App from '../App'
import type { FixtureLine, UIBlock } from '../types/contracts'

// vitest runs with the frontend folder as the working directory (import.meta.url is not a file URL under jsdom)
const sseDir = resolve(process.cwd(), 'fixtures/sse') + '/'

export function readStream(name: string): FixtureLine[] {
  return readFileSync(sseDir + name + '.jsonl', 'utf-8')
    .split('\n')
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as FixtureLine)
}

export const STREAM_NAMES = readdirSync(sseDir)
  .filter((f) => f.endsWith('.jsonl'))
  .map((f) => f.replace('.jsonl', ''))
  .sort()

export function blocksOf(stream: string): UIBlock[] {
  const ui = readStream(stream).find((l) => l.event === 'ui')
  return ui && ui.event === 'ui' ? ui.data.blocks : []
}

/** The whole app (all providers and routes) at `path`, in fixture mode with no artificial delays.
 *  `strict` wraps it in StrictMode like main.tsx does, which mounts, unmounts and mounts every component in dev. */
export function renderApp(path = '/', { strict = false }: { strict?: boolean } = {}) {
  const app = (
    <MemoryRouter initialEntries={[path]}>
      <App speed={0} />
    </MemoryRouter>
  )
  return render(strict ? <StrictMode>{app}</StrictMode> : app)
}
