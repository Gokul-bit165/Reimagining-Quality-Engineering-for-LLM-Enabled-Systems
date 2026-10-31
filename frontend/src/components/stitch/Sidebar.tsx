import React from 'react';
import type { RunSummary, BenchStatus } from '../../types/api';

interface SidebarProps {
  activeRoute: string;
  runs: RunSummary[];
  benches: BenchStatus[];
  onNavigate: (route: string) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeRoute,
  runs,
  benches,
  onNavigate,
}) => {
  const sidOf = (id: string) => id.split('-')[1];
  const seeded = runs.filter((r) => r.id.startsWith('scn-') && r.variant === 'seeded');

  return (
    <aside
      style={{
        width: '260px',
        backgroundColor: '#ffffff',
        borderRight: '1px solid #e2e8f0',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        padding: '16px 12px',
        height: '100vh',
        position: 'sticky',
        top: 0,
        zIndex: 30,
        flexShrink: 0,
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {/* Brand Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '0 8px' }}>
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              backgroundColor: '#4f46e5',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#ffffff',
              boxShadow: '0 1px 2px rgba(79, 70, 229, 0.2)',
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: '20px' }}>
              account_tree
            </span>
          </div>
          <div>
            <div
              style={{
                fontFamily: 'var(--font-geist)',
                fontWeight: 700,
                fontSize: '15px',
                color: '#4f46e5',
                letterSpacing: '-0.02em',
              }}
            >
              qe FlowOps
            </div>
            <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>
              LLM Verification Engine
            </div>
          </div>
        </div>

        {/* Primary CTA */}
        <button
          type="button"
          onClick={() => onNavigate('new')}
          style={{
            width: '100%',
            padding: '8px 12px',
            backgroundColor: activeRoute === 'new' ? '#3730a3' : '#4f46e5',
            color: '#ffffff',
            borderRadius: '8px',
            fontSize: '13px',
            fontFamily: 'var(--font-geist)',
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            border: 'none',
            cursor: 'pointer',
            boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
            transition: 'background 120ms ease',
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>
            add
          </span>
          <span>New Scenario</span>
        </button>

        {/* Navigation Section */}
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <button
            type="button"
            onClick={() => onNavigate('bench')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '8px 10px',
              borderRadius: '8px',
              fontSize: '13px',
              fontWeight: activeRoute === 'bench' ? 600 : 500,
              color: activeRoute === 'bench' ? '#4f46e5' : '#475569',
              backgroundColor: activeRoute === 'bench' ? '#eef2ff' : 'transparent',
              border: 'none',
              cursor: 'pointer',
              textAlign: 'left',
              width: '100%',
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
              compare_arrows
            </span>
            <span>Model Benchmarks</span>
          </button>

          <button
            type="button"
            onClick={() => onNavigate('test-llm')}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '8px 10px',
              borderRadius: '8px',
              fontSize: '13px',
              fontWeight: activeRoute === 'test-llm' ? 600 : 500,
              color: activeRoute === 'test-llm' ? '#4f46e5' : '#475569',
              backgroundColor: activeRoute === 'test-llm' ? '#eef2ff' : 'transparent',
              border: 'none',
              cursor: 'pointer',
              textAlign: 'left',
              width: '100%',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                smart_toy
              </span>
              <span>LLM Testing Studio</span>
            </div>
            <span
              style={{
                fontSize: '10px',
                fontWeight: 700,
                backgroundColor: '#eff6ff',
                color: '#2563eb',
                padding: '2px 6px',
                borderRadius: '4px',
                border: '1px solid #bfdbfe',
              }}
            >
              API Input
            </span>
          </button>

          {/* Scenarios Header */}
          <div
            style={{
              fontSize: '11px',
              fontFamily: 'var(--font-geist)',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: '#94a3b8',
              fontWeight: 600,
              padding: '12px 10px 4px',
            }}
          >
            Scenarios ({seeded.length})
          </div>

          <div
            className="custom-scroll"
            style={{
              maxHeight: 'calc(100vh - 420px)',
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: '2px',
            }}
          >
            {seeded.map((r) => {
              const here = activeRoute !== 'new' && sidOf(r.id) === sidOf(activeRoute);
              const appName = r.app.split('-').pop();
              const isReject = r.decision === 'REJECT';
              const isRelease = r.decision === 'RELEASE';

              return (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => onNavigate(r.id)}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    gap: '2px',
                    padding: '8px 10px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    backgroundColor: here ? '#eef2ff' : 'transparent',
                    border: here ? '1px solid #c7d2fe' : '1px solid transparent',
                    cursor: 'pointer',
                    textAlign: 'left',
                    width: '100%',
                    transition: 'all 120ms ease',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      width: '100%',
                    }}
                  >
                    <span
                      style={{
                        fontFamily: 'var(--font-geist)',
                        fontWeight: 600,
                        color: here ? '#4f46e5' : '#1e293b',
                      }}
                    >
                      {`${appName} · ${sidOf(r.id)}`}
                    </span>
                    <span
                      className={`tag ${isReject ? 't-bad' : isRelease ? 't-ok' : 't-user'}`}
                      style={{ fontSize: '10px', padding: '1px 6px' }}
                    >
                      {r.decision}
                    </span>
                  </div>
                  <span style={{ fontSize: '11px', color: '#64748b' }}>
                    {`${r.entries} ledger entries`}
                  </span>
                </button>
              );
            })}
            {!seeded.length && (
              <div style={{ fontSize: '12px', color: '#94a3b8', padding: '8px 10px' }}>
                No scenario runs yet.
              </div>
            )}
          </div>

          {/* Benchmarks Section if any */}
          {benches.length > 0 && (
            <>
              <div
                style={{
                  fontSize: '11px',
                  fontFamily: 'var(--font-geist)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                  color: '#94a3b8',
                  fontWeight: 600,
                  padding: '12px 10px 4px',
                }}
              >
                Benchmarks ({benches.length})
              </div>
              {benches.map((b) => (
                <button
                  key={b.id}
                  type="button"
                  onClick={() => onNavigate(b.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '6px 10px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    backgroundColor: activeRoute === b.id ? '#eef2ff' : 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    width: '100%',
                  }}
                >
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{b.id.slice(6)}</span>
                  <span style={{ fontSize: '10px', color: '#64748b' }}>{b.state}</span>
                </button>
              ))}
            </>
          )}
        </nav>
      </div>

      {/* Footer Cluster Telemetry Widget */}
      <div
        style={{
          padding: '10px 12px',
          borderRadius: '8px',
          backgroundColor: '#eff4ff',
          border: '1px solid #dce9ff',
          display: 'flex',
          flexDirection: 'column',
          gap: '6px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '11px', color: '#475569', fontWeight: 600 }}>
            Offline Deterministic
          </span>
          <span
            style={{
              fontSize: '11px',
              color: '#059669',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: '#10b981',
              }}
            />
            READY
          </span>
        </div>
        <div
          style={{
            width: '100%',
            height: '4px',
            backgroundColor: '#dce9ff',
            borderRadius: '9999px',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              height: '100%',
              width: '100%',
              backgroundColor: '#4f46e5',
              borderRadius: '9999px',
            }}
          />
        </div>
        <span style={{ fontSize: '10px', color: '#64748b', fontFamily: 'var(--font-mono)' }}>
          Sandbox Localhost • Hash-chained
        </span>
      </div>
    </aside>
  );
};

