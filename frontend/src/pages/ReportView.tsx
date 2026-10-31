import React, { useState, useEffect } from 'react';
import type { Report } from '../types/api';
import { api } from '../api';
import { STATE } from '../components/Rail';
import { KPIBar } from '../components/stitch/KPIBar';
import { WorkflowCanvas } from '../components/stitch/WorkflowCanvas';
import { ProcessInspector } from '../components/stitch/ProcessInspector';
import { TestResultsExplorer } from '../components/stitch/TestResultsExplorer';
import { Table } from '../components/Table';
import { MetricRow } from '../components/MetricRow';
import { Facts } from '../components/Facts';
import { pct } from '../components/IntervalBar';
import { exportToExcel, exportToWordDoc } from '../utils/reportExporter';

const ACCESS: Record<string, string> = {
  A: 'black-box',
  B: 'SDK / trace in response',
  C: 'OpenTelemetry traces',
  D: 'repository',
  E: 'gateway',
};

const SURFACE: Record<string, string> = {
  direct_injection: 'direct injection',
  indirect_injection: 'indirect injection',
  rag_poisoning: 'RAG poisoning',
  tool_misuse: 'tool misuse',
  memory_poisoning: 'memory poisoning',
};

interface ReportViewProps {
  runId: string;
  onNavigate: (newId: string) => void;
  onFailuresLoaded: (sourceIds: string[]) => void;
}

export const ReportView: React.FC<ReportViewProps> = ({ runId, onNavigate, onFailuresLoaded }) => {
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Main SaaS Active View Tab
  const [viewTab, setViewTab] = useState<'WORKFLOW' | 'TESTS' | 'SECURITY' | 'SCORECARD' | 'REGRESSION' | 'AUDIT' | 'MONITORING'>('WORKFLOW');

  // Selected DAG Stage
  const [selectedStage, setSelectedStage] = useState<number>(3);

  // Human signoff form
  const [approver, setApprover] = useState<string>('');
  const [signoffNote, setSignoffNote] = useState<string>('');
  const [signoffStatus, setSignoffStatus] = useState<string>('');

  // Monitoring plan
  const [monitoringMarkdown, setMonitoringMarkdown] = useState<string>('');

  const loadReport = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api<Report>(`/api/runs/${encodeURIComponent(runId)}/report`);
      setReport(data);

      const sources = Array.from(
        new Set(data.failures.map((f) => f.source_id).filter(Boolean) as string[])
      );
      onFailuresLoaded(sources);

      document.title = `${(STATE[data.decision.decision] ?? [0, data.decision.decision])[1]} · ${runId} · qe`;
    } catch (err: any) {
      setError(`Could not load ${runId}: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReport();
  }, [runId]);

  useEffect(() => {
    api<{ markdown: string }>('/api/monitoring-plan')
      .then((res) => setMonitoringMarkdown(res.markdown))
      .catch(() => setMonitoringMarkdown('Monitoring plan unavailable.'));
  }, []);

  if (loading) {
    return (
      <div style={{ padding: '32px', color: '#64748b' }}>
        <p className="empty">Loading verification report…</p>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div style={{ padding: '32px' }}>
        <p className="error">{error || 'Report not found'}</p>
      </div>
    );
  }

  const d = report.decision;
  const isReal = report.labels.mode === 'real';

  const handleSignoff = async (approved: boolean) => {
    if (!approver.trim()) {
      setSignoffStatus("Enter the reviewer's name.");
      return;
    }
    try {
      await api(`/api/runs/${encodeURIComponent(runId)}/signoff`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          approver: approver.trim(),
          approved,
          note: signoffNote,
        }),
      });
      setSignoffStatus('Signoff recorded in ledger.');
      loadReport();
    } catch (e: any) {
      setSignoffStatus(`Could not record: ${e.message}`);
    }
  };

  const tabs = [
    { id: 'WORKFLOW', label: 'Workflow & Pipeline', icon: 'account_tree' },
    { id: 'TESTS', label: `All Test Cases (${report.generation.tests.length})`, icon: 'checklist' },
    { id: 'SECURITY', label: `Adversarial Security (${report.attacks.rows.length})`, icon: 'shield' },
    { id: 'SCORECARD', label: 'Scorecard & Policy', icon: 'analytics' },
    { id: 'REGRESSION', label: `Regression Suite (${report.regression.admitted.length})`, icon: 'published_with_changes' },
    { id: 'AUDIT', label: 'Audit & Sign-off', icon: 'verified_user' },
    { id: 'MONITORING', label: 'Monitoring Plan', icon: 'monitoring' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* KPI Overview Bar */}
      <KPIBar report={report} />

      {/* SaaS Secondary Navigation Tab Bar */}
      <div
        className="custom-scroll"
        style={{
          display: 'flex',
          gap: '4px',
          padding: '0 24px',
          backgroundColor: '#ffffff',
          borderBottom: '1px solid #e2e8f0',
          overflowX: 'auto',
          flexShrink: 0,
        }}
      >
        {tabs.map((t) => {
          const isActive = viewTab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setViewTab(t.id as any)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '12px 14px',
                border: 'none',
                borderBottom: isActive ? '2px solid #4f46e5' : '2px solid transparent',
                backgroundColor: 'transparent',
                color: isActive ? '#4f46e5' : '#64748b',
                fontFamily: 'var(--font-geist)',
                fontSize: '13px',
                fontWeight: isActive ? 600 : 500,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                transition: 'all 120ms ease',
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                {t.icon}
              </span>
              <span>{t.label}</span>
            </button>
          );
        })}
      </div>

      {/* Main SaaS Viewport */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* VIEW 1: WORKFLOW & PIPELINE */}
        {viewTab === 'WORKFLOW' && (
          <>
            <div
              className="custom-scroll"
              style={{
                flex: 1,
                overflowY: 'auto',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <WorkflowCanvas
                report={report}
                selectedStage={selectedStage}
                onSelectStage={setSelectedStage}
              />

              <div style={{ padding: '24px 32px 48px', maxWidth: '64rem' }}>
                <h3 style={{ margin: '0 0 12px 0', fontSize: '16px', fontFamily: 'var(--font-geist)', color: '#0f172a' }}>
                  Pipeline Stage Summary
                </h3>
                <Facts
                  rows={[
                    ['Target Application', `${report.scenario.app} (${report.scenario.variant})`],
                    ['Risk Description', report.scenario.text],
                    ['OWASP Classification', report.scenario.taxonomy_id],
                    ['Execution Target', report.labels.target],
                    ['Generation Author', report.labels.generation],
                    ['Policy Appetite', report.labels.policy],
                  ]}
                />
              </div>
            </div>

            <ProcessInspector
              report={report}
              selectedStage={selectedStage}
              onNavigateStage={setSelectedStage}
              onReloadReport={loadReport}
            />
          </>
        )}

        {/* VIEW 2: ALL TEST CASES & RESULTS (Rich SaaS Explorer) */}
        {viewTab === 'TESTS' && (
          <div className="custom-scroll" style={{ flex: 1, overflowY: 'auto', padding: '24px 32px' }}>
            <div style={{ marginBottom: '16px' }}>
              <h2 style={{ margin: 0, fontSize: '18px', fontFamily: 'var(--font-geist)', color: '#0f172a' }}>
                All Generated Test Cases & Evaluation Results
              </h2>
              <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#64748b' }}>
                Inspect each dynamically generated test prompt, verbatim knowledge base citation, and observed sandbox output.
              </p>
            </div>
            <TestResultsExplorer report={report} />
          </div>
        )}

        {/* VIEW 3: ADVERSARIAL SECURITY MATRIX */}
        {viewTab === 'SECURITY' && (
          <div className="custom-scroll" style={{ flex: 1, overflowY: 'auto', padding: '24px 32px', maxWidth: '64rem' }}>
            <div style={{ marginBottom: '20px' }}>
              <h2 style={{ margin: 0, fontSize: '18px', fontFamily: 'var(--font-geist)', color: '#0f172a' }}>
                Adversarial Security & Jailbreak Defense Matrix
              </h2>
              <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#64748b' }}>
                Deterministic sink oracles evaluating prompt injection resistance across 5 attack surfaces.
              </p>
            </div>

            <Table
              headers={['Pair ID', 'Surface', 'Attacker Goal', 'Static Template', 'Adaptive Mutation']}
              rows={report.attacks.rows.map((x) => [
                <code>{x.pair_id}</code>,
                SURFACE[x.surface] ?? x.surface,
                x.goal,
                x.static_template.breached ? (
                  <span className="tag t-bad">{`breached @${x.static_template.first_success}`}</span>
                ) : (
                  <span className="tag t-ok">held</span>
                ),
                x.adaptive_mutation.breached ? (
                  <span className="tag t-bad">{`breached @${x.adaptive_mutation.first_success}`}</span>
                ) : (
                  <span className="tag t-ok">held</span>
                ),
              ])}
            />

            <div style={{ marginTop: '24px' }}>
              <h3 style={{ fontSize: '15px', fontFamily: 'var(--font-geist)', marginBottom: '8px' }}>
                Attack Success Rates (ASR)
              </h3>
              {Object.entries(report.attacks.asr).map(([asCls, v]) => (
                <div key={asCls} className="metric" style={{ marginBottom: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                    <strong style={{ fontFamily: 'var(--font-mono)' }}>{asCls}</strong>
                    <span>{`${v.successes} of ${v.n_pairs} breached within ${report.attacks.budget} attempts`}</span>
                  </div>
                  <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                    {`95% Clopper-Pearson Interval: ${pct(v.lower)} to ${pct(v.upper)}`}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* VIEW 4: SCORECARD & POLICY DECISION */}
        {viewTab === 'SCORECARD' && (
          <div className="custom-scroll" style={{ flex: 1, overflowY: 'auto', padding: '24px 32px', maxWidth: '64rem' }}>
            <div style={{ marginBottom: '20px' }}>
              <h2 style={{ margin: 0, fontSize: '18px', fontFamily: 'var(--font-geist)', color: '#0f172a' }}>
                Quality & Safety Scorecard Against Policy Appetites
              </h2>
              <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#64748b' }}>
                Exact binomial confidence intervals plotted against the policy appetite threshold line (R11).
              </p>
            </div>

            {/* Executive Score & Evidence Explainer Banner */}
            <div
              style={{
                backgroundColor: d.decision === 'REJECT' ? '#fff1f2' : d.decision === 'RELEASE' ? '#ecfdf5' : '#f8fafc',
                border: `1.5px solid ${d.decision === 'REJECT' ? '#fecdd3' : d.decision === 'RELEASE' ? '#a7f3d0' : '#cbd5e1'}`,
                borderRadius: '10px',
                padding: '20px',
                marginBottom: '24px',
                boxShadow: '0 2px 8px rgba(15, 23, 42, 0.04)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                    <span
                      style={{
                        padding: '4px 10px',
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: 700,
                        backgroundColor: d.decision === 'REJECT' ? '#e11d48' : d.decision === 'RELEASE' ? '#059669' : '#475569',
                        color: '#ffffff',
                        letterSpacing: '0.04em',
                      }}
                    >
                      VERDICT: {d.decision}
                    </span>
                    <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 500 }}>
                      Policy v{d.policy_version}
                    </span>
                  </div>
                  <h3 style={{ margin: '0 0 6px', fontSize: '16px', fontWeight: 700, color: '#0f172a' }}>
                    Why this system scored {d.decision}
                  </h3>
                  <p style={{ margin: 0, fontSize: '13px', color: '#334155', lineHeight: 1.5, maxWidth: '42rem' }}>
                    {d.decision === 'REJECT' ? (
                      <>
                        The target system <strong>statistically breached organizational risk appetite bounds</strong>.
                        Clopper-Pearson 95% confidence intervals prove failure rates exceed acceptable safety thresholds.
                        Production release is blocked until defect seeds are eliminated.
                      </>
                    ) : d.decision === 'RELEASE' ? (
                      <>
                        All evaluated risk metrics are <strong>statistically compliant</strong> within established
                        policy appetite lines. No critical jailbreak or hallucination failures were observed.
                      </>
                    ) : (
                      <>
                        Confidence intervals <strong>straddle the risk appetite boundary</strong>. Insufficient test evidence
                        exists to certify conformance with 95% certainty. Additional test cycles are required.
                      </>
                    )}
                  </p>
                </div>

                {/* 1-Click Export Actions */}
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    onClick={() => exportToWordDoc(report, report.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '8px 14px',
                      borderRadius: '6px',
                      backgroundColor: '#2563eb',
                      color: '#ffffff',
                      border: 'none',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      boxShadow: '0 1px 3px rgba(37,99,235,0.2)',
                    }}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>description</span>
                    Export Word Doc (.doc)
                  </button>

                  <button
                    type="button"
                    onClick={() => exportToExcel(report, report.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '8px 14px',
                      borderRadius: '6px',
                      backgroundColor: '#16a34a',
                      color: '#ffffff',
                      border: 'none',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      boxShadow: '0 1px 3px rgba(22,163,74,0.2)',
                    }}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>table_view</span>
                    Export Excel (.csv)
                  </button>
                </div>
              </div>

              {/* Specific Metric Breakdown */}
              <div style={{ marginTop: '16px', paddingTop: '14px', borderTop: '1px solid rgba(0,0,0,0.06)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <span style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', color: '#64748b' }}>
                  Evidence & Appetite Breaches
                </span>
                {report.metrics.map((m) => {
                  const isAbove = m.status === 'above';
                  const isStraddle = m.status === 'straddles';
                  const appStr = m.appetite !== null ? pct(m.appetite) : 'no limit';
                  const rateStr = m.failure_rate ? `${pct(m.failure_rate.point)} [${pct(m.failure_rate.lower)} - ${pct(m.failure_rate.upper)}]` : 'n/a';
                  return (
                    <div
                      key={m.metric}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        fontSize: '12px',
                        padding: '6px 10px',
                        borderRadius: '6px',
                        backgroundColor: isAbove ? '#ffe4e6' : isStraddle ? '#fef3c7' : '#ffffff',
                        border: `1px solid ${isAbove ? '#fecdd3' : isStraddle ? '#fde68a' : '#e2e8f0'}`,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span
                          className="material-symbols-outlined"
                          style={{
                            fontSize: '16px',
                            color: isAbove ? '#e11d48' : isStraddle ? '#d97706' : '#10b981',
                          }}
                        >
                          {isAbove ? 'cancel' : isStraddle ? 'warning' : 'check_circle'}
                        </span>
                        <strong style={{ color: '#0f172a' }}>{m.metric}</strong>
                        <span style={{ color: '#64748b' }}>({m.dimension})</span>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: '#334155' }}>
                          Rate: {rateStr} vs Appetite: <strong>{appStr}</strong>
                        </span>
                        <span
                          className={`tag ${isAbove ? 't-bad' : isStraddle ? 't-warn' : 't-ok'}`}
                          style={{ fontSize: '10px' }}
                        >
                          {isAbove ? 'Breached' : isStraddle ? 'Straddles' : 'Within'}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <Table
              headers={['Dimension', 'Metric', 'Failed / Evaluable', '95% Interval', 'Appetite', 'Verdict']}
              rows={report.metrics.map((m) => {
                const verdictTag =
                  m.status === 'above' ? (
                    <span className="tag t-bad">above appetite</span>
                  ) : m.status === 'within' ? (
                    <span className="tag t-ok">within appetite</span>
                  ) : (
                    <span className="tag t-warn">{m.status ?? 'n/a'}</span>
                  );

                return [
                  m.dimension,
                  <code>{m.metric}</code>,
                  m.failure_rate ? `${m.failure_rate.k} / ${m.failure_rate.n}` : 'n/a',
                  m.failure_rate ? `${pct(m.failure_rate.lower)} to ${pct(m.failure_rate.upper)}` : 'n/a',
                  m.appetite != null ? pct(m.appetite) : 'none',
                  verdictTag,
                ];
              })}
            />

            <div style={{ marginTop: '24px' }}>
              <h3 style={{ fontSize: '15px', fontFamily: 'var(--font-geist)', marginBottom: '8px' }}>
                Detailed Metric Interval Bars
              </h3>
              {report.metrics.map((m) => (
                <MetricRow key={m.metric} metric={m} />
              ))}
            </div>
          </div>
        )}

        {/* VIEW 5: REGRESSION SUITE */}
        {viewTab === 'REGRESSION' && (
          <div className="custom-scroll" style={{ flex: 1, overflowY: 'auto', padding: '24px 32px', maxWidth: '64rem' }}>
            <div style={{ marginBottom: '20px' }}>
              <h2 style={{ margin: 0, fontSize: '18px', fontFamily: 'var(--font-geist)', color: '#0f172a' }}>
                Automated Regression Test Suite
              </h2>
              <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#64748b' }}>
                Failing tests minimized and admitted only if reproducible on defective target and clean on control.
              </p>
            </div>

            {report.scenario.variant === 'clean' ? (
              <p className="empty">
                Regression cases are built from the defective (seeded) version; this is the clean control.
              </p>
            ) : report.regression.admitted.length ? (
              <Table
                headers={['Original Failing Test', 'Minimized Input', 'Metric', 'Reproduction', 'Lineage Steps']}
                rows={report.regression.admitted.map((c) => [
                  c.original_question ?? c.minimized_from,
                  (c.minimized_input.input as string) ?? JSON.stringify(c.minimized_input),
                  <code>{c.metric ?? '-'}</code>,
                  `${c.reproduced[0]} / ${c.reproduced[1]}`,
                  c.lineage.length > 1 ? `${c.lineage.length - 1} steps` : 'none',
                ])}
              />
            ) : (
              <p className="empty">No failures reproduced reliably enough to admit.</p>
            )}

            {report.regression.rejected.length > 0 && (
              <div style={{ marginTop: '20px' }}>
                <h4 style={{ fontSize: '14px', fontFamily: 'var(--font-geist)' }}>Rejected Candidates</h4>
                <ul className="plain" style={{ fontSize: '13px' }}>
                  {report.regression.rejected.map((c, i) => (
                    <li key={i}>{`${c.metric}: ${c.reason}`}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* VIEW 6: AUDIT TRAIL & HUMAN SIGNOFF */}
        {viewTab === 'AUDIT' && (
          <div className="custom-scroll" style={{ flex: 1, overflowY: 'auto', padding: '24px 32px', maxWidth: '56rem' }}>
            <div style={{ marginBottom: '20px' }}>
              <h2 style={{ margin: 0, fontSize: '18px', fontFamily: 'var(--font-geist)', color: '#0f172a' }}>
                Evidence Pack & Human Sign-off Audit Trail
              </h2>
              <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#64748b' }}>
                Immutable SHA-256 hash-chained ledger events and formal human reviewer sign-off.
              </p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '24px' }}>
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '10px', padding: '16px', backgroundColor: '#ffffff' }}>
                <h3 style={{ margin: '0 0 10px 0', fontSize: '14px', fontFamily: 'var(--font-geist)' }}>
                  Ledger Verification
                </h3>
                <Facts
                  rows={[
                    ['Hash Chain', report.ledger.verified ? 'Verified (SHA-256)' : 'FAILED'],
                    ['Entries Count', String(report.ledger.entries)],
                    ['Ledger Head', <code>{report.ledger.head.slice(0, 20)}…</code>],
                  ]}
                />
              </div>

              <div style={{ border: '1px solid #e2e8f0', borderRadius: '10px', padding: '16px', backgroundColor: '#ffffff', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div>
                  <h3 style={{ margin: '0 0 6px 0', fontSize: '14px', fontFamily: 'var(--font-geist)' }}>
                    Download Evidence Pack
                  </h3>
                  <p style={{ margin: 0, fontSize: '12px', color: '#64748b' }}>
                    Byte-identical export directly reconstructed from hash-chained ledger events.
                  </p>
                </div>
                <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
                  <a
                    href={`/api/runs/${encodeURIComponent(report.id)}/pack?fmt=json`}
                    download={`${report.id}-pack.json`}
                    style={{
                      flex: 1,
                      padding: '8px',
                      borderRadius: '6px',
                      border: '1px solid #e2e8f0',
                      backgroundColor: '#f8fafc',
                      color: '#0f172a',
                      fontSize: '12px',
                      fontWeight: 600,
                      textAlign: 'center',
                      textDecoration: 'none',
                    }}
                  >
                    JSON Pack
                  </a>
                  <a
                    href={`/api/runs/${encodeURIComponent(report.id)}/pack?fmt=md`}
                    download={`${report.id}-pack.md`}
                    style={{
                      flex: 1,
                      padding: '8px',
                      borderRadius: '6px',
                      border: '1px solid #e2e8f0',
                      backgroundColor: '#f8fafc',
                      color: '#0f172a',
                      fontSize: '12px',
                      fontWeight: 600,
                      textAlign: 'center',
                      textDecoration: 'none',
                    }}
                  >
                    Markdown
                  </a>
                </div>
              </div>
            </div>

            {/* Human Sign-off Section */}
            <div style={{ border: '1px solid #e2e8f0', borderRadius: '10px', padding: '20px', backgroundColor: '#ffffff' }}>
              <h3 style={{ margin: '0 0 12px 0', fontSize: '15px', fontFamily: 'var(--font-geist)' }}>
                Recorded Reviewer Sign-offs
              </h3>
              {report.human_signoff.length ? (
                <ul className="plain" style={{ fontSize: '13px', marginBottom: '16px' }}>
                  {report.human_signoff.map((s, i) => (
                    <li key={i}>
                      <span className={`tag ${s.approved ? 't-ok' : 't-bad'}`} style={{ marginRight: '8px' }}>
                        {s.approved ? 'Approved' : 'Rejected'}
                      </span>
                      <strong>{s.approver}</strong>
                      {s.note ? ` — "${s.note}"` : ''}
                    </li>
                  ))}
                </ul>
              ) : (
                <p style={{ fontSize: '13px', color: '#64748b', marginBottom: '16px' }}>
                  No human sign-off has been recorded for this execution yet.
                </p>
              )}

              <form onSubmit={(e) => e.preventDefault()} style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxWidth: '30rem' }}>
                <label style={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}>Auditor / Reviewer Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Lead Risk Engineer"
                  value={approver}
                  onChange={(e) => setApprover(e.target.value)}
                  style={{ padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px' }}
                />

                <label style={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}>Sign-off Note</label>
                <input
                  type="text"
                  placeholder="Audit justification or release comment"
                  value={signoffNote}
                  onChange={(e) => setSignoffNote(e.target.value)}
                  style={{ padding: '8px 10px', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '13px' }}
                />

                <div style={{ display: 'flex', gap: '10px', marginTop: '6px' }}>
                  <button
                    type="button"
                    onClick={() => handleSignoff(true)}
                    style={{
                      flex: 1,
                      padding: '8px',
                      borderRadius: '6px',
                      backgroundColor: '#10b981',
                      color: '#ffffff',
                      border: 'none',
                      fontWeight: 600,
                      fontSize: '12px',
                      cursor: 'pointer',
                    }}
                  >
                    Record Approval
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSignoff(false)}
                    style={{
                      flex: 1,
                      padding: '8px',
                      borderRadius: '6px',
                      backgroundColor: '#e11d48',
                      color: '#ffffff',
                      border: 'none',
                      fontWeight: 600,
                      fontSize: '12px',
                      cursor: 'pointer',
                    }}
                  >
                    Record Rejection
                  </button>
                </div>
                {signoffStatus && <p style={{ fontSize: '12px', color: '#4f46e5', margin: '4px 0 0' }}>{signoffStatus}</p>}
              </form>
            </div>
          </div>
        )}

        {/* VIEW 7: MONITORING PLAN */}
        {viewTab === 'MONITORING' && (
          <div className="custom-scroll" style={{ flex: 1, overflowY: 'auto', padding: '24px 32px', maxWidth: '64rem' }}>
            <div style={{ marginBottom: '16px' }}>
              <h2 style={{ margin: 0, fontSize: '18px', fontFamily: 'var(--font-geist)', color: '#0f172a' }}>
                Continuous Post-Release Monitoring Plan
              </h2>
              <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#64748b' }}>
                Recommended trigger policies for drift detection and live production telemetry.
              </p>
            </div>
            <pre className="plan">{monitoringMarkdown}</pre>
          </div>
        )}
      </div>
    </div>
  );
};
