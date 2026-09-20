/**
 * Mirror of backend/app/schemas (pydantic v2). Source of truth: contracts/*.schema.json.
 * Contract changes happen together: schemas, this file and frontend/fixtures/sse, then `make contracts`.
 * `contracts.test.ts` checks the name lists below against the exported schemas.
 */

// ── shared enums ────────────────────────────────────────────────────────────

export type AssetClass = 'equity_etf' | 'equity_fund' | 'bond_fund' | 'mixed_fund' | 'money_market'
export type Region = 'Europa' | 'USA' | 'Welt' | 'Schwellenländer' | 'Österreich'
export type Exclusion = 'Waffen' | 'Fossile' | 'Tabak' | 'Glücksspiel'
export type Distribution = 'thesaurierend' | 'ausschüttend'
export type Sfdr = 6 | 8 | 9
export type Verdict = 'pass' | 'warn' | 'fail'
export type LLMMode = 'live' | 'record' | 'replay'

export type Intent =
  | 'discover'
  | 'product_question'
  | 'portfolio_insight'
  | 'simulate'
  | 'learn'
  | 'advice_request'
  | 'out_of_scope'

export type ToolName =
  | 'screen_products'
  | 'search_kid'
  | 'portfolio_lookthrough'
  | 'explain_move'
  | 'simulate_savings_plan'
  | 'cost_projection'
  | 'suitability_check'

// ── products and portfolio ──────────────────────────────────────────────────

export interface Company {
  id: string
  name: string
  sector: string
  country: string
  market_cap_eur_m: number
  exclusion_flags: Exclusion[]
}

export interface Holding {
  id: string
  name: string
  sector: string
  country: string
  weight: number
}

export interface Product {
  id: string
  isin: string
  name: string
  issuer: string
  asset_class: AssetClass
  region: Region
  sfdr: Sfdr
  exclusions: Exclusion[]
  /** Fraction, 0.0015 = 0.15 % p. a. */
  ter: number
  entry_cost: number
  distribution: Distribution
  savings_plan_min_eur: number | null
  replication: 'physisch' | 'synthetisch' | 'aktiv'
  inception: string
  fund_size_eur_m: number
  benchmark: string
  sri: number
  recommended_holding_years: number
  holdings: Holding[]
}

export interface MarketEvent {
  id: string
  date: string
  name: string
  description: string
  /** Empty = whole market */
  sectors: string[]
  shock_pct: number
  duration_days: number
}

export type Level = 'keine' | 'basis' | 'erweitert'

export interface Profile {
  risk_class: number
  horizon_years: number
  knowledge: Partial<Record<AssetClass, Level>>
  experience: Partial<Record<AssetClass, Level>>
  loss_tolerance: 'niedrig' | 'mittel' | 'hoch'
  sustainability_preference: 'keine' | 'art8' | 'art9'
  prefers_distribution: boolean
}

export interface Position {
  product_id: string
  units: number
}

export interface Transaction {
  date: string
  product_id: string
  units: number
  amount_eur: number
  kind: 'sparplan' | 'kauf' | 'verkauf'
}

export interface Customer {
  id: string
  name: string
  age: number
  city: string
  persona: string
  profile: Profile
  positions: Position[]
  cash_eur: number
  transactions: Transaction[]
}

// ── tool result shapes used by UI blocks ────────────────────────────────────

export interface ScreenItem {
  product_id: string
  name: string
  isin: string
  asset_class: AssetClass
  region: Region
  sfdr: Sfdr
  sri: number
  ter: number
  distribution: Distribution
  savings_plan_min_eur: number | null
  why_matched: string[]
}

export interface ExposureRow {
  key: string
  label: string
  weight: number
}

export interface AttributionRow {
  product_id: string
  name: string
  pnl_eur: number
  pnl_pct: number
  contribution_pct: number
}

export interface CostRow {
  label: string
  amount_eur: number
}

export interface SuitabilityReason {
  rule: 'risk' | 'knowledge' | 'experience' | 'horizon' | 'sustainability'
  status: Verdict
  text: string
  profile_field: string
}

// ── UI blocks (hydrated) ────────────────────────────────────────────────────

export interface FilterChip {
  key: string
  label: string
  active: boolean
}

export interface CitationItem {
  chunk_id: string
  product_name: string
  page: number
  section: string
  snippet: string
}

export interface TextBlock {
  type: 'text'
  markdown: string
  /** Chunk IDs cited in the text */
  citations: string[]
}
export interface ProductCardsBlock {
  type: 'product_cards'
  items: ScreenItem[]
  filters: FilterChip[]
  total_matches: number | null
}
export interface RiskMeterBlock {
  type: 'risk_meter'
  sri: number
}
export interface FanChartBlock {
  type: 'fan_chart'
  years: number[]
  p5: number[]
  p25: number[]
  p50: number[]
  p75: number[]
  p95: number[]
  contributions: number[]
}
export interface ExposureBarsBlock {
  type: 'exposure_bars'
  dimension: 'sector' | 'country' | 'company'
  rows: ExposureRow[]
}
export interface OverlapMatrixBlock {
  type: 'overlap_matrix'
  products: { product_id: string; name: string }[]
  matrix: number[][]
}
export interface AttributionBlock {
  type: 'attribution'
  rows: AttributionRow[]
  events: MarketEvent[]
  change_eur: number
  change_pct: number
}
export interface CostBreakdownBlock {
  type: 'cost_breakdown'
  rows: CostRow[]
  total: number
  total_pct_of_contributions: number | null
}
export interface SuitabilityBlock {
  type: 'suitability'
  verdict: Verdict
  reasons: SuitabilityReason[]
}
export interface HandoffBlock {
  type: 'handoff'
  reason: string
  actions: { id: string; label: string }[]
}
export interface CitationsBlock {
  type: 'citations'
  items: CitationItem[]
}

export type UIBlock =
  | TextBlock
  | ProductCardsBlock
  | RiskMeterBlock
  | FanChartBlock
  | ExposureBarsBlock
  | OverlapMatrixBlock
  | AttributionBlock
  | CostBreakdownBlock
  | SuitabilityBlock
  | HandoffBlock
  | CitationsBlock

export const UI_BLOCK_TYPES = [
  'text',
  'product_cards',
  'risk_meter',
  'fan_chart',
  'exposure_bars',
  'overlap_matrix',
  'attribution',
  'cost_breakdown',
  'suitability',
  'handoff',
  'citations',
] as const satisfies readonly UIBlock['type'][]

// ── router ──────────────────────────────────────────────────────────────────

export interface RouterFlags {
  advice_request: boolean
  injection_suspected: boolean
  pii_present: boolean
}

// ── SSE events: `{event, data}` envelopes ───────────────────────────────────

export interface RetrievalChunk {
  id: string
  product_id: string
  page: number
  section: string
  score: number
  flags: string[]
}

export interface GuardrailCheck {
  name: string
  status: 'pass' | 'flag' | 'fail'
  detail: string
}

/** Body of POST /api/chat. */
export interface ChatRequest {
  customer_id: string
  /** 1 to 2000 characters */
  message: string
}

export interface TraceEventRecord {
  seq: number
  /** Milliseconds since the request started */
  t_ms: number
  event: string
  data: Record<string, unknown>
}

/** GET /api/traces/{id}. `message` is the PII-redacted user message. */
export interface TraceRecord {
  trace_id: string
  started_at: string
  mode: LLMMode
  customer_id: string
  message: string
  intent: Intent | null
  status: 'running' | 'ok' | 'fallback' | 'error' | 'cancelled'
  total_ms: number | null
  cost_eur: number | null
  events: TraceEventRecord[]
}

export type SSEEvent =
  | { event: 'trace'; data: { trace_id: string; started_at: string; mode: LLMMode } }
  | {
      event: 'router'
      data: { intent: Intent; flags: RouterFlags; confidence: number; model: string; latency_ms: number }
    }
  | { event: 'tool_start'; data: { call_id: string; name: ToolName; args: Record<string, unknown> } }
  | {
      event: 'tool_end'
      data: {
        call_id: string
        name: ToolName
        ok: boolean
        duration_ms: number
        result_id: string | null
        summary: string
      }
    }
  | {
      event: 'retrieval'
      data: { query: string; mode: 'hybrid' | 'dense' | 'bm25' | 'hybrid_rerank'; chunks: RetrievalChunk[] }
    }
  | { event: 'text_delta'; data: { text: string } }
  | { event: 'ui'; data: { blocks: UIBlock[] } }
  | { event: 'guardrail'; data: { checks: GuardrailCheck[] } }
  | {
      event: 'usage'
      data: { model: string; input_tokens: number; output_tokens: number; cost_eur: number }
    }
  | { event: 'done'; data: { trace_id: string; total_ms: number; cost_eur: number } }
  | { event: 'error'; data: { code: string; message: string } }

export type SSEEventName = SSEEvent['event']

export const SSE_EVENT_NAMES = [
  'trace',
  'router',
  'tool_start',
  'tool_end',
  'retrieval',
  'text_delta',
  'ui',
  'guardrail',
  'usage',
  'done',
  'error',
] as const satisfies readonly SSEEventName[]

/** One line of a recorded stream in frontend/fixtures/sse/*.jsonl */
export type FixtureLine = SSEEvent & { delay_ms: number }

// ── portfolio view: GET /api/customers/{id}/portfolio ───────────────────────

export interface SeriesPoint {
  date: string
  value_eur: number
}

export interface PortfolioPosition {
  product_id: string
  name: string
  asset_class: AssetClass
  sri: number
  units: number
  value_eur: number
  weight: number
}

export interface EventMarker {
  event: MarketEvent
  change_eur: number
  /** Portfolio move over the event window, in percent */
  change_pct: number
}

export interface PortfolioView {
  customer_id: string
  as_of: string
  total_value_eur: number
  cash_eur: number
  change_3m_eur: number
  change_3m_pct: number
  /** Daily depot value, last 12 months */
  series: SeriesPoint[]
  positions: PortfolioPosition[]
  events: EventMarker[]
}

// ── tool results (POST /api/tools/{name}) ───────────────────────────────────

export interface ToolResult<P = unknown> {
  result_id: string
  name: ToolName
  ok: boolean
  payload: P
  summary: string
}

export interface ExplainMovePayload {
  customer_id: string
  start: string
  end: string
  start_value_eur: number
  end_value_eur: number
  change_eur: number
  change_pct: number
  rows: AttributionRow[]
  events: MarketEvent[]
}

export interface LookthroughPayload {
  customer_id: string
  n_products: number
  n_companies: number
  by_company: ExposureRow[]
  by_sector: ExposureRow[]
  by_country: ExposureRow[]
  overlaps: { product_a: string; product_b: string; overlap: number }[]
  hhi: number
  top10_share: number
  flags: string[]
}

export interface SimulatePayload {
  years: number[]
  p5: number[]
  p25: number[]
  p50: number[]
  p75: number[]
  p95: number[]
  contributions: number[]
  prob_below_contributions: number
  total_contributions: number
  total_costs: number
  kest_estimate: number
  n_paths: number
  seed: number
}

export interface CostProjectionPayload {
  product_id: string
  total_contributions_eur: number
  by_year: { year: number; ter_eur: number; fees_eur: number; entry_eur: number; cumulative_eur: number }[]
  rows: CostRow[]
  total_eur: number
  total_pct_of_contributions: number
}

export interface SuitabilityPayload {
  customer_id: string
  product_id: string
  verdict: Verdict
  reasons: SuitabilityReason[]
}

// ── evals: GET /api/evals/latest ────────────────────────────────────────────

export interface EvalGate {
  name: string
  metric: string
  value: number
  threshold: number
  passed: boolean
  sample: boolean
}

export interface RetrievalRow {
  mode: 'bm25' | 'dense' | 'hybrid' | 'hybrid_rerank'
  recall_at_1: number
  recall_at_5: number
  mrr_at_10: number
  ndcg_at_5: number
  p50_ms: number
  n_questions: number
}

export interface JudgeScore {
  mean: number
  ci_low: number
  ci_high: number
}

export interface EvalReport {
  generated_at: string
  mode: 'live' | 'replay' | 'fixture'
  gates: EvalGate[]
  retrieval: { sample: boolean; rows: RetrievalRow[] }
  router: {
    sample: boolean
    n_dev: number
    n_blind: number
    accuracy_dev: number
    accuracy_blind: number
    macro_f1: number
    advice_recall: number
    false_alarm_rate: number
  }
  answers: {
    sample: boolean
    n: number
    citation_validity: number
    numeric_grounding: number
    advice_language_absent: number
    faithfulness: JudgeScore
    completeness: JudgeScore
    clarity: JudgeScore
    boundary: JudgeScore
  }
  redteam: { sample: boolean; rows: { category: string; attacks: number; successes: number }[] }
  judge_calibration: { sample: boolean; n: number; kappa: number | null }
}
