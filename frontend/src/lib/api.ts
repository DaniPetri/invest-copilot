/**
 * API client. In fixture mode (VITE_USE_FIXTURES=1) every call is answered from frontend/fixtures, so the UI works
 * without a backend; otherwise it talks to the FastAPI server (proxied under /api by Vite in development).
 */
import type {
  CostProjectionPayload,
  Customer,
  EvalReport,
  ExplainMovePayload,
  LookthroughPayload,
  PortfolioView,
  Product,
  SSEEvent,
  SimulatePayload,
  SuitabilityPayload,
  ToolName,
  ToolResult,
} from '../types/contracts'
import {
  loadApi,
  loadSSE,
  pickChatFixture,
  replay,
  toolFixture,
  toolKey,
  type ApiFixtureName,
} from './fixtures'
import { MIXES, type MixId } from './mixes'
import { postSSE } from './sse'

export const useFixtures = (): boolean => import.meta.env.VITE_USE_FIXTURES === '1'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError(0, 'Keine Verbindung zum Server.')
  }
  if (!res.ok) {
    let detail = `Fehler ${res.status}`
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

function callTool<P>(name: ToolName, args: Record<string, unknown>): Promise<ToolResult<P>> {
  return request<ToolResult<P>>(`/api/tools/${name}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(args),
  })
}

const fromFixture = <T>(name: ApiFixtureName) => loadApi<T>(name)

export const api = {
  async getCustomers(): Promise<Customer[]> {
    return useFixtures() ? fromFixture<Customer[]>('customers') : request<Customer[]>('/api/customers')
  },

  async getProducts(): Promise<Product[]> {
    return useFixtures() ? fromFixture<Product[]>('products') : request<Product[]>('/api/products')
  },

  async getProduct(id: string): Promise<Product> {
    if (useFixtures()) {
      const hit = (await fromFixture<Product[]>('products')).find((p) => p.id === id)
      if (!hit) throw new ApiError(404, `Produkt ${id} nicht gefunden`)
      return hit
    }
    return request<Product>(`/api/products/${id}`)
  },

  async getPortfolio(customerId: string): Promise<PortfolioView> {
    if (useFixtures()) {
      const hit = (await fromFixture<Record<string, PortfolioView>>('portfolios'))[customerId]
      if (!hit) throw new ApiError(404, `Kunde ${customerId} nicht gefunden`)
      return hit
    }
    return request<PortfolioView>(`/api/customers/${customerId}/portfolio`)
  },

  async getEvals(): Promise<EvalReport> {
    return useFixtures() ? fromFixture<EvalReport>('evals') : request<EvalReport>('/api/evals/latest')
  },

  explainMove(customerId: string, start: string, end: string): Promise<ToolResult<ExplainMovePayload>> {
    return useFixtures()
      ? toolFixture(toolKey.explain(customerId, start, end))
      : callTool('explain_move', { customer_id: customerId, start, end })
  },

  lookthrough(customerId: string): Promise<ToolResult<LookthroughPayload>> {
    return useFixtures()
      ? toolFixture(toolKey.lookthrough(customerId))
      : callTool('portfolio_lookthrough', { customer_id: customerId })
  },

  simulate(rate: number, years: number, mix: MixId): Promise<ToolResult<SimulatePayload>> {
    return useFixtures()
      ? toolFixture(toolKey.simulate(rate, years, mix))
      : callTool('simulate_savings_plan', {
          monthly_eur: rate,
          years,
          product_ids: null,
          weights: MIXES[mix].weights,
          fee_per_execution: 1,
        })
  },

  costProjection(productId: string, rate: number, years = 10): Promise<ToolResult<CostProjectionPayload>> {
    return useFixtures()
      ? toolFixture(toolKey.cost(productId, rate, years))
      : callTool('cost_projection', { product_id: productId, monthly_eur: rate, years })
  },

  suitability(customerId: string, productId: string): Promise<ToolResult<SuitabilityPayload>> {
    return useFixtures()
      ? toolFixture(toolKey.suitability(customerId, productId))
      : callTool('suitability_check', { customer_id: customerId, product_id: productId })
  },

  /** Streams the events of one chat turn. Fixture mode replays the recording that matches the question. */
  async *chat(
    customerId: string,
    message: string,
    opts: { signal?: AbortSignal; speed?: number } = {},
  ): AsyncGenerator<SSEEvent> {
    if (useFixtures()) {
      yield* replay(await loadSSE(pickChatFixture(message)), opts)
      return
    }
    yield* postSSE('/api/chat', { customer_id: customerId, message }, { signal: opts.signal })
  },

  /** Link to the KID PDF, optionally at a page (the PDF viewer understands `#page=N`). */
  kidUrl(productId: string, page?: number): string {
    return `/api/kid/${productId}.pdf${page ? `#page=${page}` : ''}`
  },
}

/** `KID:P07:p2:kosten` -> { productId: 'P07', page: 2, section: 'kosten' } */
export function parseChunkId(id: string): { productId: string; page: number; section: string } | null {
  const m = /^KID:(P\d{2}):p(\d+):([a-z_]+)(?::\d+)?$/.exec(id)
  return m ? { productId: m[1], page: Number(m[2]), section: m[3] } : null
}
