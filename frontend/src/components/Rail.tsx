import React from 'react';
import type { RunSummary, BenchStatus } from '../types/api';

export const STATE: Record<string, [string, string]> = {
  RELEASE: ['s-release', 'Release'],
  REJECT: ['s-reject', 'Reject'],
  CONDITIONAL: ['s-conditional', 'Conditional release'],
  INSUFFICIENT_EVIDENCE: ['s-insufficient', 'Insufficient evidence'],
};

interface RailProps {
  activeRoute: string;
  runs: RunSummary[];
  benches: BenchStatus[];
  onNavigate: (route: string) => void;
}

export const Rail: React.FC<RailProps> = ({ activeRoute, runs, benches, onNavigate }) => {
  const sidOf = (id: string) => id.split('-')[1];
  const seeded = runs.filter((r) => r.id.startsWith('scn-') && r.variant === 'seeded');

  return (
    <nav className="rail" aria-label="Scenarios">
      <div className="brand">
        qe<small>Release evidence for LLM apps</small>
      </div>

      <button
        className="btn"
        id="new-btn"
        type="button"
        style={{ marginTop: 'var(--space-5)' }}
        aria-current={activeRoute === 'new'}
        onClick={() => onNavigate('new')}
      >
        New scenario
      </button>

      <button
        className="btn btn-quiet"
        id="bench-btn"
        type="button"
        style={{ marginTop: 'var(--space-2)' }}
        aria-current={activeRoute === 'bench'}
        onClick={() => onNavigate('bench')}
      >
        Model benchmark
      </button>

      <h3 className="runs-h">Benchmarks</h3>
      <ul className="run-list" id="bench-list">
        {benches.map((b) => (
          <li key={b.id}>
            <button
              type="button"
              aria-current={activeRoute === b.id}
              onClick={() => onNavigate(b.id)}
            >
              <span className="run-name">{b.id.slice(6)}</span>
              <span className="run-meta">{`${b.state} · ${b.models.length} model(s)`}</span>
            </button>
          </li>
        ))}
        {!benches.length && <li className="empty rail-empty">No benchmarks yet.</li>}
      </ul>

      <h3 className="runs-h">Scenarios</h3>
      <ul className="run-list" id="run-list">
        {seeded.map((r) => {
          const [cls, text] = STATE[r.decision] ?? ['s-insufficient', r.decision];
          const here = activeRoute !== 'new' && sidOf(r.id) === sidOf(activeRoute);
          const appName = r.app.split('-').pop();
          return (
            <li key={r.id}>
              <button
                type="button"
                aria-current={here}
                onClick={() => onNavigate(r.id)}
              >
                <span className="run-name">{`${appName} · ${sidOf(r.id)}`}</span>
                <span className="run-meta">
                  <span className={`chip ${cls}`}>{text}</span> seeded
                </span>
              </button>
            </li>
          );
        })}
        {!seeded.length && <li className="empty rail-empty">No scenarios yet.</li>}
      </ul>

      <label className="sr-only" htmlFor="run-select">
        Scenario
      </label>
      <select
        className="rail-select"
        id="run-select"
        value={activeRoute}
        onChange={(e) => onNavigate(e.target.value)}
      >
        <option value="new">New scenario</option>
        <option value="bench">Model benchmark</option>
        {seeded.map((r) => {
          const [, text] = STATE[r.decision] ?? ['s-insufficient', r.decision];
          const appName = r.app.split('-').pop();
          return (
            <option key={r.id} value={r.id}>
              {`${appName} ${sidOf(r.id)}: ${text}`}
            </option>
          );
        })}
      </select>
    </nav>
  );
};

