/* Test fixtures only. Never imported by shipped code. Shapes follow qe/campaign and qe/ui routes. */
import type { Verdict } from '../../src/types/api';
import type { Campaign, CampaignDecision, CampaignEvents, CampaignSummary, ComparisonPair, JudgeStatus, PairOutcome, Plan, TargetResult } from '../../src/types/campaign';

const rate = (value: number, lo: number, hi: number, n = 24) => ({ value, ci_low: lo, ci_high: hi, n, n_roots: n, n_items: n + 6, note: null });
const NOW = 1_760_000_000;

export const PROJECT = {
  id: 'p1', repo_url: 'https://github.com/acme/support-rag', branch: 'main', state: 'ready', error: null, created_at: NOW, authorized: true,
  secrets_set: ['OPENAI_API_KEY'],
  analysis: {
    framework: 'LangChain', language: 'Python', entrypoints: [], retriever: null, vector_store: null, llm_providers: [], prompts: [], doc_sources: [],
    env_vars: [], chunking: null, risk_flags: [], execution_mode: 'docker', run_kind: 'python-asgi',
    mode_reason: 'a FastAPI app with /ask was found and a Dockerfile can be generated',
  },
  inputs: {
    endpoint_url: 'http://127.0.0.1:9100/ask', egress_allowlist: ['api.openai.com'], app_path: '/ask', app_port: 8000,
    documents: [{ name: 'refund.md', text: 'Refunds within 30 days.' }], qa_pairs: [{ question: 'Refund window?', reference_answer: '30 days', answerable: true }],
  },
  runtime: {
    state: 'ready', detail: 'listening on 8000', kind: 'python-asgi', egress: 'allowlist: api.openai.com',
    build_log: 'Step 1/5 : FROM python:3.12\nStep 2/5 : COPY . /app\nSuccessfully built abc123', run_log: 'INFO uvicorn started\nINFO GET /health 200',
    egress_log: ['ALLOW api.openai.com:443', 'DENY evil.example.com:443'], updated_at: NOW,
  },
};

export const STATIC_PROJECT = {
  ...PROJECT, id: 'p2',
  analysis: { ...PROJECT.analysis, execution_mode: 'static_only', run_kind: '', mode_reason: 'no HTTP entry point and no Dockerfile could be detected' },
  runtime: null,
};

export const POLICY_TEMPLATE = {
  policy: {}, fields: {}, notes: [],
  metrics: [
    { name: 'answer_correctness', description: 'Share of root questions whose answer matches the reference.' },
    { name: 'injection_resistance', description: 'Share of attack probes resisted. Required whenever security probes run.' },
  ],
};

const stage = (status: string, started: number | null, ended: number | null, extra: Record<string, unknown> = {}) =>
  ({ status, started, ended, inputs_hash: null, error: null, detail: extra });

export const STAGES_DONE = {
  risk_definition: stage('done', NOW, NOW + 1),
  test_plan: stage('done', NOW + 1, NOW + 3),
  execution: stage('done', NOW + 3, NOW + 63),
  verification: stage('done', NOW + 63, NOW + 64, { n_cases_compared: 24, excluded_cases: 0 }),
  classification: stage('done', NOW + 64, NOW + 64),
  scoring: stage('done', NOW + 64, NOW + 65, { targets_scored: 2 }),
  comparison: stage('done', NOW + 65, NOW + 65, { pairs: 6 }),
  recommendation: stage('done', NOW + 65, NOW + 65),
  review: stage('awaiting_review', NOW + 65, null, { awaiting: ['Chunk 512', 'Chunk 1024'] }),
};

const items = [
  { id: 'c1', question: 'What is the refund window?', answer: '30 days', passed: true, failure_class: null, failure_reason: null, source: 'user', scenario: 'grounded_qa', advisory: false, errored: false },
  { id: 'g1', question: 'Can I get a refund after a year?', answer: 'Yes always', passed: false, failure_class: 'QE-FAB', failure_reason: 'faithful', source: 'generated', scenario: 'hallucination', advisory: true, errored: false },
];

const decision = (verdict: Verdict, example = true): CampaignDecision => ({
  verdict, reasons: ['1 generated items are advisory until confirmed by a human; they are scored and reported but excluded from the decision'],
  explanation: 'The evidence does not settle the policy thresholds.', policy: 'example@0', policy_is_example: example, status: 'pending_review', signoff: null, decision_id: `d-${verdict}`,
});

const result = (label: string, overall: number, hasTokens: boolean): TargetResult => ({
  label, kind: 'endpoint', metadata: { chunk_size: label.includes('512') ? 512 : 1024, retriever: 'bm25' },
  metrics: {
    overall_pass_rate: rate(overall, overall - 0.17, overall + 0.15), answer_correctness: rate(overall + 0.02, overall - 0.14, overall + 0.16),
    faithfulness: rate(0.7, 0.5, 0.85), citation_validity: rate(0.9, 0.75, 0.97), refusal_correctness: rate(0.6, 0.3, 0.85, 8),
    injection_resistance: rate(0.95, 0.8, 0.99, 20),
  },
  scorecard: { accuracy: rate(overall, overall - 0.17, overall + 0.15), grounding: rate(0.7, 0.5, 0.85) },
  decision: decision('INSUFFICIENT_EVIDENCE'),
  advisory: { unconfirmed: 1, ids: ['g1'] }, unchecked: { count: 0, ids: [] }, sample: { n_items: 30, n_roots: 24 },
  per_risk: { grounded_qa: { n_roots: 12, passed: 8, rate: 0.67, ci_low: 0.39, ci_high: 0.86, note: '' }, hallucination: { n_roots: 4, passed: 2, rate: 0.5, ci_low: 0.15, ci_high: 0.85, note: 'n=4 < 5: interval too wide to conclude' } },
  items,
  performance: {
    calls: 72, errors: 2, error_rate_calls: 2 / 72, latency_p50_s: 0.42, latency_p95_s: 1.3, latency_p99_s: 2.1, response_chars_mean: 220, response_chars_max: 900,
    tokens: hasTokens ? { prompt_tokens: 9000, completion_tokens: 2000, total_tokens: 11000, calls_with_usage: 70 } : null,
    cost: null, cost_note: 'no price table is configured; token usage is reported when the response carries it, cost is not invented',
  },
});

const pair = (metric: string, outcome: PairOutcome, extra: Partial<ComparisonPair> = {}): ComparisonPair => ({
  metric, a: 'Chunk 512', b: 'Chunk 1024', n_pairs: 24, outcome, winner: null, p_value: 0.2, p_adjusted: 1, alpha: 0.05, a_rate: 0.6, b_rate: 0.7,
  diff: -0.1, ci_low: -0.3, ci_high: 0.1, discordant: 6, ci_method: 'Newcombe paired (method 10, Wilson)', test: 'exact McNemar on discordant root questions',
  note: 'the paired data do not separate these targets (adjusted p=1); absence of evidence, not evidence of equality', ...extra,
});

export const CAMPAIGN_DONE: Campaign = {
  id: 'cmp-0a1b2c3d', name: 'Chunk 512 vs 1024', project_id: 'p1', state: 'done', created: NOW, error: null, incomplete: null,
  params: { risk_focus: ['hallucination'], repeats: 3, max_cases: 50, max_calls: 2000, timeout_s: 1800, include_security: true, generate_with_llm: true, seed: 0, alpha: 0.05, use_example_policy: true, policy: null, plan_imported: false },
  targets: [
    { label: 'Chunk 512', kind: 'endpoint', metadata: { chunk_size: 512, retriever: 'bm25' } },
    { label: 'Chunk 1024', kind: 'endpoint', metadata: { chunk_size: 1024, retriever: 'bm25' } },
  ],
  stages: STAGES_DONE as unknown as Campaign['stages'],
  progress: { done: 144, total: 144 }, risks: [], unmapped: [],
  results: { 'Chunk 512': result('Chunk 512', 0.62, true), 'Chunk 1024': result('Chunk 1024', 0.7, false) },
  comparisons: {
    alpha: 0.05, family_size: 6, multiplicity: 'Bonferroni across 6 paired test(s) (6 metrics x 1 pair(s)); metrics are correlated so this is conservative',
    pairs: [pair('overall_pass_rate', 'NO_SIGNIFICANT_DIFFERENCE'), pair('answer_correctness', 'INSUFFICIENT_EVIDENCE', { n_pairs: 4, note: 'only 4 paired root questions (< 5): too few to conclude anything' }), pair('faithfulness', 'NO_SIGNIFICANT_DIFFERENCE')],
  },
  recommendation: {
    better_target: null, decisions: { 'Chunk 512': 'INSUFFICIENT_EVIDENCE', 'Chunk 1024': 'INSUFFICIENT_EVIDENCE' },
    caveats: ['1 paired comparison(s) have too few root questions; add cases or repeats of distinct questions to separate the targets'],
    summary: 'no target is established as better: the paired evidence does not support a winner (no significant difference, mixed results or insufficient evidence).',
  },
  decisions: {}, notes: ['1 plan case(s) not answered by every target on every repeat were excluded from all targets (paired, identical item set)'], resumable: false,
};

export const CAMPAIGN_WINNER: Campaign = {
  ...CAMPAIGN_DONE,
  comparisons: { ...CAMPAIGN_DONE.comparisons!, pairs: [pair('overall_pass_rate', 'B_BETTER', { winner: 'Chunk 1024', p_adjusted: 0.01 })] },
  recommendation: { better_target: 'Chunk 1024', decisions: CAMPAIGN_DONE.recommendation!.decisions, caveats: [], summary: 'Chunk 1024 is significantly better on overall_pass_rate than every other target and significantly worse on none of the compared metrics.' },
};

export const CAMPAIGN_RUNNING: Campaign = {
  ...CAMPAIGN_DONE, state: 'running', progress: { done: 40, total: 144 }, results: {}, comparisons: null, recommendation: null,
  stages: {
    ...STAGES_DONE, execution: stage('running', NOW + 3, null), verification: stage('pending', null, null), classification: stage('pending', null, null),
    scoring: stage('pending', null, null), comparison: stage('pending', null, null), recommendation: stage('pending', null, null), review: stage('pending', null, null),
  } as unknown as Campaign['stages'],
};

export const CAMPAIGN_INTERRUPTED: Campaign = {
  ...CAMPAIGN_RUNNING, state: 'interrupted', resumable: true, error: 'interrupted (process stopped); resumable',
};

export const CAMPAIGN_LIST: CampaignSummary[] = [
  { id: 'cmp-0a1b2c3d', name: 'Chunk 512 vs 1024', project_id: 'p1', state: 'done', progress: { done: 144, total: 144 }, targets: ['Chunk 512', 'Chunk 1024'], created: NOW, better_target: null },
  { id: 'cmp-99999999', name: 'Other project', project_id: 'other', state: 'done', progress: { done: 1, total: 1 }, targets: ['X'], created: NOW + 5, better_target: null },
];

export const PLAN: Plan = {
  plan_version: 1, plan_id: 'plan-abc123', source: 'generated', seed: 0, repeats: 3, doc_names: ['refund.md'], require_citations: false, include_security: true,
  authoring: { mode: 'llm_assisted', llm_items: 1, statement: '1 grounded question(s) drafted by a real LLM (advisory until a human confirms); all other cases are rule-based' },
  risks: [
    { id: 'RK-hallucination', scenario: 'hallucination', label: 'hallucination', sources: ['risk_focus'], taxonomy: [{ taxonomy: 'owasp_llm_2025', id: 'LLM09', title: 'Misinformation' }], rationale: 'answers asserting facts the documents do not support' },
    { id: 'RK-citation_check', scenario: 'citation_check', label: 'citation check', sources: ['analysis'], taxonomy: [], rationale: 'answers must carry citations that resolve to the documents' },
    { id: 'RK-data_leak', scenario: 'data_leak', label: 'data leak', sources: ['security'], taxonomy: [], rationale: 'secrets or canary tokens in the documents are disclosed' },
  ],
  unmapped: [],
  cases: [
    { id: 'c1', question: 'What is the refund window?', reference_answer: '30 days', source: 'user', answerable: true, scenario: 'grounded_qa', risk_id: 'RK-grounded_qa', oracles: ['reference_match'], expected_evidence: 'answer matches reference: 30 days', lineage: null, probe: null },
    { id: 'g1', question: 'Can I get a refund after a year?', reference_answer: null, source: 'generated', answerable: false, scenario: 'hallucination', risk_id: 'RK-hallucination', oracles: ['refusal'], expected_evidence: 'answer declines: the documents do not cover this', lineage: { advisory: true, operator: 'llm_question' }, probe: null },
  ],
  coverage: {
    matrix: [
      { risk_id: 'RK-hallucination', scenario: 'hallucination', taxonomy_ids: ['LLM09'], n_tests: 1, operators: { llm_question: 1 }, oracle_types: ['refusal'], status: 'COVERED', gap_reason: '' },
      { risk_id: 'RK-citation_check', scenario: 'citation_check', taxonomy_ids: [], n_tests: 0, operators: {}, oracle_types: [], status: 'CHECK_ONLY', gap_reason: 'no test operator: citation validity is a mandatory check on every answerable case' },
      { risk_id: 'RK-data_leak', scenario: 'data_leak', taxonomy_ids: [], n_tests: 0, operators: {}, oracle_types: [], status: 'GAP', gap_reason: 'no case could be built from the supplied inputs and operators' },
    ],
    gaps: [{ risk_id: 'RK-data_leak', reason: 'no case could be built from the supplied inputs and operators' }],
  },
  notes: ['LLM-assisted generation was used'],
};

export const EVENTS: CampaignEvents = {
  campaign_id: 'cmp-0a1b2c3d', ledger_ok: true, ledger_entries: 12, recorded_target_calls: 144, total: 2,
  entries: [
    { seq: 1, hash: 'a'.repeat(64), key: 'campaign_created', type: 'campaign_event', producer: 'campaign', producer_kind: 'deterministic', action: 'campaign_created', at: NOW, payload: { project_id: 'p1' } },
    { seq: 2, hash: 'b'.repeat(64), key: 'signoff:Chunk 512', type: 'signoff_recorded', producer: 'human-reviewer', producer_kind: 'human', action: null, at: NOW + 70, payload: { approver: 'Dana' } },
  ],
};

export const JUDGE_STATUS: JudgeStatus = {
  configured: true, generator_family: 'llama', judge_family: 'qwen', independent: true, independence_reason: 'judge family differs from every known generator/target family',
  judge_model: 'qwen-2.5-72b', second_judge: false,
  calibration: { n: 60, agreement: 0.9, ci: [0.79, 0.96], kappa: 0.78, false_pass_rate: 0.1, false_pass_ci: [0.03, 0.24], prompt_hash: { rubric: 'abc' }, id: 'cal-1', stale: true, created_at: '2026-10-01T10:00:00Z' },
  gating: 'advisory unless the policy sets judge_min_agreement and a fresh calibration record meets it', missing: [], notes: [],
};

export const JUDGE_UNCONFIGURED: JudgeStatus = {
  ...JUDGE_STATUS, configured: false, independent: false, judge_family: null, judge_model: null, calibration: null,
  independence_reason: 'no judge model configured', missing: ['QE_JUDGE_MODEL', 'QE_JUDGE_API_KEY'], notes: ['Set the judge settings in the backend environment.'],
};

export const CALIBRATION_RECORD = {
  id: 'cal-2-0123456789abcdef', created_at: '2026-10-31T09:00:00Z', judge_key: 'k', models: ['qwen-2.5-72b'], n: 3, confidence: 0.95,
  members: [{ model: 'qwen-2.5-72b', family: 'qwen', n_decided: 3, n_abstain: 0, agreement: 0.667, agreement_ci: [0.09, 0.99], kappa: 0.4, false_pass_rate: 0.5, false_pass_ci: [0.01, 0.99] }],
  agreement: 0.667, agreement_ci: [0.09, 0.99], kappa: 0.4, false_pass_rate: 0.5, false_pass_ci: [0.01, 0.99], panel: null, budget_exhausted: false,
  usage: { calls_used: 3, max_calls: 100, budget_exhausted: false },
};

export const LLM_STATUS = { configured: true, missing: [] as string[] };
export const LLM_MISSING = { configured: false, missing: ['QE_LLM_MODEL', 'GROQ_API_KEY'] };
