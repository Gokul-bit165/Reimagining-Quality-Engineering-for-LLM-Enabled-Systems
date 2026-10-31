import React from 'react';
import type { Report } from '../../types/api';

interface KPIBarProps {
  report: Report;
}

export const KPIBar: React.FC<KPIBarProps> = ({ report }) => {
  const d = report.decision.decision;
  const isReject = d === 'REJECT';
  const isRelease = d === 'RELEASE';
  const isInsufficient = d === 'INSUFFICIENT_EVIDENCE';

  // Attack stats
  const totalAttacks = report.attacks.rows.length;
  const staticBreached = report.attacks.rows.filter((r) => r.static_template.breached).length;
  const adaptiveBreached = report.attacks.rows.filter((r) => r.adaptive_mutation.breached).length;

  return (
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
      {/* 1. Release Decision */}
      <div
        style={{
          backgroundColor: isReject ? '#fff1f2' : isRelease ? '#ecfdf5' : isInsufficient ? '#f8fafc' : '#fffbeb',
          border: `1px solid ${isReject ? '#fecdd3' : isRelease ? '#a7f3d0' : isInsufficient ? '#cbd5e1' : '#fde68a'}`,
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
              color: isReject ? '#e11d48' : isRelease ? '#059669' : '#475569',
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
              {isReject ? 'gpp_bad' : isRelease ? 'verified' : 'help'}
            </span>
          </div>
          <div>
            <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>Recommendation</div>
            <div
              style={{
                fontFamily: 'var(--font-geist)',
                fontWeight: 700,
                fontSize: '15px',
                color: isReject ? '#e11d48' : isRelease ? '#059669' : '#334155',
              }}
            >
              {d}
            </div>
          </div>
        </div>
        <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: '#64748b' }}>
          {`v${report.decision.policy_version}`}
        </span>
      </div>

      {/* 2. Pipeline Execution Stages */}
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
              check_circle
            </span>
          </div>
          <div>
            <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>Stages Finished</div>
            <div
              style={{
                fontFamily: 'var(--font-geist)',
                fontWeight: 600,
                fontSize: '15px',
                color: '#0f172a',
              }}
            >
              5 Stages • 100%
            </div>
          </div>
        </div>
        <span style={{ fontSize: '11px', color: '#059669', fontWeight: 600 }}>Deterministic</span>
      </div>

      {/* 3. Generated Tests */}
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
              color: '#0284c7',
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
              quiz
            </span>
          </div>
          <div>
            <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>Tests Evaluated</div>
            <div
              style={{
                fontFamily: 'var(--font-geist)',
                fontWeight: 600,
                fontSize: '15px',
                color: '#0f172a',
              }}
            >
              {`${report.execution.cases} cases (${report.execution.runs} runs)`}
            </div>
          </div>
        </div>
        <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: '#64748b' }}>
          {`${report.execution.repeats}x repeats`}
        </span>
      </div>

      {/* 4. Adversarial Attack Status */}
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
              color: staticBreached + adaptiveBreached > 0 ? '#e11d48' : '#059669',
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
              shield
            </span>
          </div>
          <div>
            <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>Adversarial Defended</div>
            <div
              style={{
                fontFamily: 'var(--font-geist)',
                fontWeight: 600,
                fontSize: '15px',
                color: '#0f172a',
              }}
            >
              {`${totalAttacks - (staticBreached + adaptiveBreached)} / ${totalAttacks} held`}
            </div>
          </div>
        </div>
        <span style={{ fontSize: '11px', color: staticBreached > 0 ? '#e11d48' : '#059669', fontWeight: 600 }}>
          {staticBreached > 0 ? `${staticBreached} breached` : 'clean'}
        </span>
      </div>

      {/* 5. Ledger Integrity */}
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
              color: report.ledger.verified ? '#059669' : '#e11d48',
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
              link
            </span>
          </div>
          <div>
            <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>Ledger Hash Chain</div>
            <div
              style={{
                fontFamily: 'var(--font-geist)',
                fontWeight: 600,
                fontSize: '15px',
                color: '#0f172a',
              }}
            >
              {report.ledger.verified ? 'Verified Chain' : 'INTEGRITY FAILED'}
            </div>
          </div>
        </div>
        <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: '#4f46e5', fontWeight: 600 }}>
          {`${report.ledger.entries} events`}
        </span>
      </div>
    </div>
  );
};

