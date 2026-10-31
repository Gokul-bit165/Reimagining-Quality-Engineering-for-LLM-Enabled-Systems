import type { DetectedItem, ExecutionMode, Verdict } from '../types/api';

export const EXECUTION_MODE_INFO: Record<ExecutionMode, { label: string; tone: 'ok' | 'warn' | 'info'; text: string }> = {
  endpoint: {
    label: 'Live endpoint',
    tone: 'ok',
    text: 'Questions are sent to your deployed endpoint and the real answers are scored. This gives the strongest evidence.',
  },
  docker: {
    label: 'Sandboxed container',
    tone: 'ok',
    text: 'The app is built and run inside an isolated container, then queried. Real answers are scored; nothing touches your machine.',
  },
  static_only: {
    label: 'Static analysis only',
    tone: 'warn',
    text: 'Your code was analysed but NOT executed. Findings come from reading the source, so no real answers were produced. Add a deployed endpoint URL to get measured results.',
  },
};

export const VERDICT_INFO: Record<Verdict, { label: string; tone: 'release' | 'conditional' | 'reject' | 'insufficient'; text: string }> = {
  RELEASE: { label: 'Release', tone: 'release', text: 'Evidence supports shipping under the policy.' },
  CONDITIONAL: { label: 'Conditional', tone: 'conditional', text: 'Shippable only if the listed conditions are met.' },
  REJECT: { label: 'Reject', tone: 'reject', text: 'Evidence shows a breach of the policy. Do not ship.' },
  INSUFFICIENT_EVIDENCE: {
    label: 'Insufficient evidence',
    tone: 'insufficient',
    text: 'Not enough measured evidence to decide. This is a valid outcome, not a failure of the tool.',
  },
};

export const RISK_FOCUS_OPTIONS: { id: string; label: string }[] = [
  { id: 'hallucination', label: 'Hallucination (made-up answers)' },
  { id: 'retrieval', label: 'Retrieval quality (paraphrases, typos)' },
  { id: 'robustness', label: 'Robustness to noisy questions' },
  { id: 'prompt_injection', label: 'Prompt injection' },
  { id: 'data_leak', label: 'Data leakage / PII' },
];

/** Turn a detector item (string or object) into a readable label. */
export function labelOf(item: DetectedItem | null | undefined): string {
  if (item === null || item === undefined) return '';
  if (typeof item === 'string') return item;
  const line = typeof item.line === 'number' ? `:${item.line}` : '';
  if (typeof item.file === 'string' && item.file) {
    // Entry points carry a name (function) and file; prompts only a file.
    return typeof item.name === 'string' && item.name ? `${item.name} (${item.file}${line})` : `${item.file}${line}`;
  }
  for (const k of ['name', 'path', 'type', 'kind', 'value', 'text', 'id']) {
    const v = item[k];
    if (typeof v === 'string' && v) return k === 'name' || k === 'path' ? `${v}${line}` : v;
  }
  return JSON.stringify(item);
}

export function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
  return `${(v * 100).toFixed(digits)}%`;
}

export function num(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
  return v.toFixed(digits);
}

/** Plain-language text for the backend's terse failure reasons. */
export const FAILURE_REASON_TEXT: Record<string, string> = {
  faithful: 'The answer contains claims the retrieved passages do not support.',
  correct: 'The answer does not match the reference answer.',
  refusal_correct: 'The app answered a question it should have declined (nothing in the documents supports an answer).',
  citation_valid: 'The answer cites a source that does not exist or does not support it.',
  retrieval_hit: 'The retriever did not return the passage that holds the answer.',
  injection_resisted: 'The app followed an instruction hidden in the input (prompt injection).',
};
