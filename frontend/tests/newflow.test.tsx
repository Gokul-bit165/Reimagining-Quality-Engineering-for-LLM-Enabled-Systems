import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MetricCard } from '../src/components/flow/ui';
import { RunStep } from '../src/pages/project/RunStep';
import { PlanSummary } from '../src/pages/project/OperateStep';
import { TargetConfigPanel, TargetTestOutcome } from '../src/pages/project/TargetConfigPanel';
import { QaEditor, cleanPairs } from '../src/pages/project/QaEditor';
import { AllMetrics, ItemRow, SampleSummary, PolicyUsed, fmtScore } from '../src/pages/project/ResultsParts';
import { emptyTargetForm } from '../src/lib/targetConfig';
import type { EvalItem, Evaluation, Project, TargetTestResult } from '../src/types/api';

beforeEach(() => window.localStorage.clear());
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

const TEMPLATE = {
  policy: {}, fields: {}, notes: [],
  metrics: [
    { name: 'answer_correctness', description: 'Share of root questions whose answer matches the reference.' },
    { name: 'error_rate', description: 'Share of root questions whose target call errored.' },
    { name: 'injection_resistance', description: 'Share of attack probes resisted.' },
  ],
};

const project = (qa = 2): Project => ({
  id: 'p1', repo_url: 'https://github.com/a/b', branch: null, state: 'ready', error: null, created_at: 't',
  analysis: null, inputs: { qa_pairs: Array.from({ length: qa }, (_, i) => ({ question: `Q${i}` })) },
});

function stubBackend(llm: { configured: boolean; missing: string[] }) {
  const posted: unknown[] = [];
  const fn = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url === '/api/policy/template') return Promise.resolve(json(200, TEMPLATE));
    if (url === '/api/llm/status') return Promise.resolve(json(200, llm));
    if (url === '/api/evaluations' && init?.method === 'POST') { posted.push(JSON.parse(String(init.body))); return Promise.resolve(json(202, { id: 'e1', state: 'queued' })); }
    return Promise.resolve(json(404, { detail: 'nope' }));
  });
  vi.stubGlobal('fetch', fn);
  return posted;
}

const renderRun = (p = project()) => render(<RunStep project={p} evaluation={null} evalError={null} onChanged={() => undefined} />);

describe('RunStep: LLM status', () => {
  it('lists missing env NAMES, disables generation with the reason, and still allows own Q&A', async () => {
    stubBackend({ configured: false, missing: ['QE_ALLOW_REAL_LLM', 'GROQ_API_KEY'] });
    renderRun();
    const banner = await screen.findByTestId('llm-banner');
    expect(banner).toHaveTextContent('QE_ALLOW_REAL_LLM');
    expect(banner).toHaveTextContent('GROQ_API_KEY');
    expect(screen.getByTestId('generate-questions')).toBeDisabled();
    expect(screen.getByTestId('generate-disabled-reason')).toHaveTextContent(/no language model is configured/i);
  });

  it('blocks the run when there are no Q&A pairs and nothing can generate them', async () => {
    stubBackend({ configured: false, missing: ['GROQ_API_KEY'] });
    renderRun(project(0));
    await screen.findByTestId('llm-banner');
    expect(screen.getByTestId('run-blockers')).toHaveTextContent(/no questions to ask/i);
    expect(screen.getByTestId('start-eval')).toBeDisabled();
  });
});

describe('RunStep: policy gate', () => {
  it('cannot run until a policy is chosen, then sends use_example_policy with the defaults 50 / 3', async () => {
    const posted = stubBackend({ configured: true, missing: [] });
    renderRun();
    await screen.findByTestId('policy-metrics');
    expect(screen.getByTestId('start-eval')).toBeDisabled();
    expect((document.getElementById('maxq') as HTMLInputElement).value).toBe('50');
    expect((document.getElementById('rep') as HTMLInputElement).value).toBe('3');
    expect(screen.getByTestId('cap-hint')).toHaveTextContent(/regression suite first, then security probes, then question variants, then your base questions/);

    await userEvent.click(screen.getByLabelText(/Use the example policy \(illustrative thresholds, not a real risk appetite\)/));
    await waitFor(() => expect(screen.getByTestId('start-eval')).toBeEnabled());
    await userEvent.click(screen.getByTestId('start-eval'));
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({ project_id: 'p1', max_questions: 50, repeats: 3, use_example_policy: true, include_security: true });
    expect(posted[0]).not.toHaveProperty('policy');
    expect(JSON.parse(window.localStorage.getItem('qe.policy.v1:p1')!)).toEqual({ mode: 'example' });
  });

  it('builds and validates a custom policy, requiring attack resistance while security is on', async () => {
    const posted = stubBackend({ configured: true, missing: [] });
    renderRun();
    await screen.findByTestId('policy-metrics');
    await userEvent.type(screen.getByLabelText('Policy name'), 'Acme support');
    await userEvent.type(screen.getByLabelText('Version'), '2026-1');
    await userEvent.click(screen.getByLabelText('Require Answer correctness'));
    await userEvent.type(screen.getByLabelText(/Highest failure rate you accept for Answer correctness/), '15');
    expect(screen.getByTestId('start-eval')).toBeDisabled();
    expect(screen.getByTestId('run-blockers')).toHaveTextContent(/Attack resistance/);

    await userEvent.click(screen.getByLabelText('Require Attack resistance'));
    await userEvent.type(screen.getByLabelText(/Highest failure rate you accept for Attack resistance/), '5');
    await waitFor(() => expect(screen.getByTestId('start-eval')).toBeEnabled());
    await userEvent.click(screen.getByTestId('start-eval'));
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({
      policy: { policy_id: 'Acme support', version: '2026-1', required_evidence: ['answer_correctness', 'injection_resistance'],
        risk_appetite: { answer_correctness: 0.15, injection_resistance: 0.05 } },
    });
    expect(posted[0]).not.toHaveProperty('use_example_policy');
  });

  it('warns that turning security probes off blocks RELEASE', async () => {
    stubBackend({ configured: true, missing: [] });
    renderRun();
    await screen.findByTestId('policy-metrics');
    expect(screen.queryByTestId('security-off-warning')).toBeNull();
    await userEvent.click(screen.getByLabelText(/Include security probes/));
    expect(screen.getByTestId('security-off-warning')).toHaveTextContent(/cannot be recommended for RELEASE/);
  });

  it('restores the saved policy per project on the next visit', async () => {
    stubBackend({ configured: true, missing: [] });
    window.localStorage.setItem('qe.policy.v1:p1', JSON.stringify({ mode: 'custom', draft: { policyId: 'Saved', version: '9', required: { error_rate: true }, maxPct: { error_rate: '3' } } }));
    renderRun();
    await screen.findByTestId('policy-metrics');
    expect((screen.getByLabelText('Policy name') as HTMLInputElement).value).toBe('Saved');
    expect((screen.getByLabelText('Require Error rate') as HTMLInputElement).checked).toBe(true);
  });
});

describe('Target connection', () => {
  const result = (over: Partial<TargetTestResult>): TargetTestResult => ({
    ok: true, answer: 'Thirty days.', contexts: ['refund-policy.md'], contexts_kind: 'ids', latency_s: 0.42, error: null, raw_preview: '{"answer":"Thirty days."}', warnings: [], ...over,
  });

  it('says plainly that ids are not passage text and faithfulness will not be measured', () => {
    render(<TargetTestOutcome result={result({ warnings: ['contexts look like ids/filenames, not passage text: faithfulness and retrieval cannot be measured'] })} />);
    expect(screen.getByTestId('target-test-status')).toHaveTextContent('CONNECTED');
    expect(screen.getByText(/returned ids, not passage text/)).toHaveTextContent(/faithfulness will not be measured/);
    expect(screen.getByTestId('target-test-kind')).toHaveTextContent(/Ids or file names only/);
    expect(screen.getByTestId('target-test-raw')).toHaveTextContent('Thirty days');
  });

  it('shows failures with the precise error, and passage text as measurable', () => {
    const { unmount } = render(<TargetTestOutcome result={result({ ok: false, answer: '', contexts: [], contexts_kind: 'none', error: 'answer_path "data.x" did not resolve', raw_preview: null })} />);
    expect(screen.getByTestId('target-test-status')).toHaveTextContent('FAILED');
    expect(screen.getByRole('alert')).toHaveTextContent('answer_path "data.x" did not resolve');
    unmount();
    render(<TargetTestOutcome result={result({ contexts: ['Refunds are accepted within 30 days of purchase.'], contexts_kind: 'text' })} />);
    expect(screen.getByTestId('target-test-kind')).toHaveTextContent(/Faithfulness and retrieval can be measured/);
  });

  it('applies a preset and refuses to test while the request body is invalid', async () => {
    const onTest = vi.fn().mockResolvedValue(result({}));
    function Harness() {
      const [form, setForm] = React.useState(emptyTargetForm());
      const [secrets, setSecrets] = React.useState<Record<string, string>>({});
      return <TargetConfigPanel endpoint="https://staging.example.com/ask" onEndpoint={() => undefined} endpointError={null} staticOnly={false}
        form={form} onForm={setForm} secrets={secrets} onSecrets={setSecrets} envNames={[]} storedNames={['OLD_KEY']} defaultQuestion="Refund window?" onTest={onTest} />;
    }
    render(<Harness />);
    await userEvent.click(screen.getByTestId('preset-openai'));
    expect((screen.getByTestId('tc-template') as HTMLTextAreaElement).value).toContain('"messages"');
    expect((document.getElementById('tc-answer') as HTMLInputElement).value).toBe('choices.0.message.content');

    await userEvent.click(screen.getByTestId('add-header'));
    await userEvent.type(screen.getByLabelText('Header 1 name'), 'Authorization');
    await userEvent.type(screen.getByLabelText(/Header 1 value/), 'Bearer abc');
    expect(await screen.findByRole('alert')).toHaveTextContent(/Use a secret reference/);
    expect(screen.getByTestId('test-connection')).toBeDisabled();

    await userEvent.clear(screen.getByLabelText(/Header 1 value/));
    await userEvent.type(screen.getByLabelText(/Header 1 value/), 'Bearer ${{API_TOKEN}');
    await waitFor(() => expect(screen.getByTestId('test-connection')).toBeEnabled());
    // typing the new secret while OLD_KEY is stored warns that the vault is replaced as a set
    await userEvent.type(screen.getByLabelText('API_TOKEN'), 'tok');
    expect(screen.getByTestId('secrets-drop-warning')).toHaveTextContent('OLD_KEY');
    await userEvent.click(screen.getByTestId('test-connection'));
    expect(onTest).toHaveBeenCalledWith('Refund window?');
    expect(await screen.findByTestId('target-test-result')).toBeInTheDocument();
  });
});

describe('Q&A editor', () => {
  it('sets the tri-state, clears the reference for "not answerable", and cleanPairs honours the backend rule', async () => {
    const onChange = vi.fn();
    render(<QaEditor pairs={[{ question: 'Q1', reference_answer: 'A1' }, { question: 'Q2' }]} onChange={onChange} />);
    expect(screen.getByTestId('qa-unchecked')).toHaveTextContent('1 of 2');
    const select = screen.getAllByLabelText('Can the documents answer it?')[0];
    expect((select as HTMLSelectElement).value).toBe('unknown');
    await userEvent.selectOptions(select, 'no');
    expect(onChange).toHaveBeenCalledWith([{ question: 'Q1', reference_answer: '', answerable: false }, { question: 'Q2' }]);
    expect(cleanPairs([{ question: ' Q1 ', reference_answer: 'x', answerable: false }, { question: 'Q2', reference_answer: ' A ', answerable: true }, { question: '  ' }, { question: 'Q3', answerable: null }]))
      .toEqual([{ question: 'Q1', answerable: false }, { question: 'Q2', reference_answer: 'A', answerable: true }, { question: 'Q3' }]);
  });
});

const item = (over: Partial<EvalItem>): EvalItem => ({
  id: 'i1', question: 'What is the refund window?', reference_answer: null, answer: 'Thirty days', contexts: [], scores: {}, passed: null, failure_reason: null, source: 'user', ...over,
});

describe('Results: not checked and honest nulls', () => {
  it('renders passed:null as NOT CHECKED with its own tone, never as a failure', async () => {
    render(<ul><ItemRow item={item({})} /></ul>);
    const badge = screen.getByText('NOT CHECKED');
    expect(badge).toHaveAttribute('data-tone', 'unchecked');
    expect(screen.queryByText('FAIL')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: /refund window/ }));
    expect(screen.getByText(/neither a pass nor a failure/)).toBeInTheDocument();
    expect(screen.queryByText(/Why it failed/)).toBeNull();
  });

  it('formats null scores as not measured and per-repeat nulls as not checked', () => {
    expect(fmtScore(null)).toBe('not measured');
    expect(fmtScore([true, null, false])).toBe('pass / not checked / fail');
    expect(fmtScore(0.5)).toBe('0.500');
  });

  it('shows contexts_kind and labels the judge as advisory, outside the scores', async () => {
    render(<ul><ItemRow item={item({ passed: true, scores: { correct: true, faithful: null, judge_correct_untrusted: false }, detail: { contexts_kind: 'ids', unsupported_claims: [] } })} /></ul>);
    await userEvent.click(screen.getByRole('button', { name: /refund window/ }));
    expect(screen.getByTestId('contexts-kind')).toHaveTextContent(/Ids or file names only/);
    const judge = screen.getByTestId('judge-advisory');
    expect(within(judge).getByText('ADVISORY')).toBeInTheDocument();
    expect(judge).toHaveTextContent(/never changes the pass\/fail result/);
    expect(screen.getByText('faithful: not measured')).toBeInTheDocument();
    expect(screen.queryByText(/judge correct untrusted:/)).toBeNull();
  });

  it('marks unconfirmed generated items ADVISORY', () => {
    render(<ul><ItemRow item={item({ passed: true, source: 'generated', lineage: { advisory: true } })} /></ul>);
    expect(screen.getByText('ADVISORY')).toBeInTheDocument();
  });
});

const evalOf = (over: Partial<Evaluation>): Evaluation => ({
  id: 'e1', project_id: 'p1', state: 'done', progress: { done: 3, total: 3 }, error: null, metrics: {}, decision: null, items: [], ...over,
});

describe('Results: sample, metrics, policy', () => {
  it('states distinct questions vs test items and the unchecked count', () => {
    render(<SampleSummary projectId="p1" ev={evalOf({ sample: { n_roots: 12, n_items: 31 }, unchecked: { count: 4, ids: [] }, advisory: { unconfirmed: 2, ids: [] } })} />);
    expect(screen.getByTestId('sample-summary')).toHaveTextContent('12 distinct questions, 31 test items');
    expect(screen.getByTestId('unchecked-banner')).toHaveTextContent('4 items not checked');
    expect(screen.getByText(/2 generated items are advisory/)).toBeInTheDocument();
  });

  it('shows n_roots on cards and in the all-metrics table, with null as not measured', () => {
    render(<MetricCard name="accuracy" m={{ value: 0.8, ci_low: 0.6, ci_high: 0.9, n: 12, n_roots: 12, n_items: 30 }} />);
    expect(screen.getByText(/n=12 questions from 30 items/)).toBeInTheDocument();
    cleanup();
    render(<AllMetrics metrics={{
      faithfulness: { value: null, ci_low: null, ci_high: null, n: 0, n_roots: 0, n_items: 5, note: 'not measurable: no applicable items.' },
      latency_p50_s: { value: 0.25, ci_low: null, ci_high: null, n: 9 },
    }} />);
    expect(screen.getByText('not measured')).toBeInTheDocument();
    expect(screen.getByText('0.25 s')).toBeInTheDocument();
  });

  it('flags an example policy and shows saved limits only for the matching policy', () => {
    const d = { verdict: 'INSUFFICIENT_EVIDENCE' as const, reasons: ['security not tested: no injection/exfiltration probes ran'], policy: 'EXAMPLE-realeval@0', policy_is_example: true };
    const { unmount } = render(<PolicyUsed projectId="p1" ev={evalOf({ decision: d })} />);
    expect(screen.getByTestId('policy-example-badge')).toHaveTextContent('EXAMPLE POLICY');
    unmount();
    window.localStorage.setItem('qe.policy.v1:p1', JSON.stringify({ mode: 'custom', draft: { policyId: 'Acme', version: '1', required: { error_rate: true }, maxPct: { error_rate: '4' } } }));
    render(<PolicyUsed projectId="p1" ev={evalOf({ decision: { ...d, policy: 'Acme@1', policy_is_example: false } })} />);
    expect(screen.queryByTestId('policy-example-badge')).toBeNull();
    expect(screen.getByText(/Error rate: failure rate at most 4%/)).toBeInTheDocument();
  });
});

describe('Operate: monitoring plan fields', () => {
  it('renders derived_from, attention, unmeasured_required and the watch table readably', () => {
    render(<PlanSummary onDownload={vi.fn()} plan={{
      derived_from: { failed_items: 3, failure_classes: { 'QE-FAB': 2, 'QE-INJ': 1 }, unchecked_items: 4 },
      watch: [
        { metric: 'answer_correctness', required: true, status: 'failing', failure_rate: 0.4, failure_rate_ci: [0.3, 0.5], appetite: 0.2, n_roots: 10 },
        { metric: 'faithfulness', required: true, status: 'unmeasured', failure_rate: null, failure_rate_ci: [null, null], appetite: 0.1, n_roots: 0 },
      ],
      attention: ['answer_correctness'], unmeasured_required: ['faithfulness'],
    }} />);
    expect(screen.getByTestId('plan-derived')).toHaveTextContent('3 failed item(s) in QE-FAB (2), QE-INJ (1), 4 item(s) not checked');
    expect(screen.getByTestId('plan-attention')).toHaveTextContent('Answer correctness');
    expect(screen.getByTestId('plan-unmeasured')).toHaveTextContent(/Faithfulness to retrieved text/);
    const table = screen.getByTestId('watch-table');
    expect(within(table).getByText('FAILING')).toBeInTheDocument();
    expect(within(table).getByText('NOT MEASURED')).toBeInTheDocument();
    expect(table).toHaveTextContent('40.0% (30.0% to 50.0%)');
  });
});
