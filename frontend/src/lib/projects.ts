import { api, apiText, jsonInit } from '../api';
import type {
  CreateProjectBody, Evaluation, EvaluationOptions, EvaluationSummary, LlmStatus, PolicyTemplate, TargetConfig, TargetTestResult,
  TaxonomyClass, MonitoringPlan, Project, ProjectAnalysis, ProjectInputs, SignoffBody, SuggestedInputs,
} from '../types/api';

/** Fill optional collections so the UI never trips on a partial analysis. */
export function normalizeAnalysis(a: Partial<ProjectAnalysis> | null | undefined): ProjectAnalysis | null {
  if (!a) return null;
  return {
    ...a,
    framework: a.framework ?? null,
    language: a.language ?? null,
    entrypoints: a.entrypoints ?? [],
    retriever: a.retriever ?? null,
    vector_store: a.vector_store ?? null,
    llm_providers: a.llm_providers ?? [],
    prompts: a.prompts ?? [],
    doc_sources: a.doc_sources ?? [],
    env_vars: a.env_vars ?? [],
    chunking: a.chunking ?? null,
    risk_flags: a.risk_flags ?? [],
    execution_mode: a.execution_mode ?? 'static_only',
    next_steps: a.next_steps ?? [],
  };
}

export function normalizeProject(p: Project): Project {
  return {
    ...p, branch: p.branch ?? null, error: p.error ?? null, inputs: p.inputs ?? {}, analysis: normalizeAnalysis(p.analysis),
    target_config: p.target_config ?? null, secrets_set: p.secrets_set ?? [], runtime: p.runtime ?? null,
  };
}

/** Accepts {code: {name,count,examples}} or the older {code: count}. */
export function normalizeTaxonomy(raw: unknown): Record<string, TaxonomyClass> {
  const out: Record<string, TaxonomyClass> = {};
  if (!raw || typeof raw !== 'object') return out;
  for (const [code, v] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof v === 'number') out[code] = { name: code, count: v, examples: [] };
    else if (v && typeof v === 'object') {
      const o = v as Partial<TaxonomyClass>;
      out[code] = { name: o.name ?? code, count: o.count ?? 0, examples: o.examples ?? [] };
    }
  }
  return out;
}

export function sortNewest(list: EvaluationSummary[]): EvaluationSummary[] {
  return [...list].sort((a, b) => (b.created ?? 0) - (a.created ?? 0));
}

export function normalizeEvaluation(e: Evaluation): Evaluation {
  return {
    ...e,
    progress: e.progress ?? { done: 0, total: 0 },
    error: e.error ?? null,
    metrics: e.metrics ?? {},
    decision: e.decision ?? null,
    scorecard: e.scorecard ?? {},
    failure_taxonomy: normalizeTaxonomy(e.failure_taxonomy as unknown),
    items: (e.items ?? []).map((i) => ({ ...i, contexts: i.contexts ?? [], scores: i.scores ?? {} })),
    unchecked: e.unchecked ?? { count: (e.items ?? []).filter((i) => i.passed === null).length, ids: [] },
  };
}

export const projectsApi = {
  create: (body: CreateProjectBody) =>
    api<{ id: string; state: string }>('/api/projects', jsonInit('POST', body)),
  list: async () => (await api<Project[]>('/api/projects')).map(normalizeProject),
  get: async (id: string) => normalizeProject(await api<Project>(`/api/projects/${encodeURIComponent(id)}`)),
  saveInputs: (id: string, body: ProjectInputs) =>
    api<unknown>(`/api/projects/${encodeURIComponent(id)}/inputs`, jsonInit('POST', body)),
  remove: (id: string) => api<unknown>(`/api/projects/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  upload: (file: File, authorized: boolean) => {
    const form = new FormData();
    form.append('file', file);
    form.append('authorized', String(authorized));
    return api<{ id: string; state: string }>('/api/projects/upload', { method: 'POST', body: form });
  },
  suggestedInputs: (id: string) =>
    api<SuggestedInputs>(`/api/projects/${encodeURIComponent(id)}/suggested-inputs`),
  /** Secrets are write-only: sent once, never read back or stored in the browser. */
  saveSecrets: (id: string, secrets: Record<string, string>) =>
    api<unknown>(`/api/projects/${encodeURIComponent(id)}/secrets`, jsonInit('POST', { values: secrets })),
  regression: (id: string) => api<unknown>(`/api/projects/${encodeURIComponent(id)}/regression`),
  saveTargetConfig: (id: string, cfg: TargetConfig) =>
    api<TargetConfig>(`/api/projects/${encodeURIComponent(id)}/target-config`, jsonInit('POST', cfg)),
  /** Sends ONE probe question through the saved endpoint and target configuration. */
  testTarget: (id: string, question: string) =>
    api<TargetTestResult>(`/api/projects/${encodeURIComponent(id)}/target-test`, jsonInit('POST', { question })),
};

export const policyApi = {
  template: () => api<PolicyTemplate>('/api/policy/template'),
};

export const llmApi = {
  /** Setting NAMES only, never values. */
  status: () => api<LlmStatus>('/api/llm/status'),
};

export const evaluationsApi = {
  create: (body: EvaluationOptions) =>
    api<{ id: string; state: string }>('/api/evaluations', jsonInit('POST', body)),
  list: () => api<EvaluationSummary[]>('/api/evaluations'),
  /** Evaluations of one project, newest first. */
  forProject: async (projectId: string) =>
    sortNewest((await api<EvaluationSummary[]>('/api/evaluations')).filter((e) => e.project_id === projectId)),
  get: async (id: string) =>
    normalizeEvaluation(await api<Evaluation>(`/api/evaluations/${encodeURIComponent(id)}`)),
  cancel: (id: string) =>
    api<unknown>(`/api/evaluations/${encodeURIComponent(id)}/cancel`, { method: 'POST' }),
  signoff: (id: string, body: SignoffBody) =>
    api<unknown>(`/api/evaluations/${encodeURIComponent(id)}/signoff`, jsonInit('POST', body)),
  /** A human confirms one advisory (model-written) item; verdicts are recomputed. */
  confirmItem: (id: string, itemId: string, reviewer: string) =>
    api<unknown>(`/api/evaluations/${encodeURIComponent(id)}/items/${encodeURIComponent(itemId)}/confirm`, jsonInit('POST', { reviewer })),
  addRegression: (id: string, itemIds: string[]) =>
    api<unknown>(`/api/evaluations/${encodeURIComponent(id)}/regression`, jsonInit('POST', { item_ids: itemIds })),
  monitoringPlan: (id: string) =>
    api<MonitoringPlan>(`/api/evaluations/${encodeURIComponent(id)}/monitoring-plan`),
  dataset: (id: string) => apiText(`/api/evaluations/${encodeURIComponent(id)}/dataset`),
  report: (id: string) => apiText(`/api/evaluations/${encodeURIComponent(id)}/report`),
};
