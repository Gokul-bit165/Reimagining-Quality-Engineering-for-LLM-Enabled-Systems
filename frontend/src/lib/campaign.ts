import { api, apiDownload, jsonInit, type Download } from '../api';
import { parseCsv } from './parsers';
import { pct } from './explain';
import type { EvalMetric } from '../types/api';
import {
  JUDGE_LABELS, STAGE_ORDER,
  type CalibrationHistory, type CalibrationItem, type CalibrationRecord, type Campaign, type CampaignEvents, type CampaignRequest,
  type CampaignSignoffBody, type CampaignState, type CampaignSummary, type ComparisonPair, type JudgeLabel, type JudgeStatus,
  type MetaValue, type PairOutcome, type Plan, type StageStatus, type TargetKind, type TargetResult, type TargetSpec,
} from '../types/campaign';

/* ── Limits mirrored from qe/campaign/models.py (the backend stays the authority) ───────── */
export const MAX_TARGETS = 8;
export const MAX_METADATA = 20;
export const MAX_PLAN_CASES = 500;
export const MAX_CALIBRATION_ITEMS = 300;
export const MAX_CALIBRATION_TEXT = 4000;
export const MAX_EGRESS_HOSTS = 20;
const LABEL_RE = /^[A-Za-z0-9][A-Za-z0-9 _.-]{0,39}$/;
const SECRET_RE = /^[A-Z][A-Z0-9_]{0,63}$/;
const HOST_RE = /^(\*\.)?([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/;
const APP_PATH_RE = /^\/[A-Za-z0-9._~/-]*$/;

/* ── Campaign state helpers ───────────────────────────────── */
export const isCampaignActive = (state: CampaignState): boolean => state === 'queued' || state === 'running' || state === 'cancelling';

export const STAGE_LABEL: Record<string, { title: string; text: string }> = {
  risk_definition: { title: 'Risk definition', text: 'Which risks apply, from your focus, the code analysis and your documents.' },
  test_plan: { title: 'Test plan', text: 'Cases per risk, each with its oracle, plus a coverage matrix.' },
  execution: { title: 'Execution', text: 'Every case is sent to every target, repeated, within the call budget.' },
  verification: { title: 'Verification', text: 'Deterministic checks score each answer. No model decides a verdict.' },
  classification: { title: 'Classification', text: 'Failures are grouped into the failure taxonomy.' },
  scoring: { title: 'Scoring', text: 'Rates with confidence intervals, performance, and the policy decision per target.' },
  comparison: { title: 'Comparison', text: 'Paired tests between targets on the same questions.' },
  recommendation: { title: 'Recommendation', text: 'A winner only if the paired evidence supports one.' },
  review: { title: 'Human review', text: 'A named person signs off each target decision.' },
};

export const STATE_TEXT: Record<CampaignState, string> = {
  queued: 'Queued, waiting for a worker.',
  running: 'Running.',
  done: 'Finished.',
  failed: 'Failed. See the stage errors below.',
  cancelled: 'Cancelled. Work already recorded is kept and the campaign can be resumed.',
  cancelling: 'Cancelling after the current call.',
  interrupted: 'Interrupted (the server stopped). Work already recorded is kept and the campaign can be resumed.',
};

export type Tone = 'ok' | 'bad' | 'warn' | 'run' | 'idle';

export function stageTone(status: StageStatus): Tone {
  if (status === 'done') return 'ok';
  if (status === 'failed') return 'bad';
  if (status === 'running') return 'run';
  if (status === 'cancelled' || status === 'awaiting_review') return 'warn';
  return 'idle';
}

/** Badge tone attribute: idle and running badges use the neutral style. */
export const badgeTone = (tone: Tone): 'ok' | 'bad' | 'warn' | undefined => (tone === 'idle' || tone === 'run' ? undefined : tone);

export function stateTone(state: CampaignState): Tone {
  if (state === 'done') return 'ok';
  if (state === 'failed') return 'bad';
  if (state === 'running' || state === 'queued' || state === 'cancelling') return 'run';
  return 'warn';
}

/** The first stage that is not done: where the campaign is, or where it stopped. */
export function currentStage(c: Pick<Campaign, 'stages'>): string | null {
  return STAGE_ORDER.find((s) => (c.stages[s]?.status ?? 'pending') !== 'done') ?? null;
}

export function fmtDuration(started: number | null | undefined, ended: number | null | undefined, now = Date.now() / 1000): string {
  if (!started) return '';
  const secs = Math.max(0, (ended ?? now) - started);
  if (secs < 1) return '<1 s';
  if (secs < 60) return `${Math.round(secs)} s`;
  const m = Math.floor(secs / 60);
  return `${m} min ${Math.round(secs - m * 60)} s`;
}

export function fmtSeconds(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return 'not measured';
  return v < 1 ? `${Math.round(v * 1000)} ms` : `${v.toFixed(2)} s`;
}

/** "62.0% (95% CI 45.1% to 76.3%)" or an honest "not measured". */
export function fmtRate(m: Pick<EvalMetric, 'value' | 'ci_low' | 'ci_high'> | undefined | null, digits = 1): string {
  if (!m || m.value === null || m.value === undefined) return 'not measured';
  if (m.ci_low === null || m.ci_high === null || m.ci_low === undefined || m.ci_high === undefined) return pct(m.value, digits);
  return `${pct(m.value, digits)} (${pct(m.ci_low, digits)} to ${pct(m.ci_high, digits)})`;
}

/** Tokens and cost are shown only when the target reported them. */
export function fmtTokens(t: { total_tokens: number; calls_with_usage: number } | null | undefined, calls: number): string {
  if (!t) return 'not reported';
  return `${t.total_tokens.toLocaleString()} tokens in ${t.calls_with_usage} of ${calls} calls`;
}

export const fmtCost = (cost: number | null | undefined): string => (cost === null || cost === undefined ? 'not reported' : `$${cost.toFixed(4)}`);

/* ── Comparison ───────────────────────────────────────── */
export const COMPARED_METRICS = ['overall_pass_rate', 'answer_correctness', 'faithfulness', 'citation_validity', 'refusal_correctness', 'injection_resistance'];

export interface MetricRow { metric: string; cells: { label: string; metric: EvalMetric | undefined }[] }

/** One row per compared metric, one cell per target, in target order. A missing metric stays missing. */
export function buildMetricTable(results: Record<string, TargetResult>, labels: string[], metrics: string[] = COMPARED_METRICS): MetricRow[] {
  return metrics.map((metric) => ({ metric, cells: labels.map((label) => ({ label, metric: results[label]?.metrics?.[metric] })) }));
}

export const OUTCOME_TEXT: Record<PairOutcome, { label: string; tone: 'ok' | 'warn' | 'idle' | 'info' }> = {
  A_BETTER: { label: 'A is better', tone: 'ok' },
  B_BETTER: { label: 'B is better', tone: 'ok' },
  NO_SIGNIFICANT_DIFFERENCE: { label: 'No significant difference', tone: 'idle' },
  INSUFFICIENT_EVIDENCE: { label: 'Insufficient evidence', tone: 'warn' },
  NOT_MEASURABLE: { label: 'Not measurable', tone: 'idle' },
};

/** Plain-language reading of one paired comparison. Never claims equality from a non-significant result. */
export function explainPair(p: ComparisonPair): string {
  const n = `${p.n_pairs} paired question${p.n_pairs === 1 ? '' : 's'}`;
  switch (p.outcome) {
    case 'A_BETTER':
    case 'B_BETTER': {
      const win = p.outcome === 'A_BETTER' ? p.a : p.b;
      return `${win} did better on ${n}, and the gap is still significant after correcting for the number of tests run.`;
    }
    case 'NO_SIGNIFICANT_DIFFERENCE':
      return `On ${n} the data do not separate ${p.a} and ${p.b}. That is the absence of evidence, not evidence that they are equal.`;
    case 'INSUFFICIENT_EVIDENCE':
      return `Only ${n}: too few to conclude anything. Add distinct questions to separate these targets.`;
    default:
      return 'No question is measurable on both targets for this metric.';
  }
}

/** p-values are shown to 3 significant digits, with an explicit floor instead of a bare 0. */
export function fmtP(p: number | null | undefined): string {
  if (p === null || p === undefined || Number.isNaN(p)) return 'n/a';
  if (p < 0.001) return '<0.001';
  return p.toFixed(3);
}

export function fmtDiff(p: ComparisonPair): string {
  if (p.diff === undefined || p.ci_low === undefined || p.ci_high === undefined) return 'n/a';
  const pts = (v: number) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}`;
  return `${pts(p.diff)} pts (${pts(p.ci_low)} to ${pts(p.ci_high)})`;
}

/* ── Target form ──────────────────────────────────────── */
export interface MetaRow { key: string; value: string }
export interface TargetDraft {
  label: string;
  kind: TargetKind;
  endpointUrl: string;
  model: string;
  baseUrl: string;
  apiKeySecret: string;
  meta: MetaRow[];
}

export const emptyTarget = (kind: TargetKind = 'endpoint', label = ''): TargetDraft =>
  ({ label, kind, endpointUrl: '', model: '', baseUrl: '', apiKeySecret: '', meta: [] });

export interface TargetErrors { label?: string; endpointUrl?: string; model?: string; baseUrl?: string; apiKeySecret?: string; meta?: string }

function urlProblem(text: string): string | null {
  try {
    const u = new URL(text.trim());
    return u.protocol === 'http:' || u.protocol === 'https:' ? null : 'Must start with http:// or https://';
  } catch {
    return 'That does not look like a valid URL.';
  }
}

/** "true"/"false" become booleans, plain numbers become numbers, everything else stays text. */
export function parseMetaValue(text: string): MetaValue {
  const t = text.trim();
  if (t === 'true') return true;
  if (t === 'false') return false;
  if (/^-?\d+(\.\d+)?$/.test(t)) return Number(t);
  return t;
}

export function metaToRecord(rows: MetaRow[]): { record: Record<string, MetaValue>; error: string | null } {
  const record: Record<string, MetaValue> = {};
  const filled = rows.filter((r) => r.key.trim() || r.value.trim());
  if (filled.length > MAX_METADATA) return { record, error: `At most ${MAX_METADATA} metadata entries.` };
  for (const r of filled) {
    const k = r.key.trim();
    if (!k) return { record, error: 'Every metadata value needs a key.' };
    if (!r.value.trim()) return { record, error: `Metadata "${k}" has no value.` };
    if (k in record) return { record, error: `Metadata key "${k}" is used twice.` };
    record[k] = parseMetaValue(r.value);
  }
  return { record, error: null };
}

export function validateTarget(t: TargetDraft, all: TargetDraft[]): TargetErrors {
  const e: TargetErrors = {};
  const label = t.label.trim();
  if (!label) e.label = 'Give this target a label.';
  else if (!LABEL_RE.test(label)) e.label = 'Letters, digits, space, dot, dash or underscore; start with a letter or digit; 40 characters at most.';
  else if (all.filter((o) => o.label.trim().toLowerCase() === label.toLowerCase()).length > 1) e.label = 'Labels must be unique.';
  if (t.kind === 'endpoint') {
    if (t.endpointUrl.trim() && urlProblem(t.endpointUrl)) e.endpointUrl = urlProblem(t.endpointUrl)!;
  } else {
    if (!t.model.trim()) e.model = 'A model target needs a model name.';
    if (!t.baseUrl.trim()) e.baseUrl = 'A model target needs a base URL.';
    else if (urlProblem(t.baseUrl)) e.baseUrl = urlProblem(t.baseUrl)!;
  }
  if (t.apiKeySecret.trim() && !SECRET_RE.test(t.apiKeySecret.trim())) e.apiKeySecret = 'A secret name is UPPER_SNAKE_CASE, for example OPENAI_API_KEY.';
  const meta = metaToRecord(t.meta).error;
  if (meta) e.meta = meta;
  return e;
}

export const targetHasErrors = (e: TargetErrors): boolean => Object.keys(e).length > 0;

export function buildTargetSpec(t: TargetDraft): TargetSpec {
  const base: TargetSpec = { label: t.label.trim(), kind: t.kind, metadata: metaToRecord(t.meta).record };
  if (t.kind === 'endpoint') return { ...base, ...(t.endpointUrl.trim() ? { endpoint_url: t.endpointUrl.trim() } : {}) };
  return {
    ...base, model: t.model.trim(), base_url: t.baseUrl.trim(),
    ...(t.apiKeySecret.trim() ? { api_key_secret: t.apiKeySecret.trim() } : {}),
  };
}

/** Short description of how a target is reached, for lists and cards. Never includes a secret value. */
export function describeTarget(t: TargetSpec): string {
  if (t.kind === 'model') return `${t.model ?? 'model'} via ${hostOf(t.base_url)}`;
  return t.endpoint_url ? `endpoint ${hostOf(t.endpoint_url)}` : "the project's own endpoint";
}

function hostOf(url: string | null | undefined): string {
  if (!url) return 'unknown host';
  try { return new URL(url).host; } catch { return url; }
}

/* ── Whole-form validation ────────────────────────────── */
export interface CampaignFormValues {
  name: string;
  targets: TargetDraft[];
  repeats: number;
  maxCases: number;
  maxCalls: number;
  planPresent: boolean;
}

export function validateCampaignForm(f: CampaignFormValues): string[] {
  const out: string[] = [];
  if (!f.name.trim()) out.push('Give the campaign a name.');
  if (f.targets.length < 1) out.push('Add at least one target.');
  if (f.targets.length > MAX_TARGETS) out.push(`At most ${MAX_TARGETS} targets.`);
  f.targets.forEach((t, i) => { if (targetHasErrors(validateTarget(t, f.targets))) out.push(`Target ${i + 1} has problems to fix.`); });
  const needed = f.repeats * Math.max(1, f.targets.length);
  if (f.maxCalls < needed) out.push(`Max calls (${f.maxCalls}) cannot cover even one case: repeats x targets = ${needed}.`);
  return out;
}

export function buildCampaignRequest(args: {
  projectId: string; form: CampaignFormValues; riskFocus: string[];
  policy: { useExample: boolean; policy?: CampaignRequest['policy'] };
  includeSecurity: boolean; generate: boolean; plan: Record<string, unknown> | null;
}): CampaignRequest {
  const { form } = args;
  return {
    project_id: args.projectId, name: form.name.trim(), risk_focus: args.riskFocus,
    targets: form.targets.map(buildTargetSpec), repeats: form.repeats, max_cases: form.maxCases, max_calls: form.maxCalls,
    include_security: args.includeSecurity, generate_with_llm: args.generate,
    ...(args.plan ? { plan: args.plan } : {}),
    ...(args.policy.useExample ? { use_example_policy: true } : { policy: args.policy.policy }),
  };
}

/* ── Plan import ──────────────────────────────────────── */
export interface PlanParse { plan: Record<string, unknown> | null; errors: string[]; nCases: number }

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);

/** Validate a plan file the way the backend does, so the user sees the exact case that is wrong. */
export function parsePlanFile(text: string): PlanParse {
  let raw: unknown;
  try { raw = JSON.parse(text); } catch (e) {
    return { plan: null, errors: [`Not valid JSON: ${e instanceof Error ? e.message : 'parse error'}`], nCases: 0 };
  }
  if (!isObj(raw)) return { plan: null, errors: ['The plan must be a JSON object with a "cases" list (export one from a campaign).'], nCases: 0 };
  const cases = raw.cases;
  if (!Array.isArray(cases) || cases.length === 0) return { plan: null, errors: ['plan.cases must be a non-empty list.'], nCases: 0 };
  if (cases.length > MAX_PLAN_CASES) return { plan: null, errors: [`The plan has ${cases.length} cases; at most ${MAX_PLAN_CASES}.`], nCases: cases.length };
  const errors: string[] = [];
  const seen = new Set<string>();
  cases.forEach((c, n) => {
    if (!isObj(c)) { errors.push(`cases[${n}] must be an object.`); return; }
    if (typeof c.id !== 'string' || !c.id.trim()) errors.push(`cases[${n}] needs a text "id".`);
    else if (seen.has(c.id)) errors.push(`Duplicate case id "${c.id}" (cases[${n}]).`);
    else seen.add(c.id);
    if (typeof c.question !== 'string' || !c.question.trim()) errors.push(`cases[${n}] has an empty "question".`);
    if (c.source === 'security') {
      const probe = c.probe;
      if (!isObj(probe) || typeof probe.kind !== 'string' || typeof probe.oracle !== 'string' || !isObj(probe.params)) {
        errors.push(`cases[${n}] (${String(c.id)}): a security case needs a probe {kind, oracle, params}.`);
      }
    }
  });
  return errors.length ? { plan: null, errors: errors.slice(0, 8), nCases: cases.length } : { plan: raw, errors: [], nCases: cases.length };
}

/** The plan exactly as shown, as a downloadable JSON string. */
export const planToJson = (plan: Plan): string => JSON.stringify(plan, null, 2);

export function groupCasesByScenario(cases: Plan['cases']): { scenario: string; cases: Plan['cases'] }[] {
  const map = new Map<string, Plan['cases']>();
  for (const c of cases) map.set(c.scenario, [...(map.get(c.scenario) ?? []), c]);
  return [...map.entries()].map(([scenario, cs]) => ({ scenario, cases: cs }));
}

export const COVERAGE_TEXT: Record<string, { label: string; text: string }> = {
  COVERED: { label: 'Covered', text: 'At least one test case targets this risk.' },
  GAP: { label: 'Gap', text: 'No test case could be built for this risk. The reason is shown. Nothing is claimed about it.' },
  CHECK_ONLY: { label: 'Check only', text: 'No dedicated cases; it is checked on every relevant answer instead.' },
};

/* ── Egress and execution ─────────────────────────────── */
export function parseEgressHosts(text: string): string[] {
  return text.split(/[\s,]+/).map((h) => h.trim().toLowerCase()).filter(Boolean);
}

export function validateEgressHosts(hosts: string[]): string[] {
  const errors: string[] = [];
  if (hosts.length > MAX_EGRESS_HOSTS) errors.push(`At most ${MAX_EGRESS_HOSTS} hosts.`);
  for (const h of hosts) {
    if (!HOST_RE.test(h) || h.length > 253) errors.push(`"${h.slice(0, 60)}" is not valid: use a DNS name such as api.openai.com or *.example.com (no scheme, port, path or IP).`);
  }
  return errors;
}

export function validateAppPath(path: string): string | null {
  const p = path.trim();
  if (!p) return null;
  if (p.length > 200 || !APP_PATH_RE.test(p)) return 'Start with "/" and use letters, digits and . _ ~ / - only (200 characters at most).';
  return null;
}

export function validateAppPort(text: string): string | null {
  const t = text.trim();
  if (!t) return null;
  if (!/^\d+$/.test(t) || Number(t) < 1 || Number(t) > 65535) return 'A port is a whole number from 1 to 65535.';
  return null;
}

export const RUNTIME_ACTIVE = ['building', 'starting'];

export const RUNTIME_TEXT: Record<string, { label: string; tone: 'ok' | 'bad' | 'warn' | 'info' }> = {
  idle: { label: 'Not started', tone: 'info' },
  building: { label: 'Building the container image', tone: 'warn' },
  starting: { label: 'Starting the app', tone: 'warn' },
  ready: { label: 'Running and reachable', tone: 'ok' },
  failed: { label: 'Failed', tone: 'bad' },
  stopped: { label: 'Stopped', tone: 'info' },
};

/** Keep the tail of a long log: the end is where the failure is. */
export function tailLog(log: string, maxLines = 200): { text: string; hidden: number } {
  const lines = log.split('\n');
  if (lines.length <= maxLines) return { text: log, hidden: 0 };
  return { text: lines.slice(-maxLines).join('\n'), hidden: lines.length - maxLines };
}

/* ── Judge calibration input ──────────────────────────── */
export interface CalibrationParse { items: CalibrationItem[]; errors: string[]; rows: number }

const asText = (v: unknown): string => (typeof v === 'string' ? v : v === null || v === undefined ? '' : String(v));

function toCalibrationItem(row: Record<string, unknown>, where: string): { item: CalibrationItem | null; error: string | null } {
  const label = asText(row.label).trim().toLowerCase();
  if (!(JUDGE_LABELS as readonly string[]).includes(label)) return { item: null, error: `${where}: label must be one of ${JUDGE_LABELS.join(', ')} (got "${label}").` };
  const answer = asText(row.answer);
  if (!answer.trim()) return { item: null, error: `${where}: "answer" is empty.` };
  const reference = asText(row.reference ?? row.reference_answer).trim();
  let context: string | string[] | undefined;
  const rawCtx = row.context ?? row.contexts;
  if (Array.isArray(rawCtx)) context = rawCtx.map(asText).filter((c) => c.trim());
  else if (asText(rawCtx).trim()) context = asText(rawCtx).trim();
  if (Array.isArray(context) && context.length === 0) context = undefined;
  if (!reference && !context) return { item: null, error: `${where}: needs a "reference" (correctness) or "context" (faithfulness).` };
  const over = [answer, reference, ...(Array.isArray(context) ? context : [context ?? ''])].some((t) => t.length > MAX_CALIBRATION_TEXT * (typeof context === 'string' ? 4 : 1));
  if (over) return { item: null, error: `${where}: a text field is longer than ${MAX_CALIBRATION_TEXT} characters.` };
  const kind = asText(row.kind).trim().toLowerCase();
  return {
    item: {
      question: asText(row.question), answer, label: label as JudgeLabel,
      ...(reference ? { reference } : {}), ...(context ? { context } : {}),
      ...(kind === 'correctness' || kind === 'faithfulness' ? { kind } : {}),
    },
    error: null,
  };
}

/** Labelled calibration items from JSONL (one object per line), a JSON array, or CSV with a header row. */
export function parseCalibrationText(text: string, filename = ''): CalibrationParse {
  const body = text.trim();
  if (!body) return { items: [], errors: ['The input is empty.'], rows: 0 };
  const rows: { data: Record<string, unknown>; where: string }[] = [];
  const errors: string[] = [];
  const looksCsv = /\.csv$/i.test(filename) || (!body.startsWith('{') && !body.startsWith('['));
  if (body.startsWith('[')) {
    try {
      const arr: unknown = JSON.parse(body);
      (Array.isArray(arr) ? arr : []).forEach((o, i) => { if (isObj(o)) rows.push({ data: o, where: `item ${i + 1}` }); else errors.push(`item ${i + 1}: not an object.`); });
    } catch { errors.push('Not valid JSON.'); }
  } else if (looksCsv) {
    const table = parseCsv(body);
    const header = (table[0] ?? []).map((h) => h.trim().toLowerCase());
    if (!header.includes('label') || !header.includes('answer')) errors.push('CSV needs a header row with at least the columns: answer, label (plus reference or context).');
    else table.slice(1).forEach((cells, i) => rows.push({ data: Object.fromEntries(header.map((h, j) => [h, cells[j] ?? ''])), where: `row ${i + 2}` }));
  } else {
    body.split(/\r?\n/).filter((l) => l.trim()).forEach((line, i) => {
      try {
        const o: unknown = JSON.parse(line);
        if (isObj(o)) rows.push({ data: o, where: `line ${i + 1}` }); else errors.push(`line ${i + 1}: not an object.`);
      } catch { errors.push(`line ${i + 1}: not valid JSON.`); }
    });
  }
  const items: CalibrationItem[] = [];
  for (const r of rows) {
    const res = toCalibrationItem(r.data, r.where);
    if (res.item) items.push(res.item); else if (res.error) errors.push(res.error);
  }
  if (items.length > MAX_CALIBRATION_ITEMS) errors.unshift(`${items.length} items; at most ${MAX_CALIBRATION_ITEMS} per calibration.`);
  return { items, errors: errors.slice(0, 8), rows: rows.length };
}

export const fmtInterval = (ci: readonly [number, number] | null | undefined): string => (ci ? `${pct(ci[0], 1)} to ${pct(ci[1], 1)}` : 'n/a');

/** Parse the optional policy field: empty = not set, else a number in (0, 1] or a percent in (0, 100]. */
export function parseJudgeMinAgreement(text: string): { value: number | null; error: string | null } {
  const t = text.trim().replace(/%$/, '').trim();
  if (!t) return { value: null, error: null };
  if (!/^\d+(\.\d+)?$/.test(t)) return { value: null, error: 'Enter a number from 1 to 100.' };
  const n = Number(t);
  if (n <= 0 || n > 100) return { value: null, error: 'Enter a number from 1 to 100.' };
  return { value: Number((n / 100).toFixed(6)), error: null };
}

/* ── API clients ──────────────────────────────────────── */
const cid = encodeURIComponent;

export const campaignsApi = {
  create: (body: CampaignRequest) => api<{ id: string; state: string }>('/api/campaigns', jsonInit('POST', body)),
  list: () => api<CampaignSummary[]>('/api/campaigns'),
  forProject: async (projectId: string) =>
    (await api<CampaignSummary[]>('/api/campaigns')).filter((c) => c.project_id === projectId).sort((a, b) => (b.created ?? 0) - (a.created ?? 0)),
  get: (id: string) => api<Campaign>(`/api/campaigns/${cid(id)}`),
  plan: (id: string) => api<Plan>(`/api/campaigns/${cid(id)}/plan`),
  cancel: (id: string) => api<unknown>(`/api/campaigns/${cid(id)}/cancel`, { method: 'POST' }),
  resume: (id: string) => api<unknown>(`/api/campaigns/${cid(id)}/resume`, { method: 'POST' }),
  signoff: (id: string, body: CampaignSignoffBody) => api<unknown>(`/api/campaigns/${cid(id)}/signoff`, jsonInit('POST', body)),
  confirmItem: (id: string, itemId: string, reviewer: string) =>
    api<unknown>(`/api/campaigns/${cid(id)}/items/${cid(itemId)}/confirm`, jsonInit('POST', { reviewer })),
  events: (id: string, includeRuns = false) => api<CampaignEvents>(`/api/campaigns/${cid(id)}/events?include_runs=${includeRuns}`),
};

export const judgeApi = {
  status: async (): Promise<JudgeStatus> => {
    const s = await api<JudgeStatus>('/api/judge/status');
    return { ...s, missing: Array.isArray(s.missing) ? s.missing : [], notes: Array.isArray(s.notes) ? s.notes : [], independence_reason: s.independence_reason ?? '', gating: s.gating ?? '' };
  },
  history: () => api<CalibrationHistory>('/api/judge/calibration'),
  calibrate: (items: CalibrationItem[], confidence = 0.95) =>
    api<CalibrationRecord>('/api/judge/calibrate', jsonInit('POST', { items, confidence })),
};

export type ReportOwner = { kind: 'evaluation' | 'campaign'; id: string };
export type ReportFormat = 'html' | 'md' | 'json';

export function reportUrl(owner: ReportOwner, format: ReportFormat): string {
  const base = owner.kind === 'evaluation' ? '/api/evaluations' : '/api/campaigns';
  return `${base}/${cid(owner.id)}/qa-report?format=${format}`;
}

export function bundleUrl(owner: ReportOwner): string {
  return `${owner.kind === 'evaluation' ? '/api/evaluations' : '/api/campaigns'}/${cid(owner.id)}/evidence-bundle`;
}

export const reportApi = {
  report: (owner: ReportOwner, format: ReportFormat): Promise<Download> =>
    apiDownload(reportUrl(owner, format), `qa-report-${owner.id}.${format}`),
  bundle: (owner: ReportOwner): Promise<Download> => apiDownload(bundleUrl(owner), `evidence-bundle-${owner.id}.zip`),
};

/** Reasons a report or bundle can be refused, in the user's words. */
export function describeReportError(status: number, detail: string, what: 'report' | 'bundle'): string {
  if (status === 409 && /secret/i.test(detail)) {
    return `The evidence bundle was withheld because a secret was found in the evidence. Nothing was exported. Remove the secret from the project inputs or target responses, then run again. Backend message: ${detail}`;
  }
  if (status === 409) return `The ${what} cannot be built yet: ${detail}`;
  if (status === 413) return `The ${what} is too large to export (${detail}). Reduce max cases or repeats and run again.`;
  if (status === 404) return `That ${what} was not found. It may have been deleted.`;
  return detail;
}

export const ADVISORY_NOTE = 'Written by a model. Excluded from decisions until a human confirms it.';
