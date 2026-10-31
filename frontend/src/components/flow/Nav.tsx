import React from 'react';
import type { Project } from '../../types/api';
import { projectHref, type Route } from '../../lib/route';

interface NavProps {
  route: Route;
  open: boolean;
  projects: Project[];
  onClose: () => void;
}

/** Repo name plus sub-folder and a short id so two projects of one repo stay distinguishable. */
export function projectLabel(p: Project): string {
  const repo = p.repo_url.replace(/^https:\/\/github\.com\/[^/]+\//, '');
  const sub = p.subdir ? ` / ${p.subdir}` : '';
  return `${repo.length > 28 ? `${repo.slice(0, 26)}…` : repo}${sub} · ${p.id.slice(-4)}`;
}

const go = (hash: string, close: () => void) => { window.location.hash = hash; close(); };

export const Nav: React.FC<NavProps> = ({ route, open, projects, onClose }) => {
  const cur = (on: boolean) => (on ? ('page' as const) : undefined);
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
          {projects.map((p) => (
            <button type="button" key={p.id} className="navlink" aria-current={cur(route.name === 'project' && route.projectId === p.id)}
              onClick={() => go(projectHref(p.id), onClose)}>
              <span className="material-symbols-outlined" aria-hidden="true">folder</span>
              <span className="navlink__text">{projectLabel(p)}</span>
              {p.state === 'failed' && <span className="badge" data-tone="bad" title={p.error ?? 'Analysis failed'}>failed</span>}
            </button>
          ))}
        </div>
      </aside>
    </>
  );
};
