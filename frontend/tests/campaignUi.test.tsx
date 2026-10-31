import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Comparison, RecommendationPanel } from '../src/pages/campaign/Comparison';
import { TargetResults } from '../src/pages/campaign/TargetResults';
import { StageTracker } from '../src/pages/campaign/StageTracker';
import { PlanView } from '../src/pages/campaign/PlanView';
import { ReviewPanel } from '../src/pages/campaign/ReviewPanel';
import { AuditTrail } from '../src/pages/campaign/AuditTrail';
import { TargetEditor } from '../src/pages/campaign/TargetEditor';
import { ReportActions } from '../src/components/flow/ReportActions';
import { ExecutionPanel } from '../src/pages/project/ExecutionPanel';
import { JudgeStatusPanel } from '../src/pages/project/JudgePanel';
import { ItemJudgeDetail, JudgeSummary } from '../src/pages/project/JudgeResults';
import { emptyTarget } from '../src/lib/campaign';
import type { EvalItem, Project } from '../src/types/api';
import {
  CAMPAIGN_DONE, CAMPAIGN_INTERRUPTED, CAMPAIGN_RUNNING, CAMPAIGN_WINNER, EVENTS, JUDGE_STATUS, JUDGE_UNCONFIGURED, PLAN, PROJECT, STATIC_PROJECT,
} from './fixtures/campaign';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const routes = (map: Record<string, () => Response>) => {
  const fn = vi.fn((url: string, init?: RequestInit) => {
    const key = Object.keys(map).find((k) => `${init?.method ?? 'GET'} ${url}`.includes(k));
    return Promise.resolve(key ? map[key]() : json(404, { detail: 'no route' }));
  });
  vi.stubGlobal('fetch', fn);
  return fn;
};

describe('Comparison', () => {
  it('shows a side-by-side table with an interval and n_roots in every cell', () => {
    render(<Comparison campaign={CAMPAIGN_DONE} />);
    const cell = screen.getByTestId('cell-overall_pass_rate-Chunk 512');
    expect(cell).toHaveTextContent('62.0% (45.0% to 77.0%)');
    expect(cell).toHaveTextContent('n_roots = 24');
    expect(screen.getByTestId('cell-overall_pass_rate-Chunk 1024')).toHaveTextContent('70.0%');
  });

  it('labels pairwise outcomes, explains them, and warns about multiplicity', () => {
    render(<Comparison campaign={CAMPAIGN_DONE} />);
    expect(screen.getByTestId('multiplicity-caution')).toHaveTextContent(/Bonferroni across 6/);
    expect(screen.getByTestId('pair-overall_pass_rate')).toHaveAttribute('data-outcome', 'NO_SIGNIFICANT_DIFFERENCE');
    expect(screen.getByTestId('pair-answer_correctness')).toHaveTextContent('INSUFFICIENT EVIDENCE');
    expect(screen.getAllByText(/absence of evidence, not evidence that they are equal/).length).toBeGreaterThan(0);
  });

  it('never presents a winner when the backend says there is none', () => {
    render(<RecommendationPanel campaign={CAMPAIGN_DONE} />);
    expect(screen.getByTestId('recommendation')).toHaveAttribute('data-winner', 'none');
    expect(screen.getByTestId('rec-none')).toHaveTextContent('No target is established as better.');
    expect(screen.queryByTestId('rec-winner')).toBeNull();
    expect(screen.getByTestId('rec-caveats')).toHaveTextContent(/too few root questions/);
  });

  it('names the winner only when the backend does, with its own policy decision still shown', () => {
    render(<RecommendationPanel campaign={CAMPAIGN_WINNER} />);
    expect(screen.getByTestId('rec-winner')).toHaveTextContent('Chunk 1024');
    expect(screen.getByText(/Chunk 512: INSUFFICIENT EVIDENCE/)).toBeInTheDocument();
  });

  it('explains that a single target has nothing to compare', () => {
    const one = { ...CAMPAIGN_DONE, targets: [CAMPAIGN_DONE.targets[0]], results: { 'Chunk 512': CAMPAIGN_DONE.results['Chunk 512'] }, comparisons: { alpha: 0.05, family_size: 0, multiplicity: 'single target', pairs: [] } };
    render(<Comparison campaign={one} />);
    expect(screen.getByText(/one target, so there is nothing to compare/)).toBeInTheDocument();
  });
});

describe('TargetResults', () => {
  it('flags the example policy, shows latency percentiles and says "not reported" for missing tokens and cost', () => {
    render(<TargetResults campaign={CAMPAIGN_DONE} />);
    const a = screen.getByTestId('target-result-Chunk 512');
    const b = screen.getByTestId('target-result-Chunk 1024');
    expect(within(a).getByTestId('example-policy')).toBeInTheDocument();
    expect(within(a).getByTestId('performance')).toHaveTextContent('420 ms / 1.30 s / 2.10 s');
    expect(within(a).getByTestId('perf-tokens')).toHaveTextContent('11,000 tokens in 70 of 72 calls');
    expect(within(b).getByTestId('perf-tokens')).toHaveTextContent('not reported');
    expect(within(b).getByTestId('perf-cost')).toHaveTextContent('not reported');
    expect(within(a).getByTestId('sample-Chunk 512')).toHaveTextContent('n_roots = 24');
    expect(within(a).getByText(/n=4 < 5: interval too wide/)).toBeInTheDocument();
  });
});

describe('StageTracker', () => {
  it('shows nine stages with status and a running badge', () => {
    render(<StageTracker campaign={CAMPAIGN_RUNNING} onChanged={() => undefined} />);
    expect(screen.getAllByRole('listitem').filter((li) => li.getAttribute('data-testid')?.startsWith('stage-'))).toHaveLength(9);
    expect(screen.getByTestId('stage-execution')).toHaveAttribute('data-status', 'running');
    expect(screen.getByTestId('stage-risk_definition')).toHaveAttribute('data-status', 'done');
    expect(screen.getByTestId('campaign-progress')).toHaveTextContent('40 of 144');
    expect(screen.getByTestId('cancel-campaign')).toBeInTheDocument();
    expect(screen.queryByTestId('resume-banner')).toBeNull();
  });

  it('offers Resume on an interrupted campaign and posts to the resume route', async () => {
    const fn = routes({ 'POST /api/campaigns/cmp-0a1b2c3d/resume': () => json(202, { id: 'x' }) });
    const changed = vi.fn();
    render(<StageTracker campaign={CAMPAIGN_INTERRUPTED} onChanged={changed} />);
    expect(screen.getByTestId('resume-banner')).toHaveTextContent(/can be resumed/);
    await userEvent.click(screen.getByTestId('resume-campaign'));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(fn).toHaveBeenCalledWith('/api/campaigns/cmp-0a1b2c3d/resume', expect.objectContaining({ method: 'POST' }));
  });

  it('shows a stage error and an incomplete-run warning', () => {
    const failed = { ...CAMPAIGN_RUNNING, state: 'failed' as const, incomplete: 'call budget exhausted (max_calls=2000)', stages: { ...CAMPAIGN_RUNNING.stages, execution: { ...CAMPAIGN_RUNNING.stages.execution, status: 'failed' as const, error: 'target unreachable' } } };
    render(<StageTracker campaign={failed} onChanged={() => undefined} />);
    expect(screen.getByText('target unreachable')).toBeInTheDocument();
    expect(screen.getByTestId('campaign-incomplete')).toHaveTextContent(/call budget exhausted/);
  });
});

describe('PlanView', () => {
  it('shows risks, cases by scenario, COVERED / CHECK ONLY / GAP with the gap reason, and exports JSON', async () => {
    routes({ '/api/campaigns/cmp-0a1b2c3d/plan': () => json(200, PLAN) });
    render(<PlanView campaign={CAMPAIGN_DONE} />);
    expect(await screen.findByTestId('plan-view')).toBeInTheDocument();
    const m = screen.getByTestId('coverage-matrix');
    expect(within(screen.getByTestId('cov-hallucination')).getByText('COVERED')).toBeInTheDocument();
    expect(within(screen.getByTestId('cov-citation_check')).getByText('CHECK ONLY')).toBeInTheDocument();
    expect(within(screen.getByTestId('cov-data_leak')).getByText('GAP')).toBeInTheDocument();
    expect(m).toHaveTextContent('no case could be built from the supplied inputs and operators');
    expect(screen.getByTestId('cases-hallucination')).toHaveTextContent('Can I get a refund after a year?');
    expect(screen.getByTestId('plan-authoring')).toHaveTextContent(/advisory until a human confirms/);
    expect(screen.getByTestId('export-plan')).toBeInTheDocument();
  });

  it('says the plan is not ready before stage 2 finishes', () => {
    const early = { ...CAMPAIGN_RUNNING, stages: { ...CAMPAIGN_RUNNING.stages, test_plan: { ...CAMPAIGN_RUNNING.stages.test_plan, status: 'pending' as const } } };
    render(<PlanView campaign={early} />);
    expect(screen.getByText(/built in stage 2/)).toBeInTheDocument();
  });
});

describe('ReviewPanel', () => {
  it('requires a reviewer and rationale, then posts a per-target sign-off', async () => {
    const fn = routes({ 'POST /api/campaigns/cmp-0a1b2c3d/signoff': () => json(200, { id: 'x' }) });
    const changed = vi.fn();
    render(<ReviewPanel campaign={CAMPAIGN_DONE} onChanged={changed} />);
    await userEvent.click(screen.getByTestId('record-signoff-Chunk 512'));
    expect(await screen.findByText(/reviewer name \(above\) and a written rationale/)).toBeInTheDocument();
    await userEvent.type(screen.getByTestId('reviewer-name'), 'Dana');
    const form = screen.getByTestId('signoff-form-Chunk 512');
    await userEvent.type(within(form).getByLabelText('Rationale'), 'Evidence is thin but acceptable for staging.');
    await userEvent.click(screen.getByTestId('record-signoff-Chunk 512'));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    const call = fn.mock.calls.find(([u]) => String(u).endsWith('/signoff'))!;
    expect(JSON.parse(String((call[1] as RequestInit).body))).toEqual({ reviewer: 'Dana', decision: 'approve', rationale: 'Evidence is thin but acceptable for staging.', target_label: 'Chunk 512' });
  });

  it('confirms an advisory case via POST items/{id}/confirm', async () => {
    const fn = routes({ 'POST /api/campaigns/cmp-0a1b2c3d/items/g1/confirm': () => json(200, { id: 'x' }) });
    const changed = vi.fn();
    render(<ReviewPanel campaign={CAMPAIGN_DONE} onChanged={changed} />);
    await userEvent.type(screen.getByTestId('reviewer-name'), 'Dana');
    await userEvent.click(screen.getByTestId('confirm-g1'));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(fn).toHaveBeenCalledWith('/api/campaigns/cmp-0a1b2c3d/items/g1/confirm', expect.objectContaining({ method: 'POST', body: JSON.stringify({ reviewer: 'Dana' }) }));
  });

  it('shows the recorded sign-off instead of a form once reviewed', () => {
    const reviewed = structuredClone(CAMPAIGN_DONE);
    reviewed.results['Chunk 512'].decision = { ...reviewed.results['Chunk 512'].decision!, status: 'approved', signoff: { reviewer: 'Dana', decision: 'approve', rationale: 'ok' } };
    render(<ReviewPanel campaign={reviewed} onChanged={() => undefined} />);
    expect(screen.getByTestId('signed-Chunk 512')).toHaveTextContent('APPROVED');
    expect(screen.queryByTestId('signoff-form-Chunk 512')).toBeNull();
    expect(screen.getByTestId('confirm-g1')).toBeDisabled();
  });
});

describe('AuditTrail', () => {
  it('shows LEDGER VERIFIED, and LEDGER BROKEN loudly when verification fails', async () => {
    routes({ '/events': () => json(200, EVENTS) });
    const { unmount } = render(<AuditTrail campaign={CAMPAIGN_DONE} />);
    expect(await screen.findByTestId('ledger-badge')).toHaveTextContent('LEDGER VERIFIED');
    expect(screen.getAllByTestId('audit-row')).toHaveLength(2);
    unmount();
    routes({ '/events': () => json(200, { ...EVENTS, ledger_ok: false }) });
    render(<AuditTrail campaign={CAMPAIGN_DONE} />);
    expect(await screen.findByTestId('ledger-badge')).toHaveTextContent('LEDGER BROKEN');
    expect(screen.getByText(/failed verification/)).toBeInTheDocument();
  });
});

describe('TargetEditor', () => {
  it('adds up to 8 targets, switches kind, and removes', async () => {
    const Harness = () => {
      const [t, setT] = useState([emptyTarget('endpoint', 'A')]);
      return <TargetEditor targets={t} secretNames={['OPENAI_API_KEY']} onChange={setT} />;
    };
    render(<Harness />);
    expect(screen.queryByTestId('remove-target-0')).toBeNull();
    for (let i = 0; i < 7; i += 1) await userEvent.click(screen.getByTestId('add-target'));
    expect(screen.getByTestId('add-target')).toBeDisabled();
    expect(screen.getByTestId('target-7')).toBeInTheDocument();
    await userEvent.click(screen.getByTestId('remove-target-7'));
    expect(screen.queryByTestId('target-7')).toBeNull();
    await userEvent.click(within(screen.getByTestId('target-0')).getByLabelText('Bare model'));
    expect(within(screen.getByTestId('target-0')).getByLabelText('Base URL')).toBeInTheDocument();
  });
});

describe('ReportActions', () => {
  it('explains the "secret found, bundle withheld" 409 in plain words', async () => {
    routes({ '/evidence-bundle': () => json(409, { detail: 'a secret value was found in evidence.json: bundle withheld' }) });
    render(<ReportActions owner={{ kind: 'campaign', id: 'cmp-0a1b2c3d' }} />);
    await userEvent.click(screen.getByTestId('report-bundle'));
    expect(await screen.findByTestId('report-error')).toHaveTextContent(/withheld because a secret was found.*Nothing was exported/);
  });

  it('explains a 413 on the report and links to the html report', async () => {
    routes({ 'format=md': () => json(413, { detail: 'report exceeds the size cap' }) });
    render(<ReportActions owner={{ kind: 'evaluation', id: 'eval-0a1b2c3d' }} />);
    expect(screen.getByTestId('report-open-html')).toHaveAttribute('href', '/api/evaluations/eval-0a1b2c3d/qa-report?format=html');
    expect(screen.getByTestId('report-open-html')).toHaveAttribute('target', '_blank');
    await userEvent.click(screen.getByTestId('report-md'));
    expect(await screen.findByTestId('report-error')).toHaveTextContent(/too large to export/);
  });

  it('documents qe verify-bundle and the ledger head hash', () => {
    render(<ReportActions owner={{ kind: 'campaign', id: 'cmp-0a1b2c3d' }} />);
    expect(screen.getByText(/qe verify-bundle evidence-bundle-cmp-0a1b2c3d.zip/)).toBeInTheDocument();
    expect(screen.getByText(/ledger head hash/i, { selector: 'strong' })).toBeInTheDocument();
  });

  it('disables the actions with a reason before the run has finished', () => {
    render(<ReportActions owner={{ kind: 'campaign', id: 'cmp-0a1b2c3d' }} disabledReason="needs a finished campaign" />);
    expect(screen.getByTestId('report-bundle')).toBeDisabled();
    expect(screen.getByText('needs a finished campaign')).toBeInTheDocument();
  });
});

describe('ExecutionPanel', () => {
  it('says "analysed, not run" with the reason for static_only projects', () => {
    render(<ExecutionPanel project={STATIC_PROJECT as unknown as Project} />);
    expect(screen.getByTestId('static-only-note')).toHaveTextContent(/Analysed, not run.*no HTTP entry point/);
    expect(screen.getByTestId('exec-reason')).toHaveTextContent('no HTTP entry point and no Dockerfile could be detected');
    expect(screen.queryByTestId('execution-settings')).toBeNull();
  });

  it('shows mode, reason, run kind, state, logs, egress evidence and the allowlist warning for docker', async () => {
    routes({ '/api/projects/p1': () => json(200, PROJECT) });
    render(<ExecutionPanel project={PROJECT as unknown as Project} />);
    expect(screen.getByTestId('exec-mode')).toHaveTextContent('Sandboxed container (docker)');
    expect(screen.getByTestId('exec-mode')).toHaveTextContent('python-asgi');
    expect(await screen.findByTestId('runtime-state')).toHaveTextContent('RUNNING AND REACHABLE');
    expect(screen.getByTestId('build-log')).toHaveTextContent('Successfully built abc123');
    expect(screen.getByTestId('egress-log')).toHaveTextContent('DENY evil.example.com:443');
    expect(screen.getByTestId('egress-warning')).toHaveTextContent(/only your model provider's own hosts/i);
  });

  it('validates the allowlist and saves host, path and port overrides', async () => {
    const fn = routes({ 'POST /api/projects/p1/inputs': () => json(200, {}), '/api/projects/p1': () => json(200, PROJECT) });
    render(<ExecutionPanel project={PROJECT as unknown as Project} />);
    const box = await screen.findByRole('textbox', { name: /^Allowed outbound hosts/ });
    await userEvent.type(box, '{enter}https://bad.example.com');
    expect(screen.getByRole('alert')).toHaveTextContent(/is not valid/);
    expect(screen.getByTestId('save-execution')).toBeDisabled();
    await userEvent.clear(box);
    await userEvent.type(box, 'api.openai.com');
    await userEvent.click(screen.getByTestId('save-execution'));
    await waitFor(() => expect(fn.mock.calls.some(([u, i]) => String(u).endsWith('/inputs') && (i as RequestInit)?.method === 'POST')).toBe(true));
    const post = fn.mock.calls.find(([u, i]) => String(u).endsWith('/inputs') && (i as RequestInit)?.method === 'POST')!;
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({ egress_allowlist: ['api.openai.com'], app_path: '/ask', app_port: 8000 });
  });

  it('keeps polling while building and shows a spinner', async () => {
    const building = { ...PROJECT, runtime: { ...PROJECT.runtime, state: 'building', detail: 'building image' } };
    routes({ '/api/projects/p1': () => json(200, building) });
    render(<ExecutionPanel project={building as unknown as Project} />);
    expect(await screen.findByTestId('runtime-state')).toHaveTextContent('BUILDING THE CONTAINER IMAGE');
  });
});

describe('Judge panels', () => {
  it('shows independence, stale calibration and the family names', () => {
    render(<JudgeStatusPanel status={JUDGE_STATUS} error={null} />);
    expect(screen.getByTestId('judge-independence')).toHaveTextContent('INDEPENDENT');
    expect(screen.getByTestId('judge-stale')).toBeInTheDocument();
    expect(screen.getByText(/90.0% agreement with your labels \(95% CI 79.0% to 96.0%\) on 60 items/)).toBeInTheDocument();
  });

  it('lists missing setting NAMES only when the judge is not configured', () => {
    render(<JudgeStatusPanel status={JUDGE_UNCONFIGURED} error={null} />);
    expect(screen.getByTestId('judge-missing')).toHaveTextContent('QE_JUDGE_MODEL');
    expect(screen.getByTestId('judge-missing')).toHaveTextContent(/never values/);
    expect(screen.queryByTestId('judge-independence')).toBeNull();
  });

  it('shows gating vs advisory, panel agreement, conflicts and corrected rates with intervals', () => {
    const items = [{ id: 'i1', question: 'Refund window?', detail: { needs_review: ['x'] } }] as unknown as EvalItem[];
    render(<JudgeSummary items={items} judge={{
      enabled: true, gating: true, gate: { enabled: true, reason: 'calibrated: agreement lower bound 0.900 >= policy minimum 0.85' }, models: ['a', 'b'],
      panel: { n_pairs: 40, agreement: 0.85, kappa: 0.6, disagreements: 6, same_family: false }, conflicts: ['i1'],
      corrected: { correctness: { n_judged: 40, observed_defect_rate: 0.3, corrected_defect_rate: 0.25, ci_low: 0.1, ci_high: 0.42 } },
    }} />);
    expect(screen.getByTestId('judge-role')).toHaveTextContent('GATING');
    expect(screen.getByTestId('judge-panel')).toHaveTextContent('85.0% over 40 paired verdicts');
    expect(screen.getByTestId('judge-conflicts')).toHaveTextContent(/1 item need human review/);
    expect(screen.getByTestId('judge-corrected')).toHaveTextContent('25.0%');
    expect(screen.getByTestId('judge-corrected')).toHaveTextContent('10.0% to 42.0%');
  });

  it('labels the judge ADVISORY when it does not gate', () => {
    render(<JudgeSummary items={[]} judge={{ enabled: true, gating: false, gate: { enabled: false, reason: 'policy declares no judge_min_agreement: judge is advisory' }, models: ['a'], panel: null, conflicts: [] }} />);
    expect(screen.getByTestId('judge-role')).toHaveTextContent('ADVISORY');
    expect(screen.getByTestId('judge-gate-reason')).toHaveTextContent(/no judge_min_agreement/);
  });

  it('shows per-item claim quotes and a needs-review flag', () => {
    const item = { id: 'i1', detail: {
      judge_gating: false, needs_review: ['faithfulness: conflict on claim'], judge_detail: {
        correctness: { label: 'incorrect', labels: { a: 'incorrect' } },
        faithfulness: { claims: [{ claim: 'Refunds last 90 days.', status: 'contradicted', lexical_ok: false, gated_ok: false, quote: 'Refunds are accepted within 30 days.', judged: true, verifiable: true, judge_disagrees: true }] },
      },
    } } as unknown as EvalItem;
    render(<ItemJudgeDetail item={item} />);
    expect(screen.getByTestId('item-needs-review')).toBeInTheDocument();
    expect(screen.getByText('Refunds are accepted within 30 days.')).toBeInTheDocument();
    expect(screen.getByText('contradicted')).toBeInTheDocument();
    expect(screen.getByText('JUDGE DISAGREES WITH RULES')).toBeInTheDocument();
  });
});
