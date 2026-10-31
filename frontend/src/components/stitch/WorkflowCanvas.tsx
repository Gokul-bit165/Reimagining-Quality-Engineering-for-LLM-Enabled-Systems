import React from 'react';
import type { Report } from '../../types/api';

interface WorkflowCanvasProps {
  report: Report;
  selectedStage: number;
  onSelectStage: (stage: number) => void;
}

export const WorkflowCanvas: React.FC<WorkflowCanvasProps> = ({
  report,
  selectedStage,
  onSelectStage,
}) => {
  const isReject = report.decision.decision === 'REJECT';
  const isRelease = report.decision.decision === 'RELEASE';

  const stages = [
    {
      id: 1,
      number: 'STAGE 01',
      title: 'Risk Register',
      icon: 'inventory_2',
      status: 'COMPLETED',
      statusColor: '#059669',
      statusBg: '#ecfdf5',
      desc: `${report.risks.length} risks mapped from OWASP ${report.scenario.taxonomy_id}`,
      meta: `${report.risks.reduce((acc, r) => acc + r.planned_tests, 0)} planned tests`,
    },
    {
      id: 2,
      number: 'STAGE 02',
      title: 'Test Generation',
      icon: 'hub',
      status: 'COMPLETED',
      statusColor: '#059669',
      statusBg: '#ecfdf5',
      desc: `${report.generation.drafted} tests drafted; ${report.generation.rejected_drafts} rejected; ${report.generation.tests.length} validated`,
      meta: `${report.generation.tests.length} tests ready`,
    },
    {
      id: 3,
      number: 'STAGE 03',
      title: 'Sandbox Execution',
      icon: 'terminal',
      status: 'COMPLETED',
      statusColor: '#059669',
      statusBg: '#ecfdf5',
      desc: `${report.scenario.app} (${report.scenario.variant}) • ${report.execution.runs} runs executed`,
      meta: `${report.execution.consistency.identical_across_repeats}/${report.execution.consistency.cases} consistent`,
    },
    {
      id: 4,
      number: 'STAGE 04',
      title: 'Grounding & Attacks',
      icon: 'security',
      status: isReject ? 'BREACHED' : 'EVALUATED',
      statusColor: isReject ? '#e11d48' : '#059669',
      statusBg: isReject ? '#fff1f2' : '#ecfdf5',
      desc: `${report.attacks.rows.length} attack pairs on ${report.scenario.app} sink oracles`,
      meta: `${report.metrics.length} metrics evaluated`,
    },
    {
      id: 5,
      number: 'STAGE 05',
      title: 'Decision & Sign-off',
      icon: 'rule',
      status: report.decision.decision,
      statusColor: isReject ? '#e11d48' : isRelease ? '#059669' : '#d97706',
      statusBg: isReject ? '#fff1f2' : isRelease ? '#ecfdf5' : '#fffbeb',
      desc: `Ledger ${report.ledger.verified ? 'verified' : 'unverified'} • ${report.decision.evidence_ids.length} evidence records`,
      meta: report.human_signoff.length ? `${report.human_signoff.length} signoff(s)` : 'Awaiting signoff',
    },
  ];

  return (
    <div
      className="grid-dots custom-scroll"
      style={{
        flex: 1,
        backgroundColor: '#f8f9ff',
        position: 'relative',
        overflowX: 'auto',
        overflowY: 'auto',
        padding: '32px 24px',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Canvas Toolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '24px',
        }}
      >
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            backgroundColor: '#ffffff',
            border: '1px solid #e2e8f0',
            borderRadius: '8px',
            padding: '4px 10px',
            boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
          }}
        >
          <span style={{ fontSize: '11px', fontFamily: 'var(--font-geist)', color: '#475569', fontWeight: 600 }}>
            DAG Topology: Linear Verification Pipeline • 5 Nodes • 4 Edges
          </span>
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            fontSize: '11px',
            fontFamily: 'var(--font-geist)',
            color: '#64748b',
          }}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: '#10b981' }} />
            Completed / Verified
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: '#e11d48' }} />
            Defect Breached / Reject
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: '#4f46e5' }} />
            Selected Node
          </span>
        </div>
      </div>

      {/* Nodes & Connectors Container */}
      <div
        style={{
          margin: 'auto',
          padding: '24px 8px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minWidth: 'max-content',
        }}
      >
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
          {stages.map((stage, idx) => {
            const isSelected = selectedStage === stage.id;

            return (
              <React.Fragment key={stage.id}>
                {/* Node Card */}
                <div
                  onClick={() => onSelectStage(stage.id)}
                  style={{
                    cursor: 'pointer',
                    width: '240px',
                    borderRadius: '12px',
                    border: isSelected ? '2px solid #4f46e5' : '1px solid #e2e8f0',
                    backgroundColor: '#ffffff',
                    padding: '14px',
                    boxShadow: isSelected
                      ? '0 4px 12px rgba(79, 70, 229, 0.15)'
                      : '0 1px 3px rgba(15, 23, 42, 0.04)',
                    position: 'relative',
                    transition: 'all 120ms ease',
                    transform: isSelected ? 'scale(1.02)' : 'none',
                  }}
                >
                  {/* Inlet Port Anchor */}
                  <div
                    style={{
                      position: 'absolute',
                      left: '-6px',
                      top: '50%',
                      transform: 'translateY(-50%)',
                      width: '10px',
                      height: '10px',
                      borderRadius: '50%',
                      backgroundColor: isSelected ? '#4f46e5' : '#ffffff',
                      border: '2px solid #cbd5e1',
                    }}
                  />

                  {/* Header */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      paddingBottom: '8px',
                      borderBottom: '1px solid #f1f5f9',
                    }}
                  >
                    <span
                      style={{
                        fontSize: '11px',
                        fontFamily: 'var(--font-mono)',
                        color: isSelected ? '#4f46e5' : '#64748b',
                        fontWeight: 600,
                      }}
                    >
                      {stage.number}
                    </span>
                    <span
                      style={{
                        padding: '1px 6px',
                        borderRadius: '4px',
                        fontSize: '10px',
                        fontFamily: 'var(--font-geist)',
                        fontWeight: 600,
                        color: stage.statusColor,
                        backgroundColor: stage.statusBg,
                      }}
                    >
                      {stage.status}
                    </span>
                  </div>

                  {/* Title & Body */}
                  <div style={{ marginTop: '10px' }}>
                    <div
                      style={{
                        fontFamily: 'var(--font-geist)',
                        fontSize: '14px',
                        fontWeight: 600,
                        color: '#0f172a',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                      }}
                    >
                      <span
                        className="material-symbols-outlined"
                        style={{ fontSize: '18px', color: isSelected ? '#4f46e5' : '#64748b' }}
                      >
                        {stage.icon}
                      </span>
                      <span>{stage.title}</span>
                    </div>
                    <p
                      style={{
                        fontSize: '12px',
                        color: '#64748b',
                        margin: '6px 0 0',
                        lineHeight: 1.4,
                      }}
                    >
                      {stage.desc}
                    </p>
                  </div>

                  {/* Footer */}
                  <div
                    style={{
                      marginTop: '12px',
                      paddingTop: '8px',
                      borderTop: '1px solid #f1f5f9',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      fontSize: '11px',
                    }}
                  >
                    <span style={{ color: '#64748b', fontFamily: 'var(--font-mono)' }}>
                      {stage.meta}
                    </span>
                    <span
                      style={{
                        fontFamily: 'var(--font-geist)',
                        fontWeight: 600,
                        color: isSelected ? '#4f46e5' : '#0284c7',
                      }}
                    >
                      {isSelected ? 'Inspecting ⚡' : 'Inspect →'}
                    </span>
                  </div>

                  {/* Outlet Port Anchor */}
                  <div
                    style={{
                      position: 'absolute',
                      right: '-6px',
                      top: '50%',
                      transform: 'translateY(-50%)',
                      width: '10px',
                      height: '10px',
                      borderRadius: '50%',
                      backgroundColor: isSelected ? '#4f46e5' : '#ffffff',
                      border: '2px solid #cbd5e1',
                    }}
                  />
                </div>

                {/* SVG Directional Connector (if not last) */}
                {idx < stages.length - 1 && (
                  <div style={{ width: '48px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <svg width="48" height="24" viewBox="0 0 48 24" fill="none">
                      <path
                        d="M 0 12 L 40 12"
                        stroke={selectedStage === stage.id ? '#4f46e5' : '#94a3b8'}
                        strokeWidth="2"
                        strokeDasharray={selectedStage === stage.id ? '4 3' : 'none'}
                      />
                      <polygon
                        points="40,8 48,12 40,16"
                        fill={selectedStage === stage.id ? '#4f46e5' : '#94a3b8'}
                      />
                    </svg>
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
};

