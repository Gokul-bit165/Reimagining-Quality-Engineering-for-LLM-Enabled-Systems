import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { endpointHost, isLoopbackEndpoint, sourceLabel } from '../src/lib/provenance';
import { routeTitle } from '../src/lib/route';
import { PlanSummary, OperateStep } from '../src/pages/project/OperateStep';
import type { Evaluation, Project } from '../src/types/api';

describe('provenance', () => {
  it('detects loopback endpoints', () => {
    for (const u of ['http://localhost:9100/ask', 'http://127.0.0.1:8000', 'http://127.5.5.5/x', 'http://[::1]:80/', 'http://0.0.0.0:1']) expect(isLoopbackEndpoint(u)).toBe(true);
    for (const u of ['https://staging.example.com/ask', 'http://10.0.0.4/', 'http://localhost.evil.com/', null, '']) expect(isLoopbackEndpoint(u)).toBe(false);
  });
  it('extracts the host', () => {
    expect(endpointHost('https://a.example.com:8443/x')).toBe('a.example.com:8443');
    expect(endpointHost('nope')).toBeNull();
  });
  it('labels sources', () => {
    expect(sourceLabel('generated')).toBe('Generated from your docs');
    expect(sourceLabel('other')).toBe('other');
  });
});

describe('routeTitle', () => {
  it('titles each route', () => {
    expect(routeTitle({ name: 'connect' }, null)).toBe('Connect · qe');
    expect(routeTitle({ name: 'project', projectId: 'p1', step: 'results', evalId: null }, 'https://github.com/acme/rag')).toBe('acme/rag · Results · qe');
  });
});

describe('PlanSummary', () => {
  it('renders readable text and hides ids and markdown', () => {
    render(<PlanSummary onDownload={vi.fn()} plan={{
      evaluation_id: 'EVAL-SECRET-ID', project_id: 'PRJ-SECRET', rerun: { failed_items: ['a', 'b'], security_probes: ['s'], regression_suite: 'GET /x' },
      cadence_days: null, drift_triggers: ['model_change'], thresholds: { grounding: { max_failure_rate: 0.1, example: true } },
      alert_rule: 'alert when over', status: 'a plan, not a running system', markdown: '# BIG MARKDOWN',
    }} />);
    expect(screen.getByText(/2 failed question/)).toBeInTheDocument();
    expect(screen.getByText(/model change/)).toBeInTheDocument();
    expect(screen.getByText(/at most 10.0%/)).toBeInTheDocument();
    expect(screen.queryByText(/EVAL-SECRET-ID|PRJ-SECRET|BIG MARKDOWN/)).toBeNull();
    expect(screen.getByRole('button', { name: /Download full plan/ })).toBeInTheDocument();
  });
});

describe('OperateStep', () => {
  it('preselects no failures and shows the source of each', () => {
    const ev = { id: 'e1', project_id: 'p1', state: 'done', progress: { done: 2, total: 2 }, error: null, metrics: {}, decision: null,
      items: [
        { id: 'i1', question: 'Q1', reference_answer: null, answer: null, contexts: [], scores: {}, passed: false, failure_reason: null, source: 'security' },
        { id: 'i2', question: 'Q2', reference_answer: null, answer: null, contexts: [], scores: {}, passed: false, failure_reason: null, source: 'user' },
      ] } as Evaluation;
    render(<OperateStep project={{ id: 'p1' } as Project} evaluation={ev} />);
    expect(screen.getAllByRole('checkbox').every((c) => !(c as HTMLInputElement).checked)).toBe(true);
    expect(screen.getByTestId('add-regression')).toBeDisabled();
    expect(screen.getByText('Security probe')).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    expect(screen.getByTestId('add-regression')).toBeEnabled();
  });
});
