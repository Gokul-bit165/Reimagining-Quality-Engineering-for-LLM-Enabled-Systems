import React, { useState } from 'react';
import type { Report } from '../../types/api';
import { api } from '../../api';
import { Table } from '../Table';
import { MetricRow } from '../MetricRow';
import { Facts } from '../Facts';
import { exportToExcel, exportToWordDoc } from '../../utils/reportExporter';

interface ProcessInspectorProps {
  report: Report;
  selectedStage: number;
  onNavigateStage: (stage: number) => void;
  onReloadReport: () => void;
}

export const ProcessInspector: React.FC<ProcessInspectorProps> = ({
  report,
  selectedStage,
  onNavigateStage,
  onReloadReport,
}) => {
  const [activeTab, setActiveTab] = useState<'overview' | 'input' | 'execution' | 'output' | 'signoff'>('overview');
  const [approver, setApprover] = useState<string>('');
  const [note, setNote] = useState<string>('');
  const [signoffStatus, setSignoffStatus] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const stageTitles: Record<number, { title: string; subtitle: string }> = {
    1: { title: 'Risk Register & Taxonomy', subtitle: `id: owasp_${(report.scenario.taxonomy_id ?? "unknown").toLowerCase()}` },
    2: { title: 'Dynamic Test Generation', subtitle: 'id: testgen_kb_verbatim_gate' },
    3: { title: 'Sandbox Execution Engine', subtitle: `id: runner_${report.scenario.app}_${report.scenario.variant}` },
    4: { title: 'Grounding & Adversarial Attacks', subtitle: 'id: sink_oracles_asr_eval' },
    5: { title: 'Scorecard & Human Sign-off', subtitle: `id: policy_gate_v${report.decision.policy_version}` },
  };

  const currentInfo = stageTitles[selectedStage] || stageTitles[1];

  const handleSignoff = async (approved: boolean) => {
    if (!approver.trim()) {
      setSignoffStatus("Enter the reviewer's name.");
      return;
    }
    setIsSubmitting(true);
    try {
      await api(`/api/runs/${encodeURIComponent(report.id)}/signoff`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          approver: approver.trim(),
          approved,
          note,
        }),
      });
      setSignoffStatus('Signoff recorded in immutable ledger.');
      onReloadReport();
    } catch (e: any) {
      setSignoffStatus(`Could not record sign-off: ${e.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <aside
      style={{
        width: '440px',
        backgroundColor: '#ffffff',
        borderLeft: '1px solid #e2e8f0',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        boxShadow: '-4px 0 24px rgba(15, 23, 42, 0.05)',
        zIndex: 10,
        flexShrink: 0,
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '16px',
          borderBottom: '1px solid #e2e8f0',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              style={{
                padding: '2px 8px',
                borderRadius: '4px',
                fontSize: '11px',
                fontFamily: 'var(--font-mono)',
                backgroundColor: '#eff4ff',
                color: '#4f46e5',
                fontWeight: 700,
              }}
            >
              {`STAGE 0${selectedStage}`}
            </span>
            <span
              style={{
                padding: '2px 8px',
                borderRadius: '4px',
                fontSize: '11px',
                fontFamily: 'var(--font-geist)',
                backgroundColor: '#ecfdf5',
                color: '#059669',
                fontWeight: 600,
              }}
            >
              EVALUATED
            </span>
          </div>

          {/* Stepper Buttons */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <button
              type="button"
              disabled={selectedStage <= 1}
              onClick={() => onNavigateStage(selectedStage - 1)}
              style={{
                padding: '4px 6px',
                border: '1px solid #e2e8f0',
                borderRadius: '4px',
                backgroundColor: '#ffffff',
                cursor: selectedStage <= 1 ? 'not-allowed' : 'pointer',
                opacity: selectedStage <= 1 ? 0.4 : 1,
                display: 'flex',
                alignItems: 'center',
              }}
              title="Previous Stage"
            >
              <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                chevron_left
              </span>
            </button>
            <button
              type="button"
              disabled={selectedStage >= 5}
              onClick={() => onNavigateStage(selectedStage + 1)}
              style={{
                padding: '4px 6px',
                border: '1px solid #e2e8f0',
                borderRadius: '4px',
                backgroundColor: '#ffffff',
                cursor: selectedStage >= 5 ? 'not-allowed' : 'pointer',
                opacity: selectedStage >= 5 ? 0.4 : 1,
                display: 'flex',
                alignItems: 'center',
              }}
              title="Next Stage"
            >
              <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                chevron_right
              </span>
            </button>
          </div>
        </div>

        <div>
          <h2
            style={{
              margin: 0,
              fontFamily: 'var(--font-geist)',
              fontSize: '16px',
              fontWeight: 700,
              color: '#0f172a',
            }}
          >
            {currentInfo.title}
          </h2>
          <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: '#64748b' }}>
            {currentInfo.subtitle}
          </span>
        </div>
      </div>

      {/* Tabs */}
      <div
        className="custom-scroll"
        style={{
          display: 'flex',
          gap: '8px',
          padding: '0 16px',
          borderBottom: '1px solid #e2e8f0',
          backgroundColor: '#f8fafc',
          overflowX: 'auto',
        }}
      >
        {[
          { key: 'overview', label: 'Overview' },
          { key: 'input', label: 'Input Payload' },
          { key: 'execution', label: 'Execution & Scorecard' },
          { key: 'output', label: 'Evidence & Output' },
          { key: 'signoff', label: 'Signoff & Audit' },
        ].map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key as any)}
            style={{
              padding: '10px 4px',
              fontSize: '12px',
              fontFamily: 'var(--font-geist)',
              fontWeight: activeTab === tab.key ? 600 : 500,
              color: activeTab === tab.key ? '#4f46e5' : '#64748b',
              border: 'none',
              borderBottom: activeTab === tab.key ? '2px solid #4f46e5' : '2px solid transparent',
              backgroundColor: 'transparent',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Drawer Body */}
      <div
        className="custom-scroll"
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
        }}
      >
        {/* TAB 1: OVERVIEW */}
        {activeTab === 'overview' && (
          <>
            <div
              style={{
                backgroundColor: '#f8fafc',
                padding: '12px',
                borderRadius: '8px',
                border: '1px solid #e2e8f0',
              }}
            >
              <div
                style={{
                  fontSize: '11px',
                  fontFamily: 'var(--font-geist)',
                  textTransform: 'uppercase',
                  color: '#64748b',
                  fontWeight: 600,
                  marginBottom: '6px',
                }}
              >
                Verification Objective
              </div>
              <p style={{ margin: 0, fontSize: '13px', lineHeight: 1.5, color: '#334155' }}>
                {selectedStage === 1 &&
                  'Validates risk intent against the OWASP Top 10 for LLMs and plans budget allocations across component attack surfaces.'}
                {selectedStage === 2 &&
                  "Extracts ground-truth statements from target application sources and generates diverse test variations subject to a strict verbatim-evidence gate."}
                {selectedStage === 3 &&
                  `Executes generated test cases against the ${report.scenario.app} sandbox app (${report.scenario.variant}) with repeated evaluations to verify deterministic consistency.`}
                {selectedStage === 4 &&
                  'Checks numeric citations, unsupported assertions, and subjects the sandbox app to multi-turn adversarial prompt injection and poisoning attacks.'}
                {selectedStage === 5 &&
                  'Computes exact statistical confidence intervals per metric, evaluates them against policy appetite thresholds, minimizes regression cases, and enforces human sign-off.'}
              </p>
            </div>

            {/* Context Facts */}
            <div style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px' }}>
              <div
                style={{
                  fontSize: '11px',
                  fontFamily: 'var(--font-geist)',
                  textTransform: 'uppercase',
                  color: '#64748b',
                  fontWeight: 600,
                  marginBottom: '10px',
                }}
              >
                Scenario Context
              </div>
              <Facts
                rows={[
                  ['Target Application', `${report.scenario.app} (${report.scenario.variant})`],
                  ['Risk Scenario', report.scenario.text],
                  ['OWASP Category', report.scenario.taxonomy_id],
                  ['Generation Mode', report.labels.mode],
                  ['Access Level', report.access.visibility_levels.join(', ')],
                ]}
              />
            </div>

            {/* DAG Dependencies */}
            <div style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px' }}>
              <div
                style={{
                  fontSize: '11px',
                  fontFamily: 'var(--font-geist)',
                  textTransform: 'uppercase',
                  color: '#64748b',
                  fontWeight: 600,
                  marginBottom: '8px',
                }}
              >
                DAG Edge Connections
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 10px',
                    borderRadius: '6px',
                    backgroundColor: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    fontSize: '12px',
                  }}
                >
                  <span style={{ color: '#475569' }}>Upstream Prerequisite:</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: '#059669' }}>
                    {selectedStage > 1 ? `STAGE 0${selectedStage - 1} SATISFIED` : 'ROOT INLET'}
                  </span>
                </div>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 10px',
                    borderRadius: '6px',
                    backgroundColor: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    fontSize: '12px',
                  }}
                >
                  <span style={{ color: '#475569' }}>Downstream Outlet:</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: '#4f46e5' }}>
                    {selectedStage < 5 ? `STAGE 0${selectedStage + 1} READY` : 'FINAL VERDICT'}
                  </span>
                </div>
              </div>
            </div>
          </>
        )}

        {/* TAB 2: INPUT PAYLOAD */}
        {activeTab === 'input' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '11px', fontFamily: 'var(--font-geist)', color: '#64748b', fontWeight: 600, textTransform: 'uppercase' }}>
                Scenario Payload
              </span>
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(JSON.stringify(report.scenario, null, 2))}
                style={{
                  fontSize: '11px',
                  color: '#4f46e5',
                  backgroundColor: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <span className="material-symbols-outlined" style={{ fontSize: '14px' }}>
                  content_copy
                </span>
                Copy JSON
              </button>
            </div>
            <pre className="plan">{JSON.stringify(report.scenario, null, 2)}</pre>
          </div>
        )}

        {/* TAB 3: EXECUTION & SCORECARD */}
        {activeTab === 'execution' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {selectedStage === 1 && (
              <>
                <h3 style={{ margin: 0, fontSize: '14px', fontFamily: 'var(--font-geist)' }}>Risk Register</h3>
                <Table
                  headers={['Risk ID', 'Taxonomy', 'Component', 'Planned']}
                  rows={report.risks.map((x) => [
                    <code>{x.risk_id}</code>,
                    x.taxonomy_id,
                    x.component,
                    String(x.planned_tests),
                  ])}
                />
              </>
            )}

            {selectedStage === 2 && (
              <>
                <h3 style={{ margin: 0, fontSize: '14px', fontFamily: 'var(--font-geist)' }}>Generated Tests</h3>
                <Table
                  headers={['Question', 'Source', 'Author']}
                  rows={report.generation.tests.slice(0, 10).map((t) => [
                    t.question,
                    <code>{t.source_id}</code>,
                    t.family,
                  ])}
                />
              </>
            )}

            {selectedStage === 3 && (
              <>
                <h3 style={{ margin: 0, fontSize: '14px', fontFamily: 'var(--font-geist)' }}>Execution Consistency</h3>
                <Facts
                  rows={[
                    ['Total Cases', String(report.execution.cases)],
                    ['Repeats', String(report.execution.repeats)],
                    ['Runs Recorded', String(report.execution.runs)],
                    ['Errors', String(report.execution.errors)],
                    ['Consistency', `${report.execution.consistency.identical_across_repeats}/${report.execution.consistency.cases} identical`],
                  ]}
                />
              </>
            )}

            {selectedStage === 4 && (
              <>
                <h3 style={{ margin: 0, fontSize: '14px', fontFamily: 'var(--font-geist)' }}>Adversarial Attack Pairs</h3>
                <Table
                  headers={['Pair', 'Surface', 'Static', 'Adaptive']}
                  rows={report.attacks.rows.map((r) => [
                    <code>{r.pair_id}</code>,
                    r.surface,
                    r.static_template.breached ? <span className="tag t-bad">breached</span> : <span className="tag t-ok">held</span>,
                    r.adaptive_mutation.breached ? <span className="tag t-bad">breached</span> : <span className="tag t-ok">held</span>,
                  ])}
                />
              </>
            )}

            {selectedStage === 5 && (
              <>
                <h3 style={{ margin: 0, fontSize: '14px', fontFamily: 'var(--font-geist)' }}>Metric Scorecard Intervals</h3>
                {report.metrics.map((m) => (
                  <MetricRow key={m.metric} metric={m} />
                ))}
              </>
            )}
          </div>
        )}

        {/* TAB 4: OUTPUT / EVIDENCE */}
        {activeTab === 'output' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px' }}>
              <div style={{ fontSize: '11px', fontFamily: 'var(--font-geist)', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', marginBottom: '8px' }}>
                Ledger Chain Integrity
              </div>
              <Facts
                rows={[
                  ['Hash Chain Status', report.ledger.verified ? 'Verified (SHA-256)' : 'FAILED'],
                  ['Total Ledger Entries', String(report.ledger.entries)],
                  ['Current Head', <code>{report.ledger.head.slice(0, 24)}…</code>],
                ]}
              />
            </div>

            {/* Executive Report Outputs */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ fontSize: '11px', fontFamily: 'var(--font-geist)', color: '#64748b', fontWeight: 600, textTransform: 'uppercase' }}>
                Executive Report Outputs (Score & Evidence)
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                <button
                  type="button"
                  onClick={() => exportToWordDoc(report, report.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px',
                    padding: '8px 10px',
                    borderRadius: '6px',
                    backgroundColor: '#eff6ff',
                    border: '1px solid #bfdbfe',
                    color: '#1d4ed8',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>description</span>
                  Word Doc (.doc)
                </button>
                <button
                  type="button"
                  onClick={() => exportToExcel(report, report.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px',
                    padding: '8px 10px',
                    borderRadius: '6px',
                    backgroundColor: '#f0fdf4',
                    border: '1px solid #bbf7d0',
                    color: '#15803d',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>table_view</span>
                  Excel Sheet (.csv)
                </button>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <a
                href={`/api/runs/${encodeURIComponent(report.id)}/pack?fmt=json`}
                download={`${report.id}-pack.json`}
                style={{
                  flex: 1,
                  padding: '8px 12px',
                  borderRadius: '6px',
                  backgroundColor: '#ffffff',
                  border: '1px solid #e2e8f0',
                  color: '#1e293b',
                  fontSize: '12px',
                  fontFamily: 'var(--font-geist)',
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
                  padding: '8px 12px',
                  borderRadius: '6px',
                  backgroundColor: '#ffffff',
                  border: '1px solid #e2e8f0',
                  color: '#1e293b',
                  fontSize: '12px',
                  fontFamily: 'var(--font-geist)',
                  fontWeight: 600,
                  textAlign: 'center',
                  textDecoration: 'none',
                }}
              >
                Markdown Pack
              </a>
            </div>

            {report.regression.admitted.length > 0 && (
              <>
                <h4 style={{ margin: '8px 0 0', fontSize: '13px', fontFamily: 'var(--font-geist)' }}>Admitted Regression Tests</h4>
                <Table
                  headers={['Case', 'Metric', 'Reproduced']}
                  rows={report.regression.admitted.map((c) => [
                    <code>{c.case_id.slice(0, 8)}</code>,
                    c.metric ?? '-',
                    `${c.reproduced[0]}/${c.reproduced[1]}`,
                  ])}
                />
              </>
            )}
          </div>
        )}

        {/* TAB 5: SIGNOFF & AUDIT */}
        {activeTab === 'signoff' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px' }}>
              <div style={{ fontSize: '11px', fontFamily: 'var(--font-geist)', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', marginBottom: '8px' }}>
                Recorded Sign-offs
              </div>
              {report.human_signoff.length > 0 ? (
                <ul className="plain" style={{ paddingLeft: '16px', margin: 0, fontSize: '12px' }}>
                  {report.human_signoff.map((s, i) => (
                    <li key={i}>
                      <strong>{s.approved ? 'Approved' : 'Rejected'}</strong> by {s.approver}
                      {s.note ? `: ${s.note}` : ''}
                    </li>
                  ))}
                </ul>
              ) : (
                <p style={{ margin: 0, fontSize: '12px', color: '#64748b' }}>
                  No human sign-off recorded yet. Critical decisions require approval.
                </p>
              )}
            </div>

            {/* Signoff Form */}
            <form
              onSubmit={(e) => e.preventDefault()}
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '10px',
                padding: '12px',
                borderRadius: '8px',
                backgroundColor: '#f8fafc',
                border: '1px solid #e2e8f0',
              }}
            >
              <label style={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}>Reviewer Name</label>
              <input
                type="text"
                required
                maxLength={80}
                placeholder="e.g. Lead Risk Engineer"
                value={approver}
                onChange={(e) => setApprover(e.target.value)}
                style={{
                  padding: '8px 10px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  fontSize: '13px',
                }}
              />

              <label style={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}>Review Note</label>
              <input
                type="text"
                maxLength={500}
                placeholder="Optional audit rationale"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                style={{
                  padding: '8px 10px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  fontSize: '13px',
                }}
              />

              <div style={{ display: 'flex', gap: '8px', marginTop: '6px' }}>
                <button
                  type="button"
                  disabled={isSubmitting}
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
                  disabled={isSubmitting}
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

              {signoffStatus && (
                <p style={{ margin: '4px 0 0', fontSize: '12px', color: '#4f46e5', fontWeight: 500 }}>
                  {signoffStatus}
                </p>
              )}
            </form>
          </div>
        )}
      </div>
    </aside>
  );
};

