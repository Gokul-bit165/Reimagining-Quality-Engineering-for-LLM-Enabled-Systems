import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiDownload, describeError, errorKind, formatDetail } from '../src/api';
import {
  MAX_TARGETS, buildCampaignRequest, buildMetricTable, buildTargetSpec, bundleUrl, campaignsApi, currentStage, describeReportError, describeTarget, emptyTarget,
  explainPair, fmtCost, fmtDiff, fmtDuration, fmtP, fmtRate, fmtSeconds, fmtTokens, groupCasesByScenario, metaToRecord, parseCalibrationText,
  parseEgressHosts, parseJudgeMinAgreement, parseMetaValue, parsePlanFile, reportUrl, stageTone, tailLog, validateAppPath, validateAppPort,
  validateCampaignForm, validateEgressHosts, validateTarget,
} from '../src/lib/campaign';
import { buildPolicy, validateDraft, emptyDraft } from '../src/lib/policy';
import { parseRoute, projectHref, routeTitle } from '../src/lib/route';
import type { Campaign, ComparisonPair, TargetResult } from '../src/types/campaign';

afterEach(() => vi.unstubAllGlobals());

const target = (patch: Partial<ReturnType<typeof emptyTarget>> = {}) => ({ ...emptyTarget('endpoint', 'A'), ...patch });

describe('target validation and spec building', () => {
  it('accepts a bare endpoint target (project endpoint) and rejects a bad label or URL', () => {
    expect(validateTarget(target(), [target()])).toEqual({});
    expect(validateTarget(target({ label: '' }), [target({ label: '' })]).label).toMatch(/label/i);
    expect(validateTarget(target({ label: '-bad' }), [target({ label: '-bad' })]).label).toBeTruthy();
    expect(validateTarget(target({ endpointUrl: 'ftp://x' }), [target()]).endpointUrl).toMatch(/http/);
    expect(validateTarget(target({ endpointUrl: 'nope' }), [target()]).endpointUrl).toBeTruthy();
  });

  it('flags duplicate labels case-insensitively', () => {
    const all = [target({ label: 'Base' }), target({ label: 'base' })];
    expect(validateTarget(all[1], all).label).toMatch(/unique/);
  });

  it('requires model, base URL and a well-formed secret NAME for model targets', () => {
    const t = target({ kind: 'model', label: 'GPT' });
    const e = validateTarget(t, [t]);
    expect(e.model).toBeTruthy();
    expect(e.baseUrl).toBeTruthy();
    expect(validateTarget({ ...t, model: 'm', baseUrl: 'https://api.x.com/v1', apiKeySecret: 'sk-live-abc' }, [t]).apiKeySecret).toMatch(/UPPER_SNAKE/);
    expect(validateTarget({ ...t, model: 'm', baseUrl: 'https://api.x.com/v1', apiKeySecret: 'OPENAI_API_KEY' }, [t])).toEqual({});
  });

  it('builds the spec the backend expects and never adds fields of the other kind', () => {
    expect(buildTargetSpec(target({ meta: [{ key: 'chunk_size', value: '512' }] }))).toEqual({ label: 'A', kind: 'endpoint', metadata: { chunk_size: 512 } });
    const m = buildTargetSpec(target({ kind: 'model', label: 'M', model: 'gpt', baseUrl: 'https://h/v1', apiKeySecret: 'KEY_1', endpointUrl: 'https://ignored' }));
    expect(m).toEqual({ label: 'M', kind: 'model', metadata: {}, model: 'gpt', base_url: 'https://h/v1', api_key_secret: 'KEY_1' });
    expect(describeTarget(m)).toBe('gpt via h');
    expect(describeTarget(buildTargetSpec(target()))).toBe("the project's own endpoint");
  });
});

describe('metadata', () => {
  it('types values: booleans, numbers, text', () => {
    expect(parseMetaValue('true')).toBe(true);
    expect(parseMetaValue(' 12 ')).toBe(12);
    expect(parseMetaValue('0.5')).toBe(0.5);
    expect(parseMetaValue('bm25')).toBe('bm25');
  });
  it('rejects half-filled rows, duplicates and more than 20 entries', () => {
    expect(metaToRecord([{ key: '', value: 'x' }]).error).toMatch(/key/);
    expect(metaToRecord([{ key: 'k', value: '' }]).error).toMatch(/no value/);
    expect(metaToRecord([{ key: 'k', value: '1' }, { key: 'k', value: '2' }]).error).toMatch(/twice/);
    expect(metaToRecord(Array.from({ length: 21 }, (_, i) => ({ key: `k${i}`, value: '1' }))).error).toMatch(/At most 20/);
    expect(metaToRecord([{ key: '', value: '' }]).error).toBeNull();
  });
});

describe('campaign form', () => {
  const base = { name: 'c', targets: [target({ label: 'A' }), target({ label: 'B' })], repeats: 3, maxCases: 50, maxCalls: 2000, planPresent: false };
  it('is valid with two targets and enough calls', () => expect(validateCampaignForm(base)).toEqual([]));
  it('requires a name, a target and enough calls for repeats x targets', () => {
    expect(validateCampaignForm({ ...base, name: ' ' })[0]).toMatch(/name/);
    expect(validateCampaignForm({ ...base, targets: [] })).toContain('Add at least one target.');
    expect(validateCampaignForm({ ...base, maxCalls: 5 }).join()).toMatch(/repeats x targets = 6/);
  });
  it('caps targets at the backend maximum', () => {
    const many = Array.from({ length: MAX_TARGETS + 1 }, (_, i) => target({ label: `T${i}` }));
    expect(validateCampaignForm({ ...base, targets: many }).join()).toMatch(/At most 8/);
  });
  it('sends exactly one of policy / use_example_policy, and the plan only when imported', () => {
    const args = { projectId: 'p1', form: base, riskFocus: ['hallucination'], includeSecurity: true, generate: false };
    const ex = buildCampaignRequest({ ...args, policy: { useExample: true }, plan: null });
    expect(ex.use_example_policy).toBe(true);
    expect(ex).not.toHaveProperty('policy');
    expect(ex).not.toHaveProperty('plan');
    const custom = buildCampaignRequest({ ...args, policy: { useExample: false, policy: { policy_id: 'x' } as never }, plan: { cases: [] } });
    expect(custom).not.toHaveProperty('use_example_policy');
    expect(custom.policy).toEqual({ policy_id: 'x' });
    expect(custom.plan).toEqual({ cases: [] });
    expect(custom.targets).toHaveLength(2);
  });
});

describe('plan import validation', () => {
  const ok = { cases: [{ id: 'c1', question: 'Q?' }, { id: 'c2', question: 'R?' }] };
  it('accepts a valid plan', () => expect(parsePlanFile(JSON.stringify(ok))).toMatchObject({ errors: [], nCases: 2 }));
  it('reports invalid JSON, a missing cases list and a non-object', () => {
    expect(parsePlanFile('{oops').errors[0]).toMatch(/Not valid JSON/);
    expect(parsePlanFile('{"cases":[]}').errors[0]).toMatch(/non-empty/);
    expect(parsePlanFile('[1]').errors[0]).toMatch(/object/);
  });
  it('points at the exact bad case: empty question, duplicate id, security without a probe', () => {
    const r = parsePlanFile(JSON.stringify({ cases: [
      { id: 'a', question: '' }, { id: 'a', question: 'x' }, { id: 's', question: 'y', source: 'security' }, { question: 'z' },
    ] }));
    expect(r.plan).toBeNull();
    expect(r.errors.join('\n')).toMatch(/cases\[0\] has an empty/);
    expect(r.errors.join('\n')).toMatch(/Duplicate case id "a"/);
    expect(r.errors.join('\n')).toMatch(/needs a probe/);
    expect(r.errors.join('\n')).toMatch(/cases\[3\] needs a text "id"/);
  });
  it('refuses more than 500 cases', () => {
    const big = { cases: Array.from({ length: 501 }, (_, i) => ({ id: `i${i}`, question: 'q' })) };
    expect(parsePlanFile(JSON.stringify(big)).errors[0]).toMatch(/at most 500/);
  });
  it('groups cases by scenario in first-seen order', () => {
    const g = groupCasesByScenario([{ scenario: 'b', id: '1' }, { scenario: 'a', id: '2' }, { scenario: 'b', id: '3' }] as never);
    expect(g.map((x) => [x.scenario, x.cases.length])).toEqual([['b', 2], ['a', 1]]);
  });
});

describe('egress and execution settings', () => {
  it('parses separators and lowercases', () => expect(parseEgressHosts('API.openai.com, *.example.com\nfoo.io')).toEqual(['api.openai.com', '*.example.com', 'foo.io']));
  it('accepts DNS names and *.suffix; rejects schemes, ports, paths, IPs, bare words', () => {
    expect(validateEgressHosts(['api.openai.com', '*.example.com'])).toEqual([]);
    for (const bad of ['https://api.openai.com', 'api.openai.com:443', 'api.openai.com/v1', '10.0.0.1', 'localhost', '*', 'a..b.com']) {
      expect(validateEgressHosts([bad]).length, bad).toBe(1);
    }
    expect(validateEgressHosts(Array.from({ length: 21 }, (_, i) => `h${i}.example.com`)).join()).toMatch(/At most 20/);
  });
  it('validates app path and port', () => {
    expect(validateAppPath('')).toBeNull();
    expect(validateAppPath('/ask/v1')).toBeNull();
    expect(validateAppPath('ask')).toBeTruthy();
    expect(validateAppPath('/a b')).toBeTruthy();
    expect(validateAppPort('8000')).toBeNull();
    expect(validateAppPort('0')).toBeTruthy();
    expect(validateAppPort('70000')).toBeTruthy();
    expect(validateAppPort('80a')).toBeTruthy();
  });
  it('keeps the tail of a long log and says how much was hidden', () => {
    const log = Array.from({ length: 300 }, (_, i) => `l${i}`).join('\n');
    const t = tailLog(log, 200);
    expect(t.hidden).toBe(100);
    expect(t.text.startsWith('l100')).toBe(true);
    expect(tailLog('a\nb').hidden).toBe(0);
  });
});

describe('judge calibration input and policy field', () => {
  it('parses JSONL and reports precise row errors', () => {
    const text = [
      '{"question":"q","reference":"30 days","answer":"90 days","label":"incorrect"}',
      '{"answer":"x","label":"great","reference":"r"}',
      '{"answer":"x","label":"correct"}',
      'not json',
    ].join('\n');
    const r = parseCalibrationText(text);
    expect(r.items).toHaveLength(1);
    expect(r.items[0]).toMatchObject({ label: 'incorrect', reference: '30 days' });
    expect(r.errors.join('\n')).toMatch(/line 2: label must be one of/);
    expect(r.errors.join('\n')).toMatch(/line 3: needs a "reference"/);
    expect(r.errors.join('\n')).toMatch(/line 4: not valid JSON/);
  });
  it('parses CSV with a header, faithfulness context and optional kind', () => {
    const csv = 'question,context,answer,label,kind\n"Q","Refunds in 30 days.","30 days",correct,faithfulness\n';
    const r = parseCalibrationText(csv, 'x.csv');
    expect(r.errors).toEqual([]);
    expect(r.items[0]).toMatchObject({ context: 'Refunds in 30 days.', kind: 'faithfulness', label: 'correct' });
    expect(parseCalibrationText('a,b\n1,2', 'x.csv').errors[0]).toMatch(/header row/);
  });
  it('parses a JSON array and rejects empty input', () => {
    expect(parseCalibrationText('[{"answer":"a","label":"correct","reference":"a"}]').items).toHaveLength(1);
    expect(parseCalibrationText('  ').errors[0]).toMatch(/empty/);
  });
  it('parses the optional judge_min_agreement field', () => {
    expect(parseJudgeMinAgreement('')).toEqual({ value: null, error: null });
    expect(parseJudgeMinAgreement('90%')).toEqual({ value: 0.9, error: null });
    expect(parseJudgeMinAgreement('0').error).toBeTruthy();
    expect(parseJudgeMinAgreement('101').error).toBeTruthy();
    expect(parseJudgeMinAgreement('abc').error).toBeTruthy();
  });
  it('puts judge_min_agreement in the policy only when set and valid', () => {
    const metrics = [{ name: 'answer_correctness', description: '' }];
    const draft = { ...emptyDraft(), policyId: 'p', version: '1', required: { answer_correctness: true }, maxPct: { answer_correctness: '10' } };
    expect(buildPolicy(draft, metrics)).not.toHaveProperty('judge_min_agreement');
    expect(buildPolicy({ ...draft, judgeMinPct: '90' }, metrics).judge_min_agreement).toBe(0.9);
    expect(validateDraft({ ...draft, judgeMinPct: 'x' }, metrics, false).judgeMinAgreement).toBeTruthy();
    expect(validateDraft({ ...draft, judgeMinPct: '0' }, metrics, false).judgeMinAgreement).toBeTruthy();
  });
});

describe('formatters', () => {
  it('shows rates with the interval and never a bare number', () => {
    expect(fmtRate({ value: 0.62, ci_low: 0.451, ci_high: 0.763 })).toBe('62.0% (45.1% to 76.3%)');
    expect(fmtRate({ value: null, ci_low: null, ci_high: null })).toBe('not measured');
    expect(fmtRate(undefined)).toBe('not measured');
  });
  it('says "not reported" for missing tokens and cost, never zero', () => {
    expect(fmtTokens(null, 10)).toBe('not reported');
    expect(fmtTokens({ total_tokens: 1200, calls_with_usage: 4 }, 10)).toBe('1,200 tokens in 4 of 10 calls');
    expect(fmtCost(null)).toBe('not reported');
    expect(fmtCost(0.12345)).toBe('$0.1235');
  });
  it('formats seconds, p-values, durations', () => {
    expect(fmtSeconds(0.25)).toBe('250 ms');
    expect(fmtSeconds(2.5)).toBe('2.50 s');
    expect(fmtSeconds(null)).toBe('not measured');
    expect(fmtP(0.0004)).toBe('<0.001');
    expect(fmtP(0.0421)).toBe('0.042');
    expect(fmtP(undefined)).toBe('n/a');
    expect(fmtDuration(100, 100.2)).toBe('<1 s');
    expect(fmtDuration(100, 145)).toBe('45 s');
    expect(fmtDuration(100, 190)).toBe('1 min 30 s');
    expect(fmtDuration(null, null)).toBe('');
  });
  const pair = (p: Partial<ComparisonPair>): ComparisonPair => ({ metric: 'overall_pass_rate', a: 'A', b: 'B', n_pairs: 40, outcome: 'NO_SIGNIFICANT_DIFFERENCE', winner: null, p_value: 0.2, ...p });
  it('explains outcomes in plain language and never claims equality', () => {
    expect(explainPair(pair({}))).toMatch(/absence of evidence, not evidence that they are equal/);
    expect(explainPair(pair({ outcome: 'INSUFFICIENT_EVIDENCE', n_pairs: 4 }))).toMatch(/Only 4 paired questions/);
    expect(explainPair(pair({ outcome: 'B_BETTER', winner: 'B' }))).toMatch(/B did better.*after correcting/);
    expect(explainPair(pair({ outcome: 'NOT_MEASURABLE' }))).toMatch(/No question is measurable/);
  });
  it('formats the paired difference in points with its interval', () => {
    expect(fmtDiff(pair({ diff: 0.125, ci_low: -0.02, ci_high: 0.27 }))).toBe('+12.5 pts (-2.0 to +27.0)');
    expect(fmtDiff(pair({}))).toBe('n/a');
  });
});

describe('metric table and stages', () => {
  const m = (v: number) => ({ value: v, ci_low: v - 0.1, ci_high: v + 0.1, n: 10, n_roots: 10 });
  it('builds one row per metric with one cell per target, keeping gaps as gaps', () => {
    const results = { A: { label: 'A', metrics: { overall_pass_rate: m(0.5) } }, B: { label: 'B', metrics: {} } } as unknown as Record<string, TargetResult>;
    const rows = buildMetricTable(results, ['A', 'B'], ['overall_pass_rate']);
    expect(rows).toHaveLength(1);
    expect(rows[0].cells[0].metric?.value).toBe(0.5);
    expect(rows[0].cells[1].metric).toBeUndefined();
  });
  it('finds the first unfinished stage and maps status to tone', () => {
    const stages = { risk_definition: { status: 'done' }, test_plan: { status: 'done' }, execution: { status: 'running' } } as unknown as Campaign['stages'];
    expect(currentStage({ stages })).toBe('execution');
    expect(stageTone('failed')).toBe('bad');
    expect(stageTone('awaiting_review')).toBe('warn');
    expect(stageTone('pending')).toBe('idle');
  });
});

describe('typed errors and report messages', () => {
  it('classifies statuses', () => {
    expect([0, 403, 404, 409, 413, 422, 500, 418].map(errorKind)).toEqual(['network', 'forbidden', 'not_found', 'conflict', 'too_large', 'invalid', 'server', 'http']);
  });
  it('keeps the backend reason on ApiError and formats object details with missing settings', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { error: 'judge not available', missing: ['QE_JUDGE_MODEL'], notes: ['set it'] } }), { status: 409 })));
    const err = (await campaignsApi.list().catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.kind).toBe('conflict');
    expect(err.detail).toBe('judge not available. missing settings: QE_JUDGE_MODEL. set it');
    expect(describeError(err)).toBe('Conflict (409): judge not available. missing settings: QE_JUDGE_MODEL. set it');
    expect(formatDetail({ error: 'x' })).toBe('x');
  });
  it('describes 413 and 403', () => {
    expect(describeError(new ApiError(413, '413 too big', 'too big'))).toBe('Too large (413): too big');
    expect(describeError(new ApiError(403, '403 no', 'no'))).toBe('Not allowed (403): no');
  });
  it('explains the secret-withheld bundle case and other refusals readably', () => {
    const secret = describeReportError(409, 'a secret value was found in evidence.json: bundle withheld', 'bundle');
    expect(secret).toMatch(/withheld because a secret was found/);
    expect(secret).toMatch(/Nothing was exported/);
    expect(describeReportError(409, 'campaign is running: a report needs a finished run', 'report')).toBe('The report cannot be built yet: campaign is running: a report needs a finished run');
    expect(describeReportError(413, 'evidence bundle exceeds the size cap', 'bundle')).toMatch(/too large to export/);
    expect(describeReportError(404, 'x', 'report')).toMatch(/not found/);
  });
  it('apiDownload returns the filename from content-disposition and throws the reason on 413', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('zipdata', { status: 200, headers: { 'content-disposition': 'attachment; filename="evidence-bundle-cmp-1.zip"', 'content-type': 'application/zip' } })));
    const d = await apiDownload('/x', 'fallback.zip');
    expect(d.filename).toBe('evidence-bundle-cmp-1.zip');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'report exceeds the size cap' }), { status: 413 })));
    await expect(apiDownload('/x', 'f')).rejects.toMatchObject({ status: 413, kind: 'too_large', detail: 'report exceeds the size cap' });
  });
  it('builds report and bundle URLs for both owners', () => {
    expect(reportUrl({ kind: 'evaluation', id: 'eval-1' }, 'md')).toBe('/api/evaluations/eval-1/qa-report?format=md');
    expect(reportUrl({ kind: 'campaign', id: 'cmp-1' }, 'html')).toBe('/api/campaigns/cmp-1/qa-report?format=html');
    expect(bundleUrl({ kind: 'campaign', id: 'cmp-1' })).toBe('/api/campaigns/cmp-1/evidence-bundle');
  });
});

describe('routes for the new areas', () => {
  it('parses the campaign list, a campaign, the form and the judge area', () => {
    expect(parseRoute('#p/p1/campaign')).toEqual({ name: 'project', projectId: 'p1', step: 'campaign', evalId: null, campaignId: null });
    expect(parseRoute('#p/p1/campaign/cmp-abcd1234')).toEqual({ name: 'project', projectId: 'p1', step: 'campaign', evalId: null, campaignId: 'cmp-abcd1234' });
    expect(parseRoute('#p/p1/campaign/new')).toMatchObject({ campaignId: 'new' });
    expect(parseRoute('#p/p1/judge')).toEqual({ name: 'project', projectId: 'p1', step: 'judge', evalId: null });
  });
  it('keeps the six-step wizard routes unchanged', () => {
    expect(parseRoute('#p/p1/results/e1')).toEqual({ name: 'project', projectId: 'p1', step: 'results', evalId: 'e1' });
    expect(parseRoute('#p/p1/unknown')).toMatchObject({ step: 'understand' });
    expect(projectHref('p1', 'campaign', 'cmp-1')).toBe('#p/p1/campaign/cmp-1');
  });
  it('titles the new areas', () => {
    expect(routeTitle({ name: 'project', projectId: 'p1', step: 'campaign', evalId: null, campaignId: 'cmp-1' }, 'https://github.com/a/b')).toBe('a/b · Test campaign cmp-1 · qe');
    expect(routeTitle({ name: 'project', projectId: 'p1', step: 'judge', evalId: null }, null)).toBe('Project · Judge & calibration · qe');
  });
});
