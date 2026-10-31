import React, { useState } from 'react';
import type { Report } from '../../types/api';
import { exportToExcel, exportToWordDoc } from '../../utils/reportExporter';

interface TopBarProps {
  report?: Report | null;
  currentRunId?: string;
  onNavigate?: (route: string) => void;
}

export const TopBar: React.FC<TopBarProps> = ({ report, currentRunId, onNavigate }) => {
  const [showExportMenu, setShowExportMenu] = useState(false);
  const isReport = Boolean(report && currentRunId);
  const decision = report?.decision?.decision;
  const isReject = decision === 'REJECT';
  const isRelease = decision === 'RELEASE';
  const isInsufficient = decision === 'INSUFFICIENT_EVIDENCE';

  const sibling = (v: string) => {
    if (!currentRunId) return '';
    return currentRunId.slice(0, currentRunId.lastIndexOf('-') + 1) + v;
  };

  const currentVariant = currentRunId?.slice(currentRunId.lastIndexOf('-') + 1);

  return (
    <header
      style={{
        height: '56px',
        backgroundColor: '#ffffff',
        borderBottom: '1px solid #e2e8f0',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '0 24px',
        position: 'sticky',
        top: 0,
        zIndex: 20,
        flexShrink: 0,
      }}
    >
      {/* Left side: Context & Breadcrumbs */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        <span
          style={{
            fontFamily: 'var(--font-geist)',
            fontSize: '15px',
            fontWeight: 600,
            color: '#0f172a',
          }}
        >
          {isReport
            ? `Execution #${currentRunId}`
            : currentRunId?.startsWith('bench-')
            ? `Benchmark #${currentRunId}`
            : currentRunId === 'bench'
            ? 'Model Benchmark Studio'
            : currentRunId === 'test-llm'
            ? 'Interactive LLM Testing Studio'
            : currentRunId === 'new'
            ? 'New Verification Scenario'
            : 'qe Platform Orchestrator'}
        </span>

        {currentRunId === 'test-llm' && (
          <span className="tag t-ok" style={{ fontSize: '11px' }}>
            User API Probe & Scorecard
          </span>
        )}

        {currentRunId?.startsWith('bench-') && (
          <span className="tag t-sim" style={{ fontSize: '11px' }}>
            Comparative Evaluation
          </span>
        )}

        {isReport && (
          <>
            <div style={{ height: '16px', width: '1px', backgroundColor: '#e2e8f0' }} />

            {/* Variant Switcher Pills */}
            <div style={{ display: 'inline-flex', gap: '4px', background: '#f1f5f9', padding: '2px', borderRadius: '6px' }}>
              <button
                type="button"
                onClick={() => onNavigate && onNavigate(sibling('seeded'))}
                style={{
                  border: 'none',
                  padding: '3px 8px',
                  borderRadius: '4px',
                  fontSize: '11px',
                  fontFamily: 'var(--font-geist)',
                  fontWeight: currentVariant === 'seeded' ? 600 : 500,
                  backgroundColor: currentVariant === 'seeded' ? '#ffffff' : 'transparent',
                  color: currentVariant === 'seeded' ? '#4f46e5' : '#64748b',
                  cursor: 'pointer',
                  boxShadow: currentVariant === 'seeded' ? '0 1px 2px rgba(0,0,0,0.05)' : 'none',
                }}
              >
                Seeded Defect
              </button>
              <button
                type="button"
                onClick={() => onNavigate && onNavigate(sibling('clean'))}
                style={{
                  border: 'none',
                  padding: '3px 8px',
                  borderRadius: '4px',
                  fontSize: '11px',
                  fontFamily: 'var(--font-geist)',
                  fontWeight: currentVariant === 'clean' ? 600 : 500,
                  backgroundColor: currentVariant === 'clean' ? '#ffffff' : 'transparent',
                  color: currentVariant === 'clean' ? '#4f46e5' : '#64748b',
                  cursor: 'pointer',
                  boxShadow: currentVariant === 'clean' ? '0 1px 2px rgba(0,0,0,0.05)' : 'none',
                }}
              >
                Clean Control
              </button>
            </div>

            <span
              className={`tag ${isReject ? 't-bad' : isRelease ? 't-ok' : isInsufficient ? 't-user' : 't-warn'}`}
              style={{ fontSize: '11px' }}
            >
              {decision}
            </span>
          </>
        )}
      </div>

      {/* Right side: Actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', position: 'relative' }}>
        {isReport && report && (
          <>
            {/* Export Report Dropdown Button */}
            <div style={{ position: 'relative' }}>
              <button
                type="button"
                onClick={() => setShowExportMenu(!showExportMenu)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 12px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  backgroundColor: '#ffffff',
                  color: '#1e293b',
                  fontSize: '12px',
                  fontFamily: 'var(--font-geist)',
                  fontWeight: 600,
                  cursor: 'pointer',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                }}
              >
                <span className="material-symbols-outlined" style={{ fontSize: '16px', color: '#4f46e5' }}>
                  ios_share
                </span>
                <span>Export Dossier</span>
                <span className="material-symbols-outlined" style={{ fontSize: '14px', color: '#64748b' }}>
                  expand_more
                </span>
              </button>

              {showExportMenu && (
                <div
                  style={{
                    position: 'absolute',
                    right: 0,
                    top: 'calc(100% + 6px)',
                    width: '260px',
                    backgroundColor: '#ffffff',
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                    boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)',
                    zIndex: 50,
                    padding: '6px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '2px',
                  }}
                >
                  <div style={{ padding: '6px 8px', fontSize: '11px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase' }}>
                    Score & Evidence Formats
                  </div>

                  {/* Word Doc Export */}
                  <button
                    type="button"
                    onClick={() => {
                      exportToWordDoc(report, currentRunId!);
                      setShowExportMenu(false);
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      border: 'none',
                      backgroundColor: 'transparent',
                      textAlign: 'left',
                      cursor: 'pointer',
                      fontSize: '12px',
                      color: '#0f172a',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#f1f5f9')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: '18px', color: '#2563eb' }}>
                      description
                    </span>
                    <div>
                      <div style={{ fontWeight: 600 }}>Word Document (.doc)</div>
                      <div style={{ fontSize: '11px', color: '#64748b' }}>Executive score & evidence narrative</div>
                    </div>
                  </button>

                  {/* Excel CSV Export */}
                  <button
                    type="button"
                    onClick={() => {
                      exportToExcel(report, currentRunId!);
                      setShowExportMenu(false);
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      border: 'none',
                      backgroundColor: 'transparent',
                      textAlign: 'left',
                      cursor: 'pointer',
                      fontSize: '12px',
                      color: '#0f172a',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#f1f5f9')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: '18px', color: '#16a34a' }}>
                      table_view
                    </span>
                    <div>
                      <div style={{ fontWeight: 600 }}>Excel Spreadsheet (.csv)</div>
                      <div style={{ fontSize: '11px', color: '#64748b' }}>Quantitative scorecard & raw tests</div>
                    </div>
                  </button>

                  <div style={{ height: '1px', backgroundColor: '#f1f5f9', margin: '4px 0' }} />

                  {/* JSON Evidence Pack */}
                  <a
                    href={`/api/runs/${encodeURIComponent(currentRunId!)}/pack?fmt=json`}
                    download={`${currentRunId}-pack.json`}
                    onClick={() => setShowExportMenu(false)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      textDecoration: 'none',
                      fontSize: '12px',
                      color: '#0f172a',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#f1f5f9')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: '18px', color: '#7c3aed' }}>
                      data_object
                    </span>
                    <div>
                      <div style={{ fontWeight: 600 }}>Raw Evidence Pack (.json)</div>
                      <div style={{ fontSize: '11px', color: '#64748b' }}>Complete API JSON schema</div>
                    </div>
                  </a>

                  {/* Markdown Pack */}
                  <a
                    href={`/api/runs/${encodeURIComponent(currentRunId!)}/pack?fmt=md`}
                    download={`${currentRunId}-pack.md`}
                    onClick={() => setShowExportMenu(false)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      textDecoration: 'none',
                      fontSize: '12px',
                      color: '#0f172a',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#f1f5f9')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: '18px', color: '#0891b2' }}>
                      markdown
                    </span>
                    <div>
                      <div style={{ fontWeight: 600 }}>Markdown Pack (.md)</div>
                      <div style={{ fontSize: '11px', color: '#64748b' }}>Clean GitHub-flavored text</div>
                    </div>
                  </a>
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={() => onNavigate && onNavigate('new')}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 12px',
                borderRadius: '6px',
                backgroundColor: '#4f46e5',
                color: '#ffffff',
                border: 'none',
                fontSize: '12px',
                fontFamily: 'var(--font-geist)',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: '15px' }}>
                replay
              </span>
              <span>New Run</span>
            </button>
          </>
        )}
      </div>
    </header>
  );
};

