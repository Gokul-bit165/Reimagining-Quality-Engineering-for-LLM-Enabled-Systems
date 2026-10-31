import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MetricCard, SyntheticBadge, VerdictPanel } from '../src/components/flow/ui';
import { ConnectPage, validateRepoUrl } from '../src/pages/ConnectPage';
import { UnderstandStep } from '../src/pages/project/UnderstandStep';
import { evaluationCsv } from '../src/utils/reportExporter';
import type { Evaluation, Project } from '../src/types/api';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

describe('result primitives', () => {
  it('never shows a bare point estimate: value comes with interval and n', () => {
    render(<MetricCard name="grounding" m={{ value: 0.8, ci_low: 0.6, ci_high: 0.9, n: 25 }} />);
    expect(screen.getByText('80.0%')).toBeInTheDocument();
    expect(screen.getByText(/95% CI 60.0% to 90.0% · n=25/)).toBeInTheDocument();
  });

  it('says "Not measured" when there is no interval', () => {
    render(<MetricCard name="security" m={{ value: null, ci_low: null, ci_high: null, n: 0 }} />);
    expect(screen.getByText('Not measured')).toBeInTheDocument();
  });

  it('renders INSUFFICIENT EVIDENCE honestly with an explanation', () => {
    render(<VerdictPanel verdict="INSUFFICIENT_EVIDENCE" reasons={['Only 3 items measured']} />);
    expect(screen.getByTestId('verdict')).toHaveAttribute('data-tone', 'insufficient');
    expect(screen.getByText('INSUFFICIENT EVIDENCE')).toBeInTheDocument();
    expect(screen.getByText(/valid outcome/)).toBeInTheDocument();
  });

  it('flags pending human review', () => {
    render(<VerdictPanel verdict="CONDITIONAL" reasons={[]} pendingReview />);
    expect(screen.getByText('PENDING HUMAN REVIEW')).toBeInTheDocument();
  });

  it('shows the SYNTHETIC DATA badge', () => {
    render(<SyntheticBadge />);
    expect(screen.getByText(/SYNTHETIC DATA/)).toBeInTheDocument();
  });
});

describe('ConnectPage', () => {
  it('validates URLs', () => {
    expect(validateRepoUrl('')).toMatch(/Enter/);
    expect(validateRepoUrl('http://evil.example/x')).toMatch(/full URL/);
    expect(validateRepoUrl('https://github.com/a/b')).toBeNull();
  });

  it('blocks submit until authorization is confirmed, and does not call the API', async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(200, []));
    vi.stubGlobal('fetch', fetchMock);
    render(<ConnectPage />);
    await userEvent.type(document.getElementById('repo') as HTMLElement, 'https://github.com/a/b');
    await userEvent.click(screen.getByTestId('analyze'));
    expect(await screen.findByText(/must confirm you are allowed/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u, i]) => u === '/api/projects' && i?.method === 'POST')).toBe(false);
  });

  it('posts the project with authorized:true and navigates to understand', async () => {
    const fetchMock = vi.fn().mockImplementation((_url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === 'POST' ? json(202, { id: 'p9', state: 'cloning' }) : json(200, [])));
    vi.stubGlobal('fetch', fetchMock);
    render(<ConnectPage />);
    await userEvent.type(document.getElementById('repo') as HTMLElement, 'https://github.com/a/b');
    await userEvent.click(screen.getByTestId('authorized'));
    await userEvent.click(screen.getByTestId('analyze'));
    await waitFor(() => expect(window.location.hash).toBe('#p/p9/understand'));
    const post = fetchMock.mock.calls.find(([, i]) => i?.method === 'POST')!;
    expect(JSON.parse(post[1].body)).toEqual({ repo_url: 'https://github.com/a/b', authorized: true });
  });

  it('shows a clear error when the backend rejects with 409', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((_u: string, init?: RequestInit) =>
      Promise.resolve(init?.method === 'POST' ? json(409, { detail: 'authorization required' }) : json(200, []))));
    render(<ConnectPage />);
    await userEvent.type(document.getElementById('repo') as HTMLElement, 'https://github.com/a/b');
    await userEvent.click(screen.getByTestId('authorized'));
    await userEvent.click(screen.getByTestId('analyze'));
    expect(await screen.findByText(/Conflict \(409\): authorization required/)).toBeInTheDocument();
  });
});

const project = (over: Partial<Project> = {}): Project => ({
  id: 'p1', repo_url: 'https://github.com/a/b', branch: null, state: 'ready', error: null, created_at: 't', inputs: {},
  analysis: {
    framework: 'LangChain', language: 'Python', entrypoints: [], retriever: 'FAISS retriever', vector_store: 'faiss', llm_providers: ['openai'],
    prompts: [], doc_sources: [], env_vars: [], chunking: null,
    risk_flags: [{ id: 'r1', title: 'Unfiltered user input in prompt', evidence_file: 'app/chain.py', line: 42 }],
    execution_mode: 'static_only',
  },
  ...over,
});

describe('UnderstandStep', () => {
  it('explains static_only in plain language and cites file:line evidence', () => {
    render(<UnderstandStep project={project()} />);
    expect(screen.getByTestId('execution-mode')).toHaveTextContent(/analysed but NOT executed/i);
    expect(screen.getByText('app/chain.py:42')).toBeInTheDocument();
    expect(screen.getByText('LangChain')).toBeInTheDocument();
  });

  it('shows the error when analysis failed', () => {
    render(<UnderstandStep project={project({ state: 'failed', error: 'clone failed', analysis: null })} />);
    expect(screen.getByRole('alert')).toHaveTextContent('clone failed');
  });

  it('shows a loading state while analysing', () => {
    render(<UnderstandStep project={project({ state: 'analyzing', analysis: null })} />);
    expect(screen.getByRole('status')).toHaveTextContent(/Reading the code/);
  });
});

describe('evaluation export', () => {
  it('CSV marks synthetic data and carries intervals', () => {
    const ev: Evaluation = {
      id: 'e1', project_id: 'p1', state: 'done', progress: { done: 1, total: 1 }, error: null, synthetic: true,
      metrics: { grounding: { value: 0.5, ci_low: 0.2, ci_high: 0.8, n: 10 } },
      decision: { verdict: 'INSUFFICIENT_EVIDENCE', reasons: ['n too small'] },
      items: [{ id: 'i1', question: 'Q, with comma', reference_answer: null, answer: 'A', contexts: ['c1', 'c2'], scores: {}, passed: false, failure_reason: 'ungrounded', source: 'user' }],
    };
    const csv = evaluationCsv(ev);
    expect(csv).toContain('YES: SYNTHETIC DATA');
    expect(csv).toContain('INSUFFICIENT_EVIDENCE');
    expect(csv).toContain('"grounding","0.5","0.2","0.8","10"');
    expect(csv).toContain('"Q, with comma"');
    expect(csv).toContain('"c1 | c2"');
  });
});
