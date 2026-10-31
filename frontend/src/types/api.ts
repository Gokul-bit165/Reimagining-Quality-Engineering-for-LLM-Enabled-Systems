/* ══════════════════════════════════════════════════════════════
   "Connect your RAG app" flow: projects + evaluations
   Contract: qe/ui/routes_projects.py and qe/ui/routes_eval.py
   ══════════════════════════════════════════════════════════════ */

import type { JudgeBlock, RuntimeStatus } from './campaign';

export type ProjectState = 'cloning' | 'analyzing' | 'ready' | 'failed';
export type ExecutionMode = 'endpoint' | 'docker' | 'static_only';

export interface RiskFlag {
  id: string;
  title: string;
  evidence_file: string | null;
  line: number | null;
}

/** Some detectors emit plain strings, others {name|path|file, line, text}. */
export type DetectedItem = string | { [key: string]: unknown };

export interface ProjectAnalysis {
  framework: string | null;
  language: string | null;
  entrypoints: DetectedItem[];
  retriever: DetectedItem | null;
  vector_store: DetectedItem | null;
  llm_providers: DetectedItem[];
  prompts: DetectedItem[];
  doc_sources: DetectedItem[];
  env_vars: DetectedItem[];
  chunking: DetectedItem | null;
  risk_flags: RiskFlag[];
  execution_mode: ExecutionMode;
  /** Plain-language summary written by the analyser. */
  summary?: string | null;
  next_steps?: string[];
  notes?: string[];
  executed?: boolean;
  /** Why execution_mode is what it is (the precise reason when static_only). */
  mode_reason?: string;
  /** Docker mode: dockerfile | python-asgi | python-flask | python-function | node. */
  run_kind?: string;
}

export interface ProjectDocument { name: string; text: string }
/** answerable: true = the documents answer it, false = they do not (a refusal is expected), absent = unknown. */
export interface ProjectQaPair { question: string; reference_answer?: string; answerable?: boolean | null }

export type HttpMethod = 'POST' | 'GET';
export type ResponseFormat = 'auto' | 'json' | 'sse' | 'text';

/** How to call the user's endpoint. Header values are ${SECRET_NAME} references, never secret values. */
export interface TargetConfig {
  request_template: Record<string, unknown> | unknown[] | null;
  method: HttpMethod;
  answer_path: string | null;
  context_paths: string[];
  headers: Record<string, string>;
  response_format: ResponseFormat;
}

export type ContextsKind = 'text' | 'ids' | 'none';

export interface TargetTestResult {
  ok: boolean;
  answer: string;
  contexts: string[];
  contexts_kind: ContextsKind;
  latency_s: number;
  error: string | null;
  raw_preview: string | null;
  warnings: string[];
}

export interface PolicyMetricDoc { name: string; description: string }

/** GET /api/policy/template. Every number is null on purpose: the risk appetite is the user's call. */
export interface PolicyTemplate {
  policy: Record<string, unknown>;
  fields: Record<string, string>;
  metrics: PolicyMetricDoc[];
  notes: string[];
}

/** The policy object POSTed as `policy` to /api/evaluations. */
export interface PolicyPayload {
  policy_id: string;
  version: string;
  loss_matrix: Record<string, never>;
  required_evidence: string[];
  risk_appetite: Record<string, number>;
  conditional_rules: never[];
  min_improvement: Record<string, never>;
  /** Optional: minimum measured judge agreement (lower CI bound) before the judge may gate. */
  judge_min_agreement?: number;
}

export interface LlmStatus { configured: boolean; missing: string[] }

export interface ProjectInputs {
  documents?: ProjectDocument[];
  qa_pairs?: ProjectQaPair[];
  endpoint_url?: string | null;
  notes?: string | null;
  risk_focus?: string[];
  /** Docker mode: the only hosts the sandboxed app may reach (exact names or *.suffix). */
  egress_allowlist?: string[];
  /** Docker mode: HTTP path the questions are POSTed to (override). */
  app_path?: string | null;
  /** Docker mode: container port the app listens on (override). */
  app_port?: number | null;
}

export interface Project {
  id: string;
  repo_url: string;
  branch: string | null;
  subdir?: string | null;
  endpoint_url?: string | null;
  authorized?: boolean;
  state: ProjectState;
  error: string | null;
  created_at: string | number;
  analysis: ProjectAnalysis | null;
  inputs: ProjectInputs;
  target_config?: TargetConfig | null;
  /** Docker run lifecycle; null when nothing was built. Logs are scrubbed and truncated by the backend. */
  runtime?: RuntimeStatus | null;
  /** Names (never values) of secrets held in the write-only vault. */
  secrets_set?: string[];
}

export interface CreateProjectBody {
  repo_url: string;
  branch?: string;
  subdir?: string;
  endpoint_url?: string;
  /** Attestation: the user owns / may test this app. Required by the backend. */
  authorized: boolean;
}

export interface SuggestedInputs {
  documents?: ProjectDocument[];
  qa_pairs?: ProjectQaPair[];
  risk_focus?: string[];
  notes?: string | null;
  endpoint_url?: string | null;
  [key: string]: unknown;
}

export interface SignoffBody { reviewer: string; decision: 'approve' | 'reject'; rationale: string }

export type WatchStatus = 'failing' | 'uncertain' | 'within' | 'unmeasured';

export interface WatchEntry {
  metric: string;
  required: boolean;
  status: WatchStatus;
  failure_rate: number | null;
  failure_rate_ci: [number | null, number | null];
  appetite: number;
  n_roots: number;
}

export interface MonitoringPlan {
  evaluation_id?: string;
  project_id?: string;
  derived_from?: { failed_items?: number; failure_classes?: Record<string, number>; unchecked_items?: number };
  rerun?: { failed_items?: string[]; security_probes?: string[]; regression_suite?: string };
  watch?: WatchEntry[];
  attention?: string[];
  unmeasured_required?: string[];
  cadence_days?: number | null;
  cadence_note?: string;
  drift_triggers?: string[];
  thresholds?: Record<string, { max_failure_rate: number | null; policy?: string; example?: boolean }>;
  alert_rule?: string;
  status?: string;
  markdown?: string;
}

export type EvaluationState = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';
export type Verdict = 'RELEASE' | 'CONDITIONAL' | 'REJECT' | 'INSUFFICIENT_EVIDENCE';

export interface EvalMetric {
  value: number | null;
  ci_low: number | null;
  ci_high: number | null;
  n: number;
  /** Distinct root questions behind `n` (paraphrase/variant items share their parent's root). */
  n_roots?: number;
  n_items?: number;
  note?: string | null;
  metric?: string;
}

export interface EvalItem {
  id: string;
  question: string;
  reference_answer: string | null;
  answer: string | null;
  contexts: string[];
  /** Mixed: numbers, booleans (checks passed), null (not measured) and per-repeat arrays (null = not checked). */
  scores: Record<string, number | boolean | null | (number | boolean | null)[]>;
  /** null = NOT CHECKED (no reference answer and answerable undeclared). Never a failure, never a pass. */
  passed: boolean | null;
  answerable?: boolean | null;
  lineage?: { parent?: string | null; advisory?: boolean; confirmed?: boolean; [key: string]: unknown } | null;
  failure_reason: string | null;
  failure_class?: string | null;
  detail?: Record<string, unknown> | null;
  source: 'user' | 'generated' | 'security' | 'regression';
}

export interface TaxonomyClass {
  name: string;
  count: number;
  examples: { item_id: string; question: string; reason: string }[];
}

/** Row of GET /api/evaluations (summary, no items or metrics). */
export interface EvaluationSummary {
  id: string;
  project_id: string;
  state: EvaluationState;
  progress: { done: number; total: number };
  verdict: Verdict | null;
  status: string | null;
  created: number;
}

export interface Evaluation {
  id: string;
  project_id: string;
  state: EvaluationState;
  progress: { done: number; total: number };
  error: string | null;
  metrics: Record<string, EvalMetric>;
  decision: {
    verdict: Verdict;
    reasons: string[];
    status?: string | null;
    explanation?: string | null;
    policy?: string | null;
    policy_is_example?: boolean;
    signoff?: { reviewer: string; decision: string; rationale?: string; signed_digest?: string } | null;
  } | null;
  /** Six headline dimensions, each with a confidence interval. */
  scorecard?: Record<string, EvalMetric>;
  failure_taxonomy?: Record<string, TaxonomyClass>;
  items: EvalItem[];
  /** Semantic-judge block; null/absent when no judge ran. */
  judge?: JudgeBlock | null;
  /** "N distinct questions, M test items". */
  sample?: { n_roots: number; n_items: number };
  unchecked?: { count: number; ids: string[] };
  advisory?: { unconfirmed: number; ids: string[] };
  params?: { max_questions: number; repeats: number; include_security: boolean; seed?: number; risk_focus?: string[] };
  created_at?: string;
}

export interface EvaluationOptions {
  project_id: string;
  max_questions?: number;
  repeats?: number;
  include_security?: boolean;
  generate_questions?: boolean;
  risk_focus?: string[];
  /** Exactly one of `policy` / `use_example_policy: true` is required by the backend. */
  policy?: PolicyPayload;
  use_example_policy?: boolean;
}
