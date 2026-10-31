import { beforeEach, describe, expect, it } from 'vitest';
import { buildPolicy, emptyDraft, hasErrors, loadChoice, parsePercent, saveChoice, validateDraft, SECURITY_METRIC } from '../src/lib/policy';
import type { PolicyDraft } from '../src/lib/policy';

const metrics = [
  { name: 'answer_correctness', description: 'a' }, { name: 'error_rate', description: 'e' }, { name: SECURITY_METRIC, description: 's' },
];

const filled = (): PolicyDraft => ({
  policyId: 'Acme', version: '1',
  required: { answer_correctness: true, [SECURITY_METRIC]: true },
  maxPct: { answer_correctness: '15', [SECURITY_METRIC]: '5.5%' },
});

describe('parsePercent', () => {
  it('accepts 0..100 with optional % and rejects the rest', () => {
    expect(parsePercent('12')).toBe(12);
    expect(parsePercent(' 7.5 % ')).toBe(7.5);
    expect(parsePercent('0')).toBe(0);
    for (const bad of ['', 'abc', '-1', '101', '1,5', '5%%']) expect(parsePercent(bad)).toBeNull();
  });
});

describe('validateDraft', () => {
  it('invents nothing: an empty form is invalid with a reason for each gap', () => {
    const e = validateDraft(emptyDraft(), metrics, true);
    expect(hasErrors(e)).toBe(true);
    expect(e.policyId).toBeTruthy();
    expect(e.version).toBeTruthy();
    expect(e.general.join(' ')).toMatch(/at least one check/i);
  });
  it('requires an appetite for every required check', () => {
    const d = filled();
    d.maxPct = { answer_correctness: '', [SECURITY_METRIC]: 'x' };
    const e = validateDraft(d, metrics, true);
    expect(Object.keys(e.metrics).sort()).toEqual(['answer_correctness', SECURITY_METRIC]);
  });
  it('requires attack resistance while security probes run, and not when they are off', () => {
    const d = filled();
    d.required[SECURITY_METRIC] = false;
    expect(validateDraft(d, metrics, true).general.join(' ')).toMatch(/Attack resistance/);
    expect(hasErrors(validateDraft(d, metrics, false))).toBe(false);
  });
});

describe('buildPolicy', () => {
  it('converts percent to a 0..1 appetite and lists only required checks', () => {
    const p = buildPolicy(filled(), metrics);
    expect(p).toEqual({
      policy_id: 'Acme', version: '1', loss_matrix: {}, required_evidence: ['answer_correctness', SECURITY_METRIC],
      risk_appetite: { answer_correctness: 0.15, [SECURITY_METRIC]: 0.055 }, conditional_rules: [], min_improvement: {},
    });
  });
});

describe('per-project persistence', () => {
  beforeEach(() => window.localStorage.clear());
  it('round-trips a custom draft per project and keeps projects apart', () => {
    saveChoice('p1', { mode: 'custom', draft: filled() });
    expect(loadChoice('p1')).toEqual({ mode: 'custom', draft: filled() });
    expect(loadChoice('p2')).toEqual({ mode: 'unset' });
  });
  it('remembers the explicit example choice and can be cleared', () => {
    saveChoice('p1', { mode: 'example' });
    expect(loadChoice('p1')).toEqual({ mode: 'example' });
    saveChoice('p1', { mode: 'unset' });
    expect(loadChoice('p1')).toEqual({ mode: 'unset' });
  });
  it('treats corrupt storage as unset instead of crashing', () => {
    window.localStorage.setItem('qe.policy.v1:p1', '{not json');
    expect(loadChoice('p1')).toEqual({ mode: 'unset' });
    window.localStorage.setItem('qe.policy.v1:p1', JSON.stringify({ mode: 'custom', draft: { nope: 1 } }));
    expect(loadChoice('p1')).toEqual({ mode: 'unset' });
  });
});
