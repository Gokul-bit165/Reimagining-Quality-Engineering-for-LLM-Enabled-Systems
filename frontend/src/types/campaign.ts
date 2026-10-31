/* ══════════════════════════════════════════════════════════════
   Campaigns, reports, judge, runtime.
   Contract: qe/ui/routes_campaign.py, qe/campaign/models.py, qe/campaign/analysis.py,
   qe/ui/routes_judge.py, qe/ui/routes_report.py, qe/ingest/models.py (RuntimeStatus).
   ══════════════════════════════════════════════════════════════ */
import type { EvalMetric, Evaluation, PolicyPayload } from './api';

export const STAGE_ORDER = [
  'risk_definition', 'test_plan', 'execution', 'verification', 'classification',
  'scoring', 'comparison', 'recommendation', 'review',
] as const;
export type StageName = (typeof STAGE_ORDER)[number];

export type CampaignState = 'queued' | 'running' | 'done' | 'failed' | 'cancelled' | 'cancelling' | 'interrupted';
export type StageStatus = 'pending' | 'running' | 'done' | 'failed' | 'cancelled' | 'awaiting_review';
export type TargetKind = 'endpoint' | 'model';
export type MetaValue = string | number | boolean;

export interface TargetSpec {
  label: string;
  kind: TargetKind;
  endpoint_url?: string | null;
  model?: string | null;
  base_url?: string | null;
  api_key_secret?: string | null;
  metadata: Record<string, MetaValue>;
}

export interface CampaignRequest {
  project_id: string;
  name: string;
  risk_focus: string[];
  targets: TargetSpec[];
  plan?: Record<string, unknown>;
  repeats: number;
  max_cases: number;
  max_calls: number;
  /** Exactly one of `policy` / `use_example_policy: true`. */
  policy?: PolicyPayload;
  use_example_policy?: boolean;
  include_security: boolean;
  generate_with_llm: boolean;
}

export interface StageRecord {
  status: StageStatus;
  started: number | null;
  ended: number | null;
  inputs_hash: string | null;
  error: string | null;
  detail: Record<string, unknown>;
}

export interface CampaignSummary {
  id: string;
  name: string;
  project_id: string;
  state: CampaignState;
  progress: { done: number; total: number };
  targets: string[];
  created: number;
  better_target: string | null;
}

export interface CampaignItem {
  id: string;
  question: string;
  answer: string;
  passed: boolean | null;
  failure_class: string | null;
  failure_reason: string | null;
  source: string;
  scenario: string | null;
  advisory: boolean;
  errored: boolean;
}

export interface PerRisk {
  n_roots: number;
  passed: number;
  rate: number;
  ci_low: number;
  ci_high: number;
  note: string;
}

export interface Performance {
  calls: number;
  errors: number;
  error_rate_calls: number | null;
  latency_p50_s: number | null;
  latency_p95_s: number | null;
  latency_p99_s: number | null;
  response_chars_mean: number | null;
  response_chars_max: number | null;
  tokens: { prompt_tokens: number; completion_tokens: number; total_tokens: number; calls_with_usage: number } | null;
  cost: number | null;
  cost_note?: string;
}

export type CampaignDecision = NonNullable<Evaluation['decision']> & { decision_id?: string };

export interface TargetResult {
  label: string;
  kind: TargetKind;
  metadata: Record<string, MetaValue>;
  failure_taxonomy?: Evaluation['failure_taxonomy'];
  per_risk?: Record<string, PerRisk>;
  items?: CampaignItem[];
  metrics?: Record<string, EvalMetric>;
  scorecard?: Record<string, EvalMetric>;
  decision?: CampaignDecision;
  advisory?: { unconfirmed: number; ids: string[] };
  unchecked?: { count: number; ids: string[] };
  sample?: { n_items: number; n_roots: number };
  performance?: Performance;
}

export type PairOutcome = 'A_BETTER' | 'B_BETTER' | 'NO_SIGNIFICANT_DIFFERENCE' | 'INSUFFICIENT_EVIDENCE' | 'NOT_MEASURABLE';

export interface ComparisonPair {
  metric: string;
  a: string;
  b: string;
  n_pairs: number;
  outcome: PairOutcome;
  winner: string | null;
  a_rate?: number;
  b_rate?: number;
  diff?: number;
  ci_low?: number;
  ci_high?: number;
  p_value: number | null;
  p_adjusted?: number;
  alpha?: number;
  discordant?: number;
  ci_method?: string;
  test?: string;
  note?: string;
}

export interface Comparison {
  alpha: number;
  family_size: number;
  multiplicity: string;
  note?: string;
  pairs: ComparisonPair[];
}

export interface Recommendation {
  better_target: string | null;
  decisions: Record<string, string>;
  caveats: string[];
  summary: string;
}

export interface RiskEntry {
  id: string;
  scenario: string;
  label: string;
  sources: string[];
  taxonomy: { taxonomy: string; id: string; title: string }[];
  rationale: string;
}

export interface Campaign {
  id: string;
  name: string;
  project_id: string;
  state: CampaignState;
  created: number;
  error: string | null;
  incomplete: string | null;
  params: {
    risk_focus: string[]; repeats: number; max_cases: number; max_calls: number; timeout_s: number;
    include_security: boolean; generate_with_llm: boolean; seed: number; alpha: number;
    use_example_policy: boolean; policy: PolicyPayload | null; plan_imported: boolean;
  };
  targets: TargetSpec[];
  stages: Record<string, StageRecord>;
  progress: { done: number; total: number };
  risks: RiskEntry[];
  unmapped: { label: string; source: string }[];
  results: Record<string, TargetResult>;
  comparisons: Comparison | null;
  recommendation: Recommendation | null;
  decisions: Record<string, CampaignDecision>;
  notes: string[];
  resumable: boolean;
}

export type CoverageStatus = 'COVERED' | 'GAP' | 'CHECK_ONLY';

export interface CoverageRow {
  risk_id: string | null;
  scenario: string | null;
  label?: string;
  taxonomy_ids: string[];
  n_tests: number;
  operators: Record<string, number>;
  oracle_types: string[];
  status: CoverageStatus;
  gap_reason: string;
}

export interface PlanCase {
  id: string;
  question: string;
  reference_answer: string | null;
  source: string;
  answerable: boolean | null;
  scenario: string;
  risk_id: string;
  oracles: string[];
  expected_evidence: string;
  lineage: { advisory?: boolean; operator?: string; [k: string]: unknown } | null;
  probe: Record<string, unknown> | null;
}

export interface Plan {
  plan_version: number | string;
  plan_id: string;
  source: string;
  seed: number;
  repeats: number;
  doc_names: string[];
  require_citations: boolean;
  include_security: boolean;
  authoring: { mode: string; llm_items: number; statement: string };
  risks: RiskEntry[];
  unmapped: { label: string; source: string }[];
  cases: PlanCase[];
  coverage: { matrix: CoverageRow[]; gaps: { risk_id: string; reason: string }[]; taxonomy?: unknown };
  notes: string[];
}

export interface LedgerEntry {
  seq: number;
  hash: string;
  key: string;
  type: string;
  producer: string;
  producer_kind: string;
  action: string | null;
  at: number | string | null;
  payload: Record<string, unknown>;
}

export interface CampaignEvents {
  campaign_id: string;
  ledger_ok: boolean;
  ledger_entries: number;
  recorded_target_calls: number;
  total: number;
  entries: LedgerEntry[];
}

export interface CampaignSignoffBody {
  reviewer: string;
  decision: 'approve' | 'reject';
  rationale: string;
  target_label: string;
}

/* ── Judge ───────────────────────────────────────────── */
export const JUDGE_LABELS = ['correct', 'incorrect', 'partial', 'refusal', 'unanswerable'] as const;
export type JudgeLabel = (typeof JUDGE_LABELS)[number];

export interface CalibrationStatus {
  n: number;
  agreement: number | null;
  ci: [number, number] | null;
  kappa: number | null;
  false_pass_rate: number | null;
  false_pass_ci: [number, number] | null;
  prompt_hash: Record<string, string>;
  id: string;
  stale: boolean;
  created_at: string;
}

export interface JudgeStatus {
  configured: boolean;
  generator_family: string | null;
  judge_family: string | null;
  independent: boolean;
  independence_reason: string;
  judge_model: string | null;
  second_judge: boolean;
  calibration: CalibrationStatus | null;
  gating: string;
  missing: string[];
  notes: string[];
}

export interface CalibrationItem {
  question: string;
  reference?: string;
  context?: string | string[];
  answer: string;
  label: JudgeLabel;
  kind?: 'correctness' | 'faithfulness';
}

export interface CalibrationMember {
  model: string;
  family: string | null;
  n_decided: number;
  n_abstain: number;
  agreement: number | null;
  agreement_ci: [number, number] | null;
  kappa: number | null;
  false_pass_rate: number | null;
  false_pass_ci: [number, number] | null;
}

export interface CalibrationRecord {
  id: string;
  created_at: string;
  judge_key: string;
  models: string[];
  n: number;
  confidence: number;
  members: CalibrationMember[];
  agreement: number | null;
  agreement_ci: [number, number] | null;
  kappa: number | null;
  false_pass_rate: number | null;
  false_pass_ci: [number, number] | null;
  panel: { kappa: number | null; error_correlation: number; both_wrong: number; n_eff: number; correlated_errors: boolean } | null;
  budget_exhausted: boolean;
  usage?: { calls_used: number | null; max_calls: number | null; budget_exhausted: boolean };
}

export interface CalibrationHistory {
  latest: CalibrationRecord | null;
  records: { id: string; created_at: string; n: number; agreement: number | null; judge_key: string }[];
}

/** The `judge` block of an evaluation (qe.realeval.calibration.judge_report). */
export interface JudgeBlock {
  enabled: boolean;
  gating: boolean;
  gate: { enabled: boolean; reason: string; min_agreement?: number | null; calibration_id?: string | null; agreement_lower?: number };
  models: string[];
  panel: { n_pairs: number; agreement: number | null; kappa: number | null; disagreements: number; same_family: boolean } | null;
  conflicts: string[];
  usage?: { calls_used: number | null; max_calls: number | null; budget_exhausted: boolean };
  corrected?: Record<string, {
    corrected?: null; reason?: string; n_judged: number;
    observed_defect_rate?: number; corrected_defect_rate?: number; ci_low?: number; ci_high?: number; method?: string;
  }>;
}

export interface ClaimDetail {
  claim: string;
  status: string;
  lexical_ok: boolean;
  gated_ok: boolean | null;
  quote: string | null;
  judged: boolean;
  verifiable: boolean;
  judge_disagrees: boolean;
}

/* ── Runtime ─────────────────────────────────────────── */
export type RuntimeState = 'idle' | 'building' | 'starting' | 'ready' | 'failed' | 'stopped';

export interface RuntimeStatus {
  state: RuntimeState;
  detail: string;
  kind: string;
  egress: string;
  build_log: string;
  run_log: string;
  egress_log: string[];
  updated_at: number;
}
