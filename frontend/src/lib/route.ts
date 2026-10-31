export type StepKey = 'understand' | 'inputs' | 'run' | 'results' | 'operate';
export const STEP_KEYS: StepKey[] = ['understand', 'inputs', 'run', 'results', 'operate'];

export type Route =
  | { name: 'connect' }
  | { name: 'project'; projectId: string; step: StepKey; evalId: string | null }
  | { name: 'legacy'; id: string }
  | { name: 'notfound'; hash: string };

const LEGACY_RUN_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$/;
const LEGACY = new Set(['new', 'bench', 'test-llm']);

/** Hash route parser. Primary flow is `#connect` and `#p/<project>/<step>[/<evaluation>]`. */
export function parseRoute(hash: string): Route {
  let h = '';
  try { h = decodeURIComponent(hash.replace(/^#/, '')); } catch { return { name: 'notfound', hash }; }
  // Tolerate path-style links such as #/projects/<id>/results/<eval>.
  h = h.replace(/^\/+/, '').replace(/^projects\//, 'p/');
  if (!h || h === 'connect') return { name: 'connect' };
  if (h.startsWith('p/')) {
    const [, projectId, step, evalId] = h.split('/');
    if (projectId) {
      const s = (STEP_KEYS as string[]).includes(step) ? (step as StepKey) : 'understand';
      return { name: 'project', projectId, step: s, evalId: evalId || null };
    }
  }
  if (LEGACY.has(h) || h.startsWith('bench-')) return { name: 'legacy', id: h };
  // Legacy run ids are plain tokens (scn-xxxx-app-variant). Anything path-like is not a run.
  if (LEGACY_RUN_ID.test(h)) return { name: 'legacy', id: h };
  return { name: 'notfound', hash: h };
}

export function projectHref(projectId: string, step: StepKey = 'understand', evalId?: string | null): string {
  return `#p/${encodeURIComponent(projectId)}/${step}${evalId ? `/${encodeURIComponent(evalId)}` : ''}`;
}
