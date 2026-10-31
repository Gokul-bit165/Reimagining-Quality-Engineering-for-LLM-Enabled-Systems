import type { PolicyMetricDoc, PolicyPayload } from '../types/api';

/** Required (with an appetite) whenever security probes run. Mirrors qe/realeval/assemble.py. */
export const SECURITY_METRIC = 'injection_resistance';

/** A metric where the measured number already is a failure rate (all others are success rates). */
export const FAILURE_RATE_METRICS = ['error_rate'];

export interface PolicyDraft {
  policyId: string;
  version: string;
  /** metric -> is it required evidence for a RELEASE decision */
  required: Record<string, boolean>;
  /** metric -> maximum acceptable failure rate, as typed (percent, 0 to 100) */
  maxPct: Record<string, string>;
  /** Optional minimum judge agreement, as typed (percent). Blank = the judge stays advisory. */
  judgeMinPct?: string;
}

/** What the user chose for a project. `unset` is the only state with no stored value. */
export type PolicyChoice =
  | { mode: 'unset' }
  | { mode: 'example' }
  | { mode: 'custom'; draft: PolicyDraft };

export const emptyDraft = (): PolicyDraft => ({ policyId: '', version: '', required: {}, maxPct: {} });

export interface PolicyErrors {
  policyId?: string;
  version?: string;
  judgeMinAgreement?: string;
  /** metric -> message */
  metrics: Record<string, string>;
  /** Problems that belong to the whole form. */
  general: string[];
}

export const hasErrors = (e: PolicyErrors): boolean =>
  Boolean(e.policyId || e.version || e.judgeMinAgreement || e.general.length || Object.keys(e.metrics).length);

/** Parse "12", "12.5" or "12%" into a number 0..100, or null when it is not one. */
export function parsePercent(text: string): number | null {
  const t = text.trim().replace(/%$/, '').trim();
  if (!/^\d+(\.\d+)?$/.test(t)) return null;
  const n = Number(t);
  return n >= 0 && n <= 100 ? n : null;
}

export function validateDraft(draft: PolicyDraft, metrics: PolicyMetricDoc[], includeSecurity: boolean): PolicyErrors {
  const errors: PolicyErrors = { metrics: {}, general: [] };
  if (!draft.policyId.trim()) errors.policyId = 'Give this policy a name.';
  if (!draft.version.trim()) errors.version = 'Give this policy a version label.';
  const required = metrics.filter((m) => draft.required[m.name]);
  if (required.length === 0) errors.general.push('Choose at least one check that must be within your limit before a release.');
  for (const m of required) {
    const text = draft.maxPct[m.name] ?? '';
    if (!text.trim()) errors.metrics[m.name] = 'Enter the highest failure rate you accept.';
    else if (parsePercent(text) === null) errors.metrics[m.name] = 'Enter a number from 0 to 100.';
  }
  const judgeText = (draft.judgeMinPct ?? '').trim();
  if (judgeText) {
    const n = parsePercent(judgeText);
    if (n === null || n <= 0) errors.judgeMinAgreement = 'Enter a number above 0 and up to 100, or leave it blank.';
  }
  if (includeSecurity && !draft.required[SECURITY_METRIC]) {
    errors.general.push('Security probes are on, so "Attack resistance" must be a required check. Require it, or turn security probes off (the result then can never be RELEASE).');
  }
  return errors;
}

/** Build the exact object the backend validates. Only call after validateDraft() came back clean. */
export function buildPolicy(draft: PolicyDraft, metrics: PolicyMetricDoc[]): PolicyPayload {
  const required = metrics.filter((m) => draft.required[m.name]).map((m) => m.name);
  const appetite: Record<string, number> = {};
  for (const name of required) {
    const pct = parsePercent(draft.maxPct[name] ?? '');
    if (pct !== null) appetite[name] = Number((pct / 100).toFixed(6));
  }
  const judgeMin = (draft.judgeMinPct ?? '').trim() ? parsePercent(draft.judgeMinPct ?? '') : null;
  return {
    policy_id: draft.policyId.trim(), version: draft.version.trim(), loss_matrix: {},
    required_evidence: required, risk_appetite: appetite, conditional_rules: [], min_improvement: {},
    ...(judgeMin !== null && judgeMin > 0 ? { judge_min_agreement: Number((judgeMin / 100).toFixed(6)) } : {}),
  };
}

const key = (projectId: string) => `qe.policy.v1:${projectId}`;

function isDraft(v: unknown): v is PolicyDraft {
  if (!v || typeof v !== 'object') return false;
  const d = v as Record<string, unknown>;
  return typeof d.policyId === 'string' && typeof d.version === 'string'
    && typeof d.required === 'object' && d.required !== null && typeof d.maxPct === 'object' && d.maxPct !== null;
}

/** The choice saved for this project in this browser. Corrupt or foreign data reads as `unset`. */
export function loadChoice(projectId: string, storage: Pick<Storage, 'getItem'> = window.localStorage): PolicyChoice {
  try {
    const raw = storage.getItem(key(projectId));
    if (!raw) return { mode: 'unset' };
    const v = JSON.parse(raw) as { mode?: string; draft?: unknown };
    if (v.mode === 'example') return { mode: 'example' };
    if (v.mode === 'custom' && isDraft(v.draft)) return { mode: 'custom', draft: v.draft };
  } catch { /* fall through */ }
  return { mode: 'unset' };
}

export function saveChoice(projectId: string, choice: PolicyChoice, storage: Pick<Storage, 'setItem' | 'removeItem'> = window.localStorage): void {
  try {
    if (choice.mode === 'unset') storage.removeItem(key(projectId));
    else storage.setItem(key(projectId), JSON.stringify(choice));
  } catch { /* storage unavailable: the choice then lasts for this page view only */ }
}

/** Friendly names for the policy form. Backend metric names stay the identifiers. */
export const METRIC_LABEL: Record<string, string> = {
  answer_correctness: 'Answer correctness',
  faithfulness: 'Faithfulness to retrieved text',
  citation_validity: 'Citation validity',
  retrieval_hit_rate: 'Retrieval hit rate',
  refusal_correctness: 'Correct refusals',
  completeness: 'Completeness',
  injection_resistance: 'Attack resistance',
  error_rate: 'Error rate',
  stability_pass_k: 'Stability across repeats',
  overall_pass_rate: 'Overall pass rate',
};

export const metricLabel = (name: string): string => METRIC_LABEL[name] ?? name.replace(/_/g, ' ');
