import React, { useState, useEffect, useRef } from 'react';
import type { BenchStatus, BenchReport } from '../types/api';
import { api } from '../api';
import { Table } from '../components/Table';
import { MiniBar } from '../components/MiniBar';
import { pct } from '../components/IntervalBar';
import { ProcessingState } from '../components/stitch/ProcessingState';

const METRIC_LABEL: Record<string, string> = {
  faithfulness: 'Faithfulness',
  answer_accuracy: 'Answer accuracy',
  abstention: 'Abstention',
  injection_resistance: 'Injection resistance',
  consistency: 'Consistency',
};

interface BenchViewProps {
  benchId: string;
}

export const BenchView: React.FC<BenchViewProps> = ({ benchId }) => {
  const [status, setStatus] = useState<BenchStatus | null>(null);
  const [report, setReport] = useState<BenchReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'comparison' | 'separability' | 'failures' | 'audit'>('comparison');
  const [searchFilter, setSearchFilter] = useState('');
  const [selectedModelFilter, setSelectedModelFilter] = useState<string>('all');
  const pollTimerRef = useRef<number | null>(null);

  const fetchBench = async () => {
    try {
      const data = await api<{ status: BenchStatus; report: BenchReport | null }>(
        `/api/benchmarks/${encodeURIComponent(benchId)}`
      );
      setStatus(data.status);
      setReport(data.report);
      document.title = `Model benchmark · ${benchId} · qe`;

      if (data.status.state === 'running') {
        pollTimerRef.current = window.setTimeout(fetchBench, 2000);
      }
    } catch (e: any) {
      setError(`Could not load ${benchId}: ${e.message}`);
    }
  };

  useEffect(() => {
    fetchBench();
    return () => {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [benchId]);

  if (error) {
    return (
      <div style={{ padding: '32px 24px', maxWidth: '1200px', margin: '0 auto' }}>
        <div style={{ padding: '16px', backgroundColor: '#fff1f2', border: '1px solid #fecdd3', borderRadius: '8px', color: '#e11d48' }}>
          <strong>Error loading benchmark:</strong> {error}
        </div>
      </div>
    );
  }

  if (!status) {
    return (
      <div style={{ padding: '48px 24px', textAlign: 'center', color: '#64748b' }}>
        <span className="material-symbols-outlined" style={{ fontSize: '32px', animation: 'spin 2s linear infinite', color: '#4f46e5' }}>
          progress_activity
        </span>
        <p style={{ marginTop: '8px', fontSize: '14px' }}>Loading benchmark details…</p>
      </div>
    );
  }

  // Running State: render full SaaS Processing State
  if (status.state === 'running') {
    const benchSteps = [
      { name: '1. Synthesizing multi-style test suite (grounded, false premise, injections)', done: (status.done || 0) >= 2, active: (status.done || 0) < 2 },
      { name: '2. Deterministic reference model invocation', done: (status.done || 0) >= Math.round((status.total || 1) * 0.4), active: (status.done || 0) < Math.round((status.total || 1) * 0.4) && (status.done || 0) >= 2 },
      { name: '3. Real/target model execution with 3-second API pacing', done: (status.done || 0) >= Math.round((status.total || 1) * 0.8), active: (status.done || 0) < Math.round((status.total || 1) * 0.8) && (status.done || 0) >= Math.round((status.total || 1) * 0.4) },
      { name: '4. Computing Clopper-Pearson exact binomial confidence intervals', done: (status.done || 0) >= (status.total || 1), active: (status.done || 0) >= Math.round((status.total || 1) * 0.8) && (status.done || 0) < (status.total || 1) },
      { name: '5. Statistical separability evaluation & overlap checking', done: false, active: (status.done || 0) >= (status.total || 1) },
      { name: '6. Cryptographic block signing on immutable ledger', done: false, active: false },
    ];

    return (
      <div style={{ padding: '32px 24px' }}>
        <ProcessingState
          title={`Executing Benchmark: ${benchId}`}
          subtitle={`Running side-by-side evaluation (${status.done} of ${status.total} test calls completed)`}
          customProgress={status.total > 0 ? Math.round((status.done / status.total) * 100) : 10}
          statusNote={status.note}
          stepsList={benchSteps}
        />
      </div>
    );
  }

  if (status.state === 'error') {
    return (
      <div style={{ padding: '32px 24px', maxWidth: '1200px', margin: '0 auto' }}>
        <div style={{ padding: '20px', backgroundColor: '#fff1f2', border: '1px solid #fecdd3', borderRadius: '8px', color: '#e11d48' }}>
          <h3 style={{ margin: '0 0 8px', fontSize: '16px' }}>Benchmark Failed</h3>
          <p style={{ margin: 0, fontSize: '14px' }}>{status.error || 'An unexpected error occurred during execution.'}</p>
        </div>
      </div>
    );
  }

  if (!report) {
    return null;
  }

  const modelNames = Object.keys(report.models);
  const totalCalls = Object.values(report.models).reduce((acc, m) => acc + m.runs.total, 0);
  const separableCount = report.comparison.reduce((acc, c) => acc + c.separable.length, 0);
  const isSeparable = separableCount > 0;

  // Collect all failing examples across models
  const allFailures: {
    model: string;
    metric: string;
    style: string;
    question: string;
    output: string;
    detail?: string;
  }[] = [];

  Object.entries(report.models).forEach(([modelName, m]) => {
    Object.entries(m.metrics).forEach(([metricKey, metricVal]) => {
      metricVal.examples.forEach((ex) => {
        allFailures.push({
          model: modelName,
          metric: metricKey,
          style: ex.style || 'unspecified',
          question: ex.question || '(no prompt recorded)',
          output: ex.output || '(empty)',
          detail: ex.detail || undefined,
        });
      });
    });
  });

  const filteredFailures = allFailures.filter((f) => {
    const matchesModel = selectedModelFilter === 'all' || f.model === selectedModelFilter;
    const matchesSearch =
      !searchFilter ||
      f.question.toLowerCase().includes(searchFilter.toLowerCase()) ||
      f.output.toLowerCase().includes(searchFilter.toLowerCase()) ||
      (f.detail && f.detail.toLowerCase().includes(searchFilter.toLowerCase())) ||
      f.metric.toLowerCase().includes(searchFilter.toLowerCase());
    return matchesModel && matchesSearch;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflowY: 'auto' }}>
      {/* 1. SaaS KPI Bar for Benchmark */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '12px',
          padding: '16px 24px',
          backgroundColor: '#ffffff',
          borderBottom: '1px solid #e2e8f0',
        }}
      >
        {/* KPI 1: Evaluated Models */}
        <div
          style={{
            backgroundColor: '#eff4ff',
            border: '1px solid #dce9ff',
            borderRadius: '8px',
            padding: '10px 14px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                backgroundColor: '#ffffff',
                border: '1px solid #dce9ff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#4f46e5',
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                compare
              </span>
            </div>
            <div>
              <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>Models Evaluated</div>
              <div style={{ fontFamily: 'var(--font-geist)', fontWeight: 700, fontSize: '15px', color: '#1e293b' }}>
                {`${modelNames.length} Models`}
              </div>
            </div>
          </div>
          <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: '#64748b' }}>
            {`${totalCalls} calls`}
          </span>
        </div>

        {/* KPI 2: Test Suite Composition */}
        <div
          style={{
            backgroundColor: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: '8px',
            padding: '10px 14px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                backgroundColor: '#ffffff',
                border: '1px solid #e2e8f0',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#0284c7',
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                quiz
              </span>
            </div>
            <div>
              <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>Suite Size</div>
              <div style={{ fontFamily: 'var(--font-geist)', fontWeight: 700, fontSize: '15px', color: '#1e293b' }}>
                {`${report.benchmark.n_tests} tests × ${report.benchmark.repeats} reps`}
              </div>
            </div>
          </div>
          <span style={{ fontSize: '11px', color: '#64748b', fontFamily: 'var(--font-mono)' }}>
            {report.benchmark.focus || 'General'}
          </span>
        </div>

        {/* KPI 3: Separability Verdict */}
        <div
          style={{
            backgroundColor: isSeparable ? '#ecfdf5' : '#f8fafc',
            border: `1px solid ${isSeparable ? '#a7f3d0' : '#cbd5e1'}`,
            borderRadius: '8px',
            padding: '10px 14px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                backgroundColor: '#ffffff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: isSeparable ? '#059669' : '#64748b',
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                {isSeparable ? 'insights' : 'flaky'}
              </span>
            </div>
            <div>
              <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>Conclusion</div>
              <div
                style={{
                  fontFamily: 'var(--font-geist)',
                  fontWeight: 700,
                  fontSize: '14px',
                  color: isSeparable ? '#059669' : '#475569',
                }}
              >
                {isSeparable ? `${separableCount} Separable Metrics` : 'Intervals Overlap'}
              </div>
            </div>
          </div>
          <span
            className={`tag ${isSeparable ? 't-ok' : 't-warn'}`}
            style={{ fontSize: '10px', padding: '2px 6px' }}
          >
            {isSeparable ? 'Conclusive' : 'Overlap'}
          </span>
        </div>

        {/* KPI 4: Cryptographic Ledger */}
        <div
          style={{
            backgroundColor: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: '8px',
            padding: '10px 14px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                backgroundColor: '#ffffff',
                border: '1px solid #e2e8f0',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: report.ledger.verified ? '#10b981' : '#f59e0b',
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                lock
              </span>
            </div>
            <div>
              <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>Ledger Hash Chain</div>
              <div style={{ fontFamily: 'var(--font-geist)', fontWeight: 700, fontSize: '14px', color: '#1e293b' }}>
                {report.ledger.verified ? 'Cryptographically Verified' : 'Unverified'}
              </div>
            </div>
          </div>
          <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: '#64748b' }}>
            {`${report.ledger.entries} events`}
          </span>
        </div>
      </div>

      {/* 2. Top Header & Model Chips */}
      <div
        style={{
          padding: '18px 24px',
          backgroundColor: '#ffffff',
          borderBottom: '1px solid #e2e8f0',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              style={{
                fontSize: '11px',
                fontFamily: 'var(--font-mono)',
                color: '#64748b',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              {benchId}
            </span>
            <span className="tag t-ok" style={{ fontSize: '10px' }}>
              Completed
            </span>
            {report.benchmark.focus && (
              <span className="tag t-app" style={{ fontSize: '10px' }}>
                Focus: {report.benchmark.focus}
              </span>
            )}
          </div>
          <h1
            style={{
              margin: '4px 0 0',
              fontFamily: 'var(--font-geist)',
              fontSize: '20px',
              fontWeight: 700,
              color: '#0f172a',
            }}
          >
            Model Benchmark Suite
          </h1>
        </div>

        {/* Model tags */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {Object.entries(report.models).map(([m, v]) => (
            <div
              key={m}
              style={{
                padding: '6px 12px',
                borderRadius: '6px',
                backgroundColor: v.simulated ? '#eff4ff' : '#fffbeb',
                border: `1px solid ${v.simulated ? '#c7d2fe' : '#fde68a'}`,
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '12px',
              }}
            >
              <span
                style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  backgroundColor: v.simulated ? '#4f46e5' : '#d97706',
                }}
              />
              <strong style={{ color: '#0f172a' }}>{m}</strong>
              <span style={{ fontSize: '11px', color: '#64748b' }}>
                ({v.simulated ? 'simulated' : 'real'})
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 3. SaaS Tab Navigation */}
      <div
        style={{
          padding: '0 24px',
          backgroundColor: '#f8fafc',
          borderBottom: '1px solid #e2e8f0',
          display: 'flex',
          gap: '24px',
        }}
      >
        <button
          type="button"
          onClick={() => setActiveTab('comparison')}
          style={{
            padding: '12px 4px',
            fontSize: '13px',
            fontWeight: activeTab === 'comparison' ? 600 : 500,
            color: activeTab === 'comparison' ? '#4f46e5' : '#64748b',
            borderBottom: activeTab === 'comparison' ? '2px solid #4f46e5' : '2px solid transparent',
            background: 'none',
            borderTop: 'none',
            borderLeft: 'none',
            borderRight: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>
            table_chart
          </span>
          Head-to-Head Comparison
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('separability')}
          style={{
            padding: '12px 4px',
            fontSize: '13px',
            fontWeight: activeTab === 'separability' ? 600 : 500,
            color: activeTab === 'separability' ? '#4f46e5' : '#64748b',
            borderBottom: activeTab === 'separability' ? '2px solid #4f46e5' : '2px solid transparent',
            background: 'none',
            borderTop: 'none',
            borderLeft: 'none',
            borderRight: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>
            analytics
          </span>
          Separability & Statistical Conclusions
          {isSeparable && (
            <span
              style={{
                backgroundColor: '#10b981',
                color: '#ffffff',
                borderRadius: '10px',
                padding: '1px 6px',
                fontSize: '10px',
                fontWeight: 700,
              }}
            >
              {separableCount}
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('failures')}
          style={{
            padding: '12px 4px',
            fontSize: '13px',
            fontWeight: activeTab === 'failures' ? 600 : 500,
            color: activeTab === 'failures' ? '#4f46e5' : '#64748b',
            borderBottom: activeTab === 'failures' ? '2px solid #4f46e5' : '2px solid transparent',
            background: 'none',
            borderTop: 'none',
            borderLeft: 'none',
            borderRight: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>
            rule
          </span>
          Failing Test Explorer
          {allFailures.length > 0 && (
            <span
              style={{
                backgroundColor: '#ef4444',
                color: '#ffffff',
                borderRadius: '10px',
                padding: '1px 6px',
                fontSize: '10px',
                fontWeight: 700,
              }}
            >
              {allFailures.length}
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('audit')}
          style={{
            padding: '12px 4px',
            fontSize: '13px',
            fontWeight: activeTab === 'audit' ? 600 : 500,
            color: activeTab === 'audit' ? '#4f46e5' : '#64748b',
            borderBottom: activeTab === 'audit' ? '2px solid #4f46e5' : '2px solid transparent',
            background: 'none',
            borderTop: 'none',
            borderLeft: 'none',
            borderRight: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>
            security
          </span>
          Audit Notes & Ledger
        </button>
      </div>

      {/* 4. Main Body Content Based on Active Tab */}
      <div style={{ padding: '24px', flex: 1, backgroundColor: '#f8fafc' }}>
        {/* TAB 1: Comparison Matrix */}
        {activeTab === 'comparison' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Model Overview Summary Cards */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: `repeat(auto-fit, minmax(300px, 1fr))`,
                gap: '16px',
              }}
            >
              {Object.entries(report.models).map(([name, m]) => (
                <div
                  key={name}
                  style={{
                    backgroundColor: '#ffffff',
                    borderRadius: '10px',
                    border: '1px solid #e2e8f0',
                    padding: '20px',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                    <div>
                      <h3 style={{ margin: '0 0 4px', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
                        {name}
                      </h3>
                      <span className={`tag ${m.simulated ? 't-sim' : 't-warn'}`} style={{ fontSize: '11px' }}>
                        {m.simulated ? 'Deterministic Simulated Reference' : 'Real Model (OpenRouter)'}
                      </span>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: '12px', color: '#64748b' }}>Total Executions</div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: '14px', color: '#0f172a' }}>
                        {`${m.runs.total} calls`}
                      </div>
                    </div>
                  </div>

                  {m.runs.errors > 0 && (
                    <div
                      style={{
                        padding: '8px 12px',
                        backgroundColor: '#fffbeb',
                        border: '1px solid #fde68a',
                        borderRadius: '6px',
                        fontSize: '12px',
                        color: '#92400e',
                        marginBottom: '12px',
                      }}
                    >
                      <strong>{m.runs.errors} calls errored</strong> (no evidence, not counted as test failures):{' '}
                      {m.runs.error_kinds.join('; ')}
                    </div>
                  )}

                  {/* Per-metric breakdown mini summary */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', borderTop: '1px solid #f1f5f9', paddingTop: '12px' }}>
                    {Object.entries(m.metrics).map(([metricKey, cell]) => {
                      const totalTested = cell.failed + cell.passed;
                      const failureRate = totalTested > 0 ? (cell.failed / totalTested) * 100 : 0;
                      return (
                        <div key={metricKey} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
                          <span style={{ color: '#475569', fontWeight: 500 }}>
                            {METRIC_LABEL[metricKey] ?? metricKey}
                          </span>
                          <span style={{ fontFamily: 'var(--font-mono)', color: cell.failed > 0 ? '#ef4444' : '#10b981', fontWeight: 600 }}>
                            {cell.failed > 0 ? `${cell.failed} failed (${failureRate.toFixed(0)}%)` : '0 failures (100% pass)'}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            {/* Comparison Matrix Table Card */}
            <div
              style={{
                backgroundColor: '#ffffff',
                borderRadius: '10px',
                border: '1px solid #e2e8f0',
                boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  padding: '16px 20px',
                  borderBottom: '1px solid #e2e8f0',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <h2 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                    Side-by-Side Metric Evaluation Matrix
                  </h2>
                  <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#64748b' }}>
                    Clopper-Pearson 95% exact binomial intervals shown per model candidate.
                  </p>
                </div>
              </div>

              <div style={{ padding: '8px 16px' }}>
                <Table
                  headers={['Evaluated Metric & Operational Meaning', ...modelNames]}
                  rows={report.comparison.map((c) => [
                    <div style={{ maxWidth: '300px' }}>
                      <strong style={{ color: '#0f172a', fontSize: '13px' }}>
                        {METRIC_LABEL[c.metric] ?? c.metric}
                      </strong>
                      <p style={{ margin: '3px 0 0', fontSize: '11px', color: '#64748b', lineHeight: 1.4 }}>
                        {c.meaning}
                      </p>
                    </div>,
                    ...modelNames.map((m) => {
                      const r = c.cells[m];
                      const cell = report.models[m].metrics[c.metric];
                      if (!r || !cell) {
                        return (
                          <span className="empty" style={{ fontSize: '12px' }}>
                            {cell?.not_evaluable ? 'not evaluable' : 'no evidence'}
                          </span>
                        );
                      }
                      return (
                        <div style={{ minWidth: '160px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <strong style={{ fontSize: '13px', color: cell.failed > 0 ? '#b91c1c' : '#15803d' }}>
                              {`${cell.failed} / ${cell.failed + cell.passed} failed`}
                            </strong>
                            <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: '#64748b' }}>
                              {`${pct(r.lower)} – ${pct(r.upper)}`}
                            </span>
                          </div>
                          <div style={{ marginTop: '4px' }}>
                            <MiniBar rate={r} />
                          </div>
                        </div>
                      );
                    }),
                  ])}
                />
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: Separability & Conclusions */}
        {activeTab === 'separability' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div
              style={{
                backgroundColor: '#ffffff',
                borderRadius: '10px',
                border: '1px solid #e2e8f0',
                padding: '24px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
              }}
            >
              <h2 style={{ margin: '0 0 12px', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
                Statistical Separation Findings
              </h2>

              {isSeparable ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div
                    style={{
                      padding: '12px 16px',
                      backgroundColor: '#ecfdf5',
                      border: '1px solid #a7f3d0',
                      borderRadius: '8px',
                      color: '#065f46',
                      fontSize: '13px',
                      lineHeight: 1.5,
                    }}
                  >
                    <strong>Clear statistical separation observed.</strong> The confidence intervals between the
                    evaluated models do not overlap on the following metrics:
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {report.comparison.flatMap((c) =>
                      c.separable.map((s, i) => (
                        <div
                          key={`${c.metric}-${i}`}
                          style={{
                            padding: '12px 16px',
                            backgroundColor: '#ffffff',
                            border: '1px solid #e2e8f0',
                            borderRadius: '8px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '12px',
                          }}
                        >
                          <span className="material-symbols-outlined" style={{ color: '#059669', fontSize: '20px' }}>
                            verified
                          </span>
                          <div>
                            <strong style={{ color: '#0f172a', fontSize: '14px' }}>
                              {METRIC_LABEL[c.metric] ?? c.metric}
                            </strong>
                            <p style={{ margin: '2px 0 0', fontSize: '13px', color: '#334155' }}>{s}</p>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              ) : (
                <div
                  style={{
                    padding: '16px',
                    backgroundColor: '#fffbeb',
                    border: '1px solid #fde68a',
                    borderRadius: '8px',
                    color: '#92400e',
                    fontSize: '13px',
                    lineHeight: 1.6,
                  }}
                >
                  <p style={{ margin: '0 0 6px', fontWeight: 700, fontSize: '14px' }}>
                    No pair of models is separable on any metric at this sample size.
                  </p>
                  <p style={{ margin: 0 }}>
                    Every confidence interval overlaps. This is <strong>not a tie claim</strong>; it is a limitation of
                    the evidence. To detect smaller performance deltas between these model architectures, run a larger
                    test suite (e.g. 20 tests with 3 repeats).
                  </p>
                </div>
              )}

              {report.benchmark.suite_generator && (
                <div style={{ marginTop: '20px', padding: '12px 16px', backgroundColor: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <div style={{ fontSize: '11px', textTransform: 'uppercase', color: '#64748b', fontWeight: 600 }}>
                    Suite Generation Telemetry
                  </div>
                  <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#334155' }}>
                    Suite contains <strong>{report.benchmark.suite.n} tests</strong> (
                    {Object.entries(report.benchmark.suite.styles)
                      .map(([k, v]) => `${v} ${k}`)
                      .join(', ')}
                    ); generated by <code>{report.benchmark.suite_generator}</code>.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 3: Failing Test Explorer */}
        {activeTab === 'failures' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Search & Model Filter Bar */}
            <div
              style={{
                display: 'flex',
                gap: '12px',
                alignItems: 'center',
                flexWrap: 'wrap',
                backgroundColor: '#ffffff',
                padding: '14px 18px',
                borderRadius: '8px',
                border: '1px solid #e2e8f0',
              }}
            >
              <div style={{ flex: 1, minWidth: '240px', position: 'relative' }}>
                <span
                  className="material-symbols-outlined"
                  style={{
                    position: 'absolute',
                    left: '10px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    fontSize: '18px',
                    color: '#94a3b8',
                  }}
                >
                  search
                </span>
                <input
                  type="text"
                  placeholder="Search failing prompts, outputs, or error details..."
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 12px 8px 36px',
                    fontSize: '13px',
                    border: '1px solid #cbd5e1',
                    borderRadius: '6px',
                    outline: 'none',
                  }}
                />
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <label style={{ fontSize: '12px', color: '#64748b', fontWeight: 600 }}>Filter Model:</label>
                <select
                  value={selectedModelFilter}
                  onChange={(e) => setSelectedModelFilter(e.target.value)}
                  style={{
                    padding: '7px 12px',
                    fontSize: '12px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    backgroundColor: '#ffffff',
                  }}
                >
                  <option value="all">All Models ({allFailures.length})</option>
                  {modelNames.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Failing Test Cases List */}
            {filteredFailures.length === 0 ? (
              <div
                style={{
                  backgroundColor: '#ffffff',
                  borderRadius: '10px',
                  border: '1px solid #e2e8f0',
                  padding: '48px 24px',
                  textAlign: 'center',
                  color: '#64748b',
                }}
              >
                <span className="material-symbols-outlined" style={{ fontSize: '36px', color: '#10b981' }}>
                  check_circle
                </span>
                <h3 style={{ margin: '8px 0 4px', fontSize: '16px', color: '#0f172a' }}>
                  {allFailures.length === 0 ? 'Zero Test Failures' : 'No Matching Failures'}
                </h3>
                <p style={{ margin: 0, fontSize: '13px' }}>
                  {allFailures.length === 0
                    ? 'All evaluated models passed the complete benchmark suite without errors.'
                    : 'No failing tests matched your search and filter criteria.'}
                </p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {filteredFailures.map((f, idx) => (
                  <div
                    key={idx}
                    style={{
                      backgroundColor: '#ffffff',
                      borderRadius: '8px',
                      border: '1px solid #e2e8f0',
                      boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        padding: '12px 16px',
                        backgroundColor: '#fff1f2',
                        borderBottom: '1px solid #fecdd3',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span className="tag t-bad" style={{ fontSize: '11px', fontWeight: 600 }}>
                          {METRIC_LABEL[f.metric] ?? f.metric} Failure
                        </span>
                        <span className="tag t-model" style={{ fontSize: '11px' }}>
                          Model: {f.model}
                        </span>
                        <span className="tag t-app" style={{ fontSize: '11px' }}>
                          Style: {f.style}
                        </span>
                      </div>
                      <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: '#991b1b' }}>
                        Case #{idx + 1}
                      </span>
                    </div>

                    <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {/* Test Prompt */}
                      <div>
                        <div style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>
                          Test Prompt / Input
                        </div>
                        <div
                          style={{
                            marginTop: '4px',
                            padding: '10px 12px',
                            backgroundColor: '#f8fafc',
                            borderRadius: '6px',
                            border: '1px solid #e2e8f0',
                            fontSize: '13px',
                            color: '#0f172a',
                            lineHeight: 1.5,
                          }}
                        >
                          {f.question}
                        </div>
                      </div>

                      {/* Model Raw Output */}
                      <div>
                        <div style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>
                          Model Raw Response
                        </div>
                        <div
                          style={{
                            marginTop: '4px',
                            padding: '10px 12px',
                            backgroundColor: '#ffffff',
                            borderRadius: '6px',
                            border: '1px solid #fed7aa',
                            fontSize: '13px',
                            color: '#9a3412',
                            lineHeight: 1.5,
                            fontFamily: 'var(--font-mono)',
                          }}
                        >
                          {f.output || '(Empty response returned)'}
                        </div>
                      </div>

                      {/* Failure Reason */}
                      {f.detail && (
                        <div>
                          <div style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>
                            Evaluation Reasoning
                          </div>
                          <p style={{ margin: '4px 0 0', fontSize: '12px', color: '#b91c1c' }}>
                            {f.detail}
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 4: Audit Notes & Ledger */}
        {activeTab === 'audit' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div
              style={{
                backgroundColor: '#ffffff',
                borderRadius: '10px',
                border: '1px solid #e2e8f0',
                padding: '24px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
              }}
            >
              <h2 style={{ margin: '0 0 12px', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
                Pre-Release Interpretive Guidelines
              </h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {report.notes.map((t, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '12px 14px',
                      backgroundColor: '#f8fafc',
                      borderRadius: '6px',
                      border: '1px solid #e2e8f0',
                      fontSize: '13px',
                      color: '#334155',
                      lineHeight: 1.5,
                      display: 'flex',
                      gap: '10px',
                      alignItems: 'flex-start',
                    }}
                  >
                    <span className="material-symbols-outlined" style={{ color: '#64748b', fontSize: '18px', marginTop: '2px' }}>
                      info
                    </span>
                    <span>{t}</span>
                  </div>
                ))}
              </div>

              <div
                style={{
                  marginTop: '20px',
                  padding: '16px',
                  backgroundColor: '#f1f5f9',
                  borderRadius: '8px',
                  border: '1px solid #cbd5e1',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <div style={{ fontSize: '11px', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>
                    Cryptographic Ledger Verification
                  </div>
                  <div style={{ marginTop: '2px', fontFamily: 'var(--font-mono)', fontSize: '12px', color: '#1e293b' }}>
                    Head: {report.ledger.head}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <span
                    className={`tag ${report.ledger.verified ? 't-ok' : 't-bad'}`}
                    style={{ fontSize: '12px', fontWeight: 600 }}
                  >
                    {report.ledger.verified ? 'HASH CHAIN VERIFIED' : 'FAILED VERIFICATION'}
                  </span>
                  <div style={{ fontSize: '11px', color: '#64748b', marginTop: '4px' }}>
                    {report.ledger.entries} signed event blocks
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
