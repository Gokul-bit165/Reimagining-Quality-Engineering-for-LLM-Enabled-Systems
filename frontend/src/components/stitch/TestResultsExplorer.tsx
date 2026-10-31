import React, { useState, useMemo } from 'react';
import type { Report } from '../../types/api';

interface TestResultsExplorerProps {
  report: Report;
}

export const TestResultsExplorer: React.FC<TestResultsExplorerProps> = ({ report }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'FAILED' | 'PASSED'>('ALL');
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);

  // Map failure details by case_id
  const failuresMap = useMemo(() => {
    const map = new Map<string, any>();
    report.metrics.forEach((m) => {
      m.failures.forEach((f) => {
        map.set(f.case_id, { ...f, metric: m.metric, dimension: m.dimension });
      });
    });
    return map;
  }, [report]);

  // Combine generated tests with evaluation status
  const allTestCases = useMemo(() => {
    return report.generation.tests.map((t) => {
      const failure = failuresMap.get(t.case_id);
      const isFailed = Boolean(failure);
      return {
        id: t.case_id,
        question: t.question,
        expected: t.expected,
        sourceId: t.source_id,
        riskId: t.risk_id,
        family: t.family,
        isFailed,
        status: isFailed ? 'FAILED' : 'PASSED',
        failure,
      };
    });
  }, [report, failuresMap]);

  // Filtered cases
  const filteredCases = useMemo(() => {
    return allTestCases.filter((tc) => {
      const matchesStatus =
        statusFilter === 'ALL' ||
        (statusFilter === 'FAILED' && tc.isFailed) ||
        (statusFilter === 'PASSED' && !tc.isFailed);

      const matchesSearch =
        !searchTerm ||
        tc.question.toLowerCase().includes(searchTerm.toLowerCase()) ||
        tc.expected.toLowerCase().includes(searchTerm.toLowerCase()) ||
        tc.sourceId.toLowerCase().includes(searchTerm.toLowerCase()) ||
        tc.id.toLowerCase().includes(searchTerm.toLowerCase());

      return matchesStatus && matchesSearch;
    });
  }, [allTestCases, statusFilter, searchTerm]);

  const selectedCase = useMemo(() => {
    return allTestCases.find((c) => c.id === selectedCaseId);
  }, [allTestCases, selectedCaseId]);

  const failedCount = allTestCases.filter((c) => c.isFailed).length;
  const passedCount = allTestCases.length - failedCount;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Top Filter and Search Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '16px',
          flexWrap: 'wrap',
          backgroundColor: '#ffffff',
          padding: '12px 16px',
          borderRadius: '10px',
          border: '1px solid #e2e8f0',
          boxShadow: '0 1px 2px rgba(15, 23, 42, 0.03)',
        }}
      >
        {/* Status Filter Tabs */}
        <div style={{ display: 'flex', gap: '4px', backgroundColor: '#f1f5f9', padding: '3px', borderRadius: '8px' }}>
          <button
            type="button"
            onClick={() => setStatusFilter('ALL')}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              border: 'none',
              fontSize: '12px',
              fontFamily: 'var(--font-geist)',
              fontWeight: statusFilter === 'ALL' ? 600 : 500,
              backgroundColor: statusFilter === 'ALL' ? '#ffffff' : 'transparent',
              color: statusFilter === 'ALL' ? '#0f172a' : '#64748b',
              cursor: 'pointer',
              boxShadow: statusFilter === 'ALL' ? '0 1px 2px rgba(0,0,0,0.05)' : 'none',
            }}
          >
            {`All Tests (${allTestCases.length})`}
          </button>
          <button
            type="button"
            onClick={() => setStatusFilter('FAILED')}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              border: 'none',
              fontSize: '12px',
              fontFamily: 'var(--font-geist)',
              fontWeight: statusFilter === 'FAILED' ? 600 : 500,
              backgroundColor: statusFilter === 'FAILED' ? '#ffffff' : 'transparent',
              color: statusFilter === 'FAILED' ? '#e11d48' : '#64748b',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              boxShadow: statusFilter === 'FAILED' ? '0 1px 2px rgba(0,0,0,0.05)' : 'none',
            }}
          >
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#e11d48' }} />
            {`Failed (${failedCount})`}
          </button>
          <button
            type="button"
            onClick={() => setStatusFilter('PASSED')}
            style={{
              padding: '6px 12px',
              borderRadius: '6px',
              border: 'none',
              fontSize: '12px',
              fontFamily: 'var(--font-geist)',
              fontWeight: statusFilter === 'PASSED' ? 600 : 500,
              backgroundColor: statusFilter === 'PASSED' ? '#ffffff' : 'transparent',
              color: statusFilter === 'PASSED' ? '#059669' : '#64748b',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              boxShadow: statusFilter === 'PASSED' ? '0 1px 2px rgba(0,0,0,0.05)' : 'none',
            }}
          >
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#10b981' }} />
            {`Passed (${passedCount})`}
          </button>
        </div>

        {/* Search Input */}
        <div style={{ position: 'relative', minWidth: '280px' }}>
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
            placeholder="Search test prompt, expected, source..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              width: '100%',
              padding: '7px 12px 7px 34px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontSize: '12px',
              outline: 'none',
              backgroundColor: '#f8fafc',
            }}
          />
        </div>
      </div>

      {/* Main Table Layout */}
      <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
        {/* Table Container */}
        <div
          className="tbl-wrap"
          style={{
            flex: 1,
            margin: 0,
            borderRadius: '10px',
            border: '1px solid #e2e8f0',
            backgroundColor: '#ffffff',
            boxShadow: '0 1px 3px rgba(15, 23, 42, 0.04)',
          }}
        >
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: '100px' }}>Status</th>
                <th>Test Prompt / Question</th>
                <th>Expected Source Grounding</th>
                <th style={{ width: '110px' }}>Source Ref</th>
                <th style={{ width: '100px' }}>Risk Target</th>
                <th style={{ width: '80px', textAlign: 'right' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredCases.map((tc) => {
                const isSelected = selectedCaseId === tc.id;
                return (
                  <tr
                    key={tc.id}
                    onClick={() => setSelectedCaseId(tc.id)}
                    style={{
                      cursor: 'pointer',
                      backgroundColor: isSelected ? '#eff4ff' : undefined,
                    }}
                  >
                    <td>
                      <span
                        className={`tag ${tc.isFailed ? 't-bad' : 't-ok'}`}
                        style={{ fontSize: '10px', padding: '2px 8px' }}
                      >
                        {tc.status}
                      </span>
                    </td>
                    <td style={{ fontWeight: 500, color: '#0f172a' }}>{tc.question}</td>
                    <td style={{ color: '#475569', fontSize: '12px' }}>{tc.expected}</td>
                    <td>
                      <code style={{ fontSize: '11px', color: '#4f46e5' }}>{tc.sourceId}</code>
                    </td>
                    <td>
                      <code style={{ fontSize: '11px', color: '#64748b' }}>{tc.riskId}</code>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedCaseId(tc.id);
                        }}
                        style={{
                          border: 'none',
                          background: 'transparent',
                          color: '#4f46e5',
                          fontSize: '11px',
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        Inspect →
                      </button>
                    </td>
                  </tr>
                );
              })}
              {!filteredCases.length && (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '32px', color: '#94a3b8' }}>
                    No test cases match the current filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Selected Test Case Inspector Card (Right Pane) */}
        {selectedCase && (
          <div
            style={{
              width: '380px',
              backgroundColor: '#ffffff',
              borderRadius: '10px',
              border: '1px solid #e2e8f0',
              padding: '16px',
              boxShadow: '0 4px 12px rgba(15, 23, 42, 0.05)',
              display: 'flex',
              flexDirection: 'column',
              gap: '14px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span
                className={`tag ${selectedCase.isFailed ? 't-bad' : 't-ok'}`}
                style={{ fontSize: '11px' }}
              >
                {selectedCase.status}
              </span>
              <button
                type="button"
                onClick={() => setSelectedCaseId(null)}
                style={{
                  border: 'none',
                  backgroundColor: 'transparent',
                  color: '#94a3b8',
                  cursor: 'pointer',
                  padding: '2px',
                }}
              >
                <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                  close
                </span>
              </button>
            </div>

            <div>
              <div style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: '#64748b' }}>
                CASE ID: {selectedCase.id.slice(0, 16)}…
              </div>
              <h4 style={{ margin: '4px 0 0', fontSize: '14px', color: '#0f172a' }}>
                Test Case Inspection
              </h4>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px' }}>
              <div>
                <strong style={{ color: '#475569', display: 'block' }}>Prompt Sent:</strong>
                <div style={{ backgroundColor: '#f8fafc', padding: '8px', borderRadius: '6px', color: '#0f172a' }}>
                  {selectedCase.question}
                </div>
              </div>

              <div>
                <strong style={{ color: '#475569', display: 'block' }}>Ground Truth (Source Expectation):</strong>
                <div style={{ backgroundColor: '#f8fafc', padding: '8px', borderRadius: '6px', color: '#0f172a' }}>
                  {selectedCase.expected}
                </div>
              </div>

              {selectedCase.failure && (
                <>
                  <div>
                    <strong style={{ color: '#e11d48', display: 'block' }}>Observed Sandbox Output:</strong>
                    <div
                      style={{
                        backgroundColor: '#fff1f2',
                        border: '1px solid #fecdd3',
                        padding: '8px',
                        borderRadius: '6px',
                        color: '#9f1239',
                      }}
                    >
                      {selectedCase.failure.output || '(empty / rejected)'}
                    </div>
                  </div>

                  <div>
                    <strong style={{ color: '#475569', display: 'block' }}>Failing Metric & Detail:</strong>
                    <div style={{ color: '#334155', marginTop: '2px' }}>
                      <code>{selectedCase.failure.metric}</code>
                      {selectedCase.failure.detail && ` — ${selectedCase.failure.detail}`}
                    </div>
                  </div>

                  <div>
                    <strong style={{ color: '#475569', display: 'block' }}>Evidence Key:</strong>
                    <code style={{ fontSize: '11px', color: '#64748b', wordBreak: 'break-all' }}>
                      {selectedCase.failure.evidence_key}
                    </code>
                  </div>
                </>
              )}

              <div style={{ paddingTop: '8px', borderTop: '1px solid #f1f5f9', display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>Author Variant:</span>
                <span style={{ fontWeight: 600 }}>{selectedCase.family}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>KB Source:</span>
                <code>{selectedCase.sourceId}</code>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

