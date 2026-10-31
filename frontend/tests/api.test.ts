import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, describeError, formatDetail } from '../src/api';
import { evaluationsApi, normalizeAnalysis, normalizeTaxonomy, projectsApi } from '../src/lib/projects';

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } }));
  vi.stubGlobal('fetch', fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe('api()', () => {
  it('returns parsed JSON on success', async () => {
    mockFetch(200, { ok: 1 });
    await expect(api('/x')).resolves.toEqual({ ok: 1 });
  });

  it('throws ApiError carrying status and backend detail', async () => {
    mockFetch(409, { detail: 'already running' });
    await expect(api('/x')).rejects.toMatchObject({ status: 409, message: '409 already running' });
  });

  it('maps a network failure to status 0 with a clear message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const err = (await api('/x').catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
    expect(describeError(err)).toMatch(/Cannot reach the backend/);
  });
});

describe('real-backend shapes', () => {
  it('normalizes the {code:{name,count,examples}} taxonomy and the legacy numeric form', () => {
    expect(normalizeTaxonomy({ 'QE-FAB': { name: 'Fabricated', count: 6, examples: [] }, X: 2 })).toEqual({
      'QE-FAB': { name: 'Fabricated', count: 6, examples: [] }, X: { name: 'X', count: 2, examples: [] },
    });
  });
  it('keeps analyser summary and next steps', () => {
    const a = normalizeAnalysis({ execution_mode: 'endpoint', summary: 'plain words', next_steps: ['a'] });
    expect(a?.summary).toBe('plain words');
    expect(a?.next_steps).toEqual(['a']);
  });
  it('filters evaluations by project and sorts newest first', async () => {
    mockFetch(200, [
      { id: 'a', project_id: 'p1', created: 1 }, { id: 'b', project_id: 'p2', created: 9 }, { id: 'c', project_id: 'p1', created: 5 },
    ]);
    expect((await evaluationsApi.forProject('p1')).map((e) => e.id)).toEqual(['c', 'a']);
  });
});

describe('formatDetail', () => {
  it('flattens FastAPI validation errors into readable text', () => {
    const d = [{ type: 'value_error', loc: ['body', 'authorized'], msg: 'Value error, you must confirm you own this app' }];
    expect(formatDetail(d)).toBe('authorized: you must confirm you own this app');
    expect(formatDetail('plain')).toBe('plain');
  });
});

describe('describeError', () => {
  it('explains 404 as a missing endpoint', () => {
    expect(describeError(new ApiError(404, '404 Not Found'), 'evaluations')).toMatch(/not support evaluations/);
  });
  it('labels conflicts and server errors', () => {
    expect(describeError(new ApiError(409, '409 busy'))).toMatch(/^Conflict \(409\): busy/);
    expect(describeError(new ApiError(500, '500 boom'))).toMatch(/Backend error \(500\): boom/);
  });
});

describe('projectsApi / evaluationsApi', () => {
  it('POSTs the create body including authorized', async () => {
    const f = mockFetch(202, { id: 'p1', state: 'cloning' });
    await projectsApi.create({ repo_url: 'https://github.com/a/b', authorized: true });
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/api/projects');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ repo_url: 'https://github.com/a/b', authorized: true });
  });

  it('fills missing optional fields of a project so the UI cannot crash', async () => {
    mockFetch(200, { id: 'p1', repo_url: 'r', state: 'ready', created_at: 't', analysis: { execution_mode: 'static_only' } });
    const p = await projectsApi.get('p1');
    expect(p.analysis?.risk_flags).toEqual([]);
    expect(p.analysis?.prompts).toEqual([]);
    expect(p.inputs).toEqual({});
  });

  it('normalizes evaluations: items get contexts', async () => {
    mockFetch(200, { id: 'e1', project_id: 'p1', state: 'running', items: [{ id: 'i', question: 'q', source: 'user' }] });
    const e = await evaluationsApi.get('e1');
    expect(e.items[0].contexts).toEqual([]);
    expect(e.progress).toEqual({ done: 0, total: 0 });
  });

  it('url-encodes ids', async () => {
    const f = mockFetch(200, {});
    await evaluationsApi.cancel('a/b');
    expect(f.mock.calls[0][0]).toBe('/api/evaluations/a%2Fb/cancel');
  });
});
