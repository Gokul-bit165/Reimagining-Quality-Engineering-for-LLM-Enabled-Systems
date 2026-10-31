export type StepKey = 'understand' | 'inputs' | 'run' | 'results' | 'operate';
/** The guided wizard. Order matters: it is the stepper. */
export const STEP_KEYS: StepKey[] = ['understand', 'inputs', 'run', 'results', 'operate'];

/** Work areas beside the wizard: they do not replace or reorder its steps. */
export type ToolKey = 'campaign' | 'judge';
export const TOOL_KEYS: ToolKey[] = ['campaign', 'judge'];
export type AreaKey = StepKey | ToolKey;

export type Route =
  | { name: 'connect' }
  | { name: 'project'; projectId: string; step: AreaKey; evalId: string | null; /** Set only on the campaign area. */ campaignId?: string | null }
  | { name: 'notfound'; hash: string };

const isArea = (s: string | undefined): s is AreaKey => Boolean(s) && ([...STEP_KEYS, ...TOOL_KEYS] as string[]).includes(s as string);

/** Hash route parser. `#connect`, `#p/<project>/<step>[/<evaluation>]`, `#p/<project>/campaign[/<campaign>]`, `#p/<project>/judge`. */
export function parseRoute(hash: string): Route {
  let h = '';
  try { h = decodeURIComponent(hash.replace(/^#/, '')); } catch { return { name: 'notfound', hash }; }
  // Tolerate path-style links such as #/projects/<id>/results/<eval>.
  h = h.replace(/^\/+/, '').replace(/^projects\//, 'p/');
  if (!h || h === 'connect') return { name: 'connect' };
  if (h.startsWith('p/')) {
    const [, projectId, step, sub] = h.split('/');
    if (projectId) {
      const s: AreaKey = isArea(step) ? step : 'understand';
      if (s === 'campaign') return { name: 'project', projectId, step: s, evalId: null, campaignId: sub || null };
      return { name: 'project', projectId, step: s, evalId: s === 'judge' ? null : sub || null };
    }
  }
  return { name: 'notfound', hash: h };
}

export function projectHref(projectId: string, step: AreaKey = 'understand', subId?: string | null): string {
  return `#p/${encodeURIComponent(projectId)}/${step}${subId ? `/${encodeURIComponent(subId)}` : ''}`;
}

export const campaignHref = (projectId: string, campaignId?: string | null): string => projectHref(projectId, 'campaign', campaignId);

const AREA_TITLE: Record<AreaKey, string> = {
  understand: 'Understand', inputs: 'Inputs', run: 'Run', results: 'Results', operate: 'Operate',
  campaign: 'Test campaign', judge: 'Judge & calibration',
};

/** Browser tab title for a route. `repoUrl` is the project's repository once known. */
export function routeTitle(route: Route, repoUrl: string | null): string {
  if (route.name === 'connect') return 'Connect · qe';
  if (route.name === 'notfound') return 'Not found · qe';
  const name = repoUrl ? repoUrl.replace(/^https:\/\/github\.com\//, '') : 'Project';
  const detail = route.step === 'campaign' && route.campaignId ? ` ${route.campaignId}` : '';
  return `${name} · ${AREA_TITLE[route.step]}${detail} · qe`;
}
