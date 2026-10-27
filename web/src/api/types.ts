/* ─── API types mirroring docs/API.md ─── */

// GET /api/health
export interface HealthResponse {
  status: string;
  live_available: boolean;
  model: string;
  mode_default: string;
}

// GET /api/config
export interface ToolParam {
  name: string;
  type: string;
  required: boolean;
}

export interface ToolDef {
  name: string;
  description: string;
  params: ToolParam[];
}

export interface Weights {
  w1: number;
  w2: number;
  w3: number;
}

export interface ConfigResponse {
  weights: Weights;
  tau1: number;
  tau2: number;
  tools: ToolDef[];
  tool_policies: Record<string, ToolPolicy>;
}

export interface ToolPolicy {
  severity_prior: number;
  minimum_decision: Tier | null;
}

// POST /api/runs
export interface RunRequest {
  task: string;
  mode: 'live' | 'offline';
}

export interface RunResponse {
  run_id: string;
}

// POST /api/chat and POST /api/chat/approve
export interface ChatRequest {
  session_id: string;
  message: string;
}

export interface ChatToolEvent {
  tool: string;
  args: Record<string, unknown>;
  decision: Tier | string | null;
  risk: number | null;
  status: string;
  run_id?: string;
  score_breakdown?: {
    V: number | null;
    C: number | null;
    F: number | null;
    severity_prior: number | null;
    historical_failure_rate: number | null;
    weights: { w1: number; w2: number; w3: number };
    R: number | null;
    score_based_decision: Tier | string | null;
    floor: Tier | string | null;
    floor_applied: boolean;
    decision: Tier | string | null;
    degraded: boolean;
  };
}

export interface ChatResponse {
  reply: string;
  tool_events: ChatToolEvent[];
  error?: string;
}

export interface ChatApproveRequest {
  run_id: string;
  approved: boolean;
}

// SSE event payloads
export interface RunStartedEvent {
  run_id: string;
  task: string;
  mode: string;
  llm_mode: string;
}

export interface ScoredEvent {
  tool_name: string;
  args: Record<string, unknown>;
  score: number;
  tier: Tier;
  contributing_signals: ContributingSignals;
}

export interface ContributingSignals {
  reversibility: number;
  confidence: number;
  failure_rate: number;
  confidence_source?: string;
  historical_failure_rate?: number;
  severity_prior?: number;
  score_based_decision?: Tier | string;
  floor?: Tier | string | null;
  floor_applied?: boolean;
  weights?: Weights;
  R?: number;
  final_decision?: Tier | string;
}

export interface ReviewRequiredEvent {
  tool_name: string;
  args: Record<string, unknown>;
  score: number;
  signals: ContributingSignals;
  tau2: number;
  timeout_seconds: number;
}

export interface ReviewResolvedEvent {
  approved: boolean;
}

export interface ReviewTimeoutEvent {
  timeout_seconds: number;
}

export type Tier = 'AUTO_ALLOW' | 'LOG_AND_MONITOR' | 'HUMAN_REVIEW';

export interface Decision {
  score: number | null;
  tier: Tier | null;
  signals: ContributingSignals | null;
  assessed: boolean;
}

export interface RunFinishedEvent {
  run_id: string;
  task_instruction: string;
  status: RunStatus;
  llm_mode: string;
  tool_name: string | null;
  args: Record<string, unknown> | null;
  result: string | null;
  error: string | null;
  extracted_confidence: number | null;
  decision: Decision;
  outcome_log: Record<string, unknown> | null;
  ignored_calls: unknown[];
}

export interface RunErrorEvent {
  error: string;
}

export type RunStatus =
  | 'RUNNING'
  | 'EXECUTED'
  | 'DENIED_BY_HUMAN_REVIEW'
  | 'REJECTED_UNSUPPORTED_TOOL'
  | 'REJECTED_INVALID_ARGS'
  | 'EXECUTION_ERROR'
  | 'LLM_ERROR'
  | 'NO_TOOL_CALL';

// POST /api/runs/{run_id}/review
export interface ReviewRequest {
  approve: boolean;
}

export interface ReviewResponse {
  status: string;
  run_id: string;
  approved: boolean;
}

// GET /api/runs
export interface RunRecord {
  run_id: string;
  created_at: string;
  task: string;
  mode: string;
  llm_mode: string;
  status: RunStatus;
  tool_name: string | null;
  args: Record<string, unknown> | null;
  result: string | null;
  error: string | null;
  extracted_confidence: number | null;
  decision: Decision;
  outcome_log: Record<string, unknown> | null;
  ignored_calls: unknown[];
}

// GET /api/stats
export interface ToolStat {
  tool_name: string;
  total_calls: number;
  failure_rate: number;
}

export interface SessionTotals {
  executed: number;
  denied: number;
  rejected: number;
  errors: number;
}

export interface StatsResponse {
  tools: ToolStat[];
  totals: SessionTotals;
  session_totals: SessionTotals;
}

// POST /api/score (what-if)
export interface ScoreRequest {
  tool_name: string;
  args?: Record<string, unknown>;
  confidence?: number | null;
  w1?: number;
  w2?: number;
  w3?: number;
  tau1?: number;
  tau2?: number;
  severity_prior?: number;
  minimum_decision?: Tier | 'NONE';
}

export interface ScoreResponse {
  score: number;
  tier: Tier;
  signals: {
    reversibility: number;
    confidence: number;
    confidence_gap: number;
    failure_rate: number;
    historical_failure_rate: number;
    severity_prior: number;
    weights: Weights;
    R: number;
    confidence_source: string;
    score_based_decision: Tier;
    floor: Tier | null;
    floor_applied: boolean;
    final_decision: Tier;
  };
  terms: {
    reversibility: number;
    confidence_gap: number;
    failure_rate: number;
  };
  clamped: boolean;
  score_based_tier: Tier;
  floor: Tier | null;
  floor_applied: boolean;
}

// POST /api/benchmark
export interface BenchmarkRequest {
  w1?: number;
  w2?: number;
  w3?: number;
  tau1?: number;
  tau2?: number;
}

export interface BenchmarkScenarioResult {
  scenario_id: string;
  task_instruction: string;
  ground_truth: 'low' | 'medium' | 'high' | string;
  assigned_tiers: Tier[];
  is_unsafe_execution: boolean;
  is_false_positive: boolean;
  baseline_latency_ms: number;
  cgtel_latency_ms: number;
}

export interface BenchmarkSummary {
  total_scenarios: number;
  low_risk_count: number;
  medium_risk_count: number;
  high_risk_count: number;
  unsafe_execution_rate: number;
  false_positive_rate: number;
  avg_baseline_latency_ms: number;
  avg_cgtel_latency_ms: number;
  avg_latency_overhead_ms: number;
}

export interface BenchmarkConfigUsed extends Weights {
  tau1: number;
  tau2: number;
}

export interface BenchmarkResponse {
  results: BenchmarkScenarioResult[];
  summary: BenchmarkSummary;
  config_used: BenchmarkConfigUsed;
}

// POST /api/reset-history
export interface ResetHistoryRequest {
  confirm: boolean;
}

export interface ResetHistoryResponse {
  cleared: boolean;
  default_failure_rate: number;
}

// Stamp variants
export type StampVariant =
  | 'AUTHORISED'
  | 'FLAGGED'
  | 'HELD FOR REVIEW'
  | 'REFUSED'
  | 'REJECTED MALFORMED'
  | 'NOT ASSESSED';
