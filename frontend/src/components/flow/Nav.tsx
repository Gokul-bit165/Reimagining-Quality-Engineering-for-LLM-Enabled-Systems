import React from 'react';
import type { BenchStatus, Project, RunSummary } from '../../types/api';
import { projectHref, type Route } from '../../lib/route';

interface NavProps {
  route: Route;
  open: boolean;
  projects: Project[];
  runs: RunSummary[];
  benches: BenchStatus[];
  onClose: () => void;
}

/** Repo name plus sub-folder and a short id so two projects of one repo stay distinguishable. */
export function projectLabel(p: Project): string {
  const repo = p.repo_url.replace(/^https:\/\/github\.com\/[^/]+\//, '');
  const sub = p.subdir ? ` / ${p.subdir}` : '';
  return `${repo.length > 28 ? `${repo.slice(0, 26)}…` : repo}${sub} · ${p.id.slice(-4)}`;
}

const go = (hash: string, close: () => void) => { window.location.hash = hash; close(); };

export const Nav: React.FC<NavProps> = ({ route, open, projects, runs, benches, onClose }) => {
  const legacyId = route.name === 'legacy' ? route.id : '';
  const cur = (on: boolean) => (on ? ('page' as const) : undefined);
  const pastOpen = legacyId !== '' && !['new', 'bench', 'test-llm'].includes(legacyId);
  const scenarioRuns = runs.filter((r) => r.id.startsWith('scn-') && r.variant === 'seeded');
  return (
    <>
      {open && <button type="button" className="scrim" aria-label="Close navigation" onClick={onClose} />}
      <aside className="sidenav" data-open={open} aria-label="Primary" id="primary-nav">
        <div className="sidenav__brand">
          <div className="sidenav__logo"><span className="material-symbols-outlined" aria-hidden="true">account_tree</span></div>
          <div><div className="sidenav__name">qe FlowOps</div><div className="sidenav__sub">Release evidence for RAG apps</div></div>
        </div>

        <div className="sidenav__group">
          <button type="button" className="navlink" aria-current={cur(route.name === 'connect')} onClick={() => go('#connect', onClose)}>
            <span className="material-symbols-outlined" aria-hidden="true">add_link</span><span className="navlink__text">Connect your RAG app</span>
          </button>
        </div>

        <div className="sidenav__group">
          <div className="sidenav__label">Your projects</div>
          {projects.length === 0 && <span className="muted" style={{ padding: '0 8px' }}>None yet</span>}
          {projects.slice(0, 12).map((p) => (
            <button type="button" key={p.id} className="navlink" aria-current={cur(route.name === 'project' && route.projectId === p.id)}
              onClick={() => go(projectHref(p.id), onClose)}>
              <span className="material-symbols-outlined" aria-hidden="true">folder</span>
              <span className="navlink__text">{projectLabel(p)}</span>
            </button>
          ))}
        </div>

        <div className="sidenav__group">
          <div className="sidenav__label">Tools</div>
          <button type="button" className="navlink" aria-current={cur(legacyId === 'new')} onClick={() => go('#new', onClose)}>
            <span className="material-symbols-outlined" aria-hidden="true">science</span><span className="navlink__text">Scenario tester</span>
          </button>
          <button type="button" className="navlink" aria-current={cur(legacyId === 'bench')} onClick={() => go('#bench', onClose)}>
            <span className="material-symbols-outlined" aria-hidden="true">leaderboard</span><span className="navlink__text">Model benchmarks</span>
          </button>
          <button type="button" className="navlink" aria-current={cur(legacyId === 'test-llm')} onClick={() => go('#test-llm', onClose)}>
            <span className="material-symbols-outlined" aria-hidden="true">terminal</span><span className="navlink__text">LLM testing studio</span>
          </button>
          {(scenarioRuns.length > 0 || benches.length > 0) && (
            <details className="navdetails" open={pastOpen}>
              <summary>Past runs ({scenarioRuns.length + benches.length})</summary>
              {scenarioRuns.slice(0, 8).map((r) => (
                <button type="button" key={r.id} className="navlink" aria-current={cur(legacyId === r.id)}
                  onClick={() => go(`#${encodeURIComponent(r.id)}`, onClose)}>
                  <span className="navlink__text fmono">{r.id}</span>
                </button>
              ))}
              {benches.slice(0, 8).map((x) => (
                <button type="button" key={x.id} className="navlink" aria-current={cur(legacyId === x.id)} onClick={() => go(`#${encodeURIComponent(x.id)}`, onClose)}>
                  <span className="navlink__text fmono">{x.id}</span>
                </button>
              ))}
            </details>
          )}
        </div>
      </aside>
    </>
  );
};
