import { z } from 'zod';

/* ── Rate (confidence interval) ───────────────────────────── */
export const RateSchema = z.object({
  k: z.number(),
  n: z.number(),
  point: z.number(),
  lower: z.number(),
  upper: z.number(),
  confidence: z.number(),
  method: z.string(),
});
export type Rate = z.infer<typeof RateSchema>;

/* ── Failure example inside a metric ──────────────────────── */
export const FailureSchema = z.object({
  case_id: z.string(),
  question: z.string().nullable(),
  expected: z.string().nullable(),
  state: z.string(),
  detail: z.string().nullable(),
  evidence_key: z.string(),
  output: z.string(),
  citations: z.array(z.string()),
});
export type Failure = z.infer<typeof FailureSchema>;

/* ── Metric ───────────────────────────────────────────────── */
export const MetricSchema = z.object({
  metric: z.string(),
  dimension: z.string(),
  failed_cases: z.number(),
  passed_cases: z.number(),
  not_evaluable_cases: z.number(),
  failure_rate: RateSchema.optional(),
  appetite: z.number().nullable(),
  status: z.enum(['within', 'above', 'straddles', 'no_appetite']).optional(),
  failures: z.array(FailureSchema),
});
export type Metric = z.infer<typeof MetricSchema>;

/* ── Report ───────────────────────────────────────────────── */
export const ReportSchema = z.object({
  id: z.string(),
  scenario: z.object({
    app: z.string(),
    variant: z.enum(['clean', 'seeded']),
    taxonomy_id: z.string(),
    text: z.string(),
    previous_failures: z.array(z.string()),
    budget: z.number(),
    mode: z.enum(['simulated', 'real']),
    tester_model: z.string().nullable(),
    target_model: z.string().nullable(),
    repeats: z.number(),
    attack_budget: z.number(),
    regression: z.string(),
  }),
  labels: z.object({
    generation: z.string(),
    target: z.string(),
    policy: z.string(),
    mode: z.enum(['simulated', 'real']),
  }),
  risks: z.array(z.object({
    risk_id: z.string(),
    taxonomy_id: z.string(),
    title: z.string(),
    component: z.string(),
    rationale: z.string(),
    source: z.string(),
    status: z.string(),
    planned_tests: z.number(),
  })),
  plan: z.object({
    allocation: z.array(z.tuple([z.string(), z.number()])),
    unplanned: z.array(z.string()),
    budget: z.number(),
  }),
  generation: z.object({
    drafted: z.number(),
    rejected_drafts: z.number(),
    redundant: z.record(z.string()),
    unplanned_risks: z.array(z.string()),
    tests: z.array(z.object({
      case_id: z.string(),
      question: z.string(),
      expected: z.string(),
      source_id: z.string(),
      risk_id: z.string(),
      family: z.string(),
    })),
  }),
  execution: z.object({
    runs: z.number(),
    repeats: z.number(),
    cases: z.number(),
    errors: z.number(),
    unrun: z.number(),
    consistency: z.object({
      cases: z.number(),
      identical_across_repeats: z.number(),
    }),
    error_kinds: z.array(z.string()).optional(),
  }),
  checks: z.object({
    ran: z.array(z.string()),
    attack_oracles: z.array(z.string()),
    not_run: z.array(z.string()),
  }),
  metrics: z.array(MetricSchema),
  attacks: z.object({
    budget: z.number(),
    verdict_attacker: z.string(),
    rows: z.array(z.object({
      pair_id: z.string(),
      surface: z.string(),
      goal: z.string(),
      baseline_breached: z.boolean(),
      static_template: z.object({
        breached: z.boolean(),
        first_success: z.number().nullable(),
        attempts: z.number(),
      }),
      adaptive_mutation: z.object({
        breached: z.boolean(),
        first_success: z.number().nullable(),
        attempts: z.number(),
      }),
    })),
    asr: z.record(z.object({
      successes: z.number(),
      n_pairs: z.number(),
      asr: z.number(),
      lower: z.number(),
      upper: z.number(),
      budget: z.number(),
    })),
  }),
  failures: z.array(z.object({
    case_id: z.string(),
    metric: z.string(),
    location: z.string(),
    rule: z.string().nullable(),
    evidence: z.array(z.string()),
    substitution: z.string(),
    source_id: z.string().nullable(),
    question: z.string().nullable(),
  })),
  failure_taxonomy: z.record(z.number()),
  regression: z.object({
    admitted: z.array(z.object({
      case_id: z.string(),
      minimized_from: z.string(),
      original_question: z.string().nullable(),
      minimized_input: z.record(z.unknown()),
      reproduced: z.tuple([z.number(), z.number()]),
      metric: z.string().nullable(),
      lineage: z.array(z.string()),
    })),
    rejected: z.array(z.object({
      case_id: z.string(),
      metric: z.string(),
      reason: z.string(),
    })),
  }),
  decision: z.object({
    decision: z.enum(['RELEASE', 'CONDITIONAL', 'REJECT', 'INSUFFICIENT_EVIDENCE']),
    policy_version: z.string(),
    evidence_ids: z.array(z.string()),
    conditions: z.array(z.string()),
    uncovered_risks: z.array(z.string()),
  }),
  policy: z.object({
    id: z.string(),
    version: z.string(),
    example_only: z.boolean(),
  }),
  access: z.object({
    visibility_levels: z.array(z.string()),
    note: z.string(),
  }),
  ledger: z.object({
    entries: z.number(),
    head: z.string(),
    verified: z.boolean(),
  }),
  human_signoff: z.array(z.object({
    approver: z.string(),
    approved: z.boolean(),
    note: z.string(),
    decision_id: z.string(),
  })),
});
export type Report = z.infer<typeof ReportSchema>;

/* ── Run summary (from /api/runs) ─────────────────────────── */
export interface RunSummary {
  id: string;
  app: string;
  variant: 'clean' | 'seeded';
  decision: string;
  entries: number;
  verified: boolean;
  example_policy: boolean;
}

/* ── Taxonomy ─────────────────────────────────────────────── */
export interface TaxonomyEntry { id: string; title: string; }
export interface Taxonomy {
  name: string;
  status: string;
  apps: string[];
  entries: TaxonomyEntry[];
}

/* ── Config ───────────────────────────────────────────────── */
export interface Config {
  real_available: boolean;
  reason?: string;
  tester_model?: string;
  target_model?: string;
  max_calls?: number;
}

/* ── Benchmark types ──────────────────────────────────────── */
export interface BenchStatus {
  id: string;
  state: 'running' | 'done' | 'error';
  done: number;
  total: number;
  note: string;
  error?: string;
  models: string[];
  started: string;
}

export interface BenchCell {
  failed: number;
  passed: number;
  not_evaluable: number;
  rate?: Rate;
  examples: {
    test_id: string;
    style: string | null;
    question: string | null;
    expected: string | null;
    output: string;
    detail: string | null;
  }[];
}

export interface BenchReport {
  benchmark: {
    models: string[];
    focus: string;
    n_tests: number;
    repeats: number;
    pace_s: number;
    suite_generator: string;
    suite: { n: number; styles: Record<string, number>; sources: string[] };
  };
  models: Record<string, {
    simulated: boolean;
    metrics: Record<string, BenchCell>;
    runs: { total: number; errors: number; error_kinds: string[] };
  }>;
  comparison: {
    metric: string;
    meaning: string;
    cells: Record<string, Rate | null>;
    separable: string[];
  }[];
  tests: {
    test_id: string;
    style: string;
    question: string;
    expected: string;
    source_id: string;
    canary: string | null;
  }[];
  ledger: { entries: number; head: string; verified: boolean };
  notes: string[];
}

export interface BenchModels {
  simulated: { id: string; description: string }[];
  real_available: boolean;
  reason?: string;
  suggested_real: string[];
}


/* ══════════════════════════════════════════════════════════════
   "Connect your RAG app" flow: projects + evaluations
   Contract: qe/ui/routes_projects.py and qe/ui/routes_eval.py
   ══════════════════════════════════════════════════════════════ */

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
}

export interface ProjectDocument { name: string; text: string }
export interface ProjectQaPair { question: string; reference_answer?: string }

export interface ProjectInputs {
  documents?: ProjectDocument[];
  qa_pairs?: ProjectQaPair[];
  endpoint_url?: string | null;
  notes?: string | null;
  risk_focus?: string[];
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

export interface MonitoringPlan {
  [key: string]: unknown;
}

export type EvaluationState = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';
export type Verdict = 'RELEASE' | 'CONDITIONAL' | 'REJECT' | 'INSUFFICIENT_EVIDENCE';

export interface EvalMetric {
  value: number | null;
  ci_low: number | null;
  ci_high: number | null;
  n: number;
  note?: string | null;
}

export interface EvalItem {
  id: string;
  question: string;
  reference_answer: string | null;
  answer: string | null;
  contexts: string[];
  /** Mixed: numbers, booleans (checks passed) and arrays (per-repeat results). */
  scores: Record<string, number | boolean | null | (number | boolean)[]>;
  passed: boolean | null;
  failure_reason: string | null;
  failure_class?: string | null;
  detail?: Record<string, unknown> | null;
  source: 'user' | 'generated' | 'security';
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
  synthetic: boolean;
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
  synthetic: boolean;
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
  created_at?: string;
}

export interface EvaluationOptions {
  project_id: string;
  max_questions?: number;
  repeats?: number;
  include_security?: boolean;
  generate_questions?: boolean;
  risk_focus?: string[];
  /** Permit the offline synthetic question generator; results are then labelled SYNTHETIC. */
  allow_synthetic?: boolean;
  policy?: Record<string, unknown>;
}
