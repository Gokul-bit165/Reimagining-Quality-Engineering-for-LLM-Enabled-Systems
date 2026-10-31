import React, { useEffect, useState } from 'react';
import type { Project } from './types/api';
import { projectsApi } from './lib/projects';
import { parseRoute, routeTitle, type Route } from './lib/route';
import { Nav } from './components/flow/Nav';
import { ConnectPage } from './pages/ConnectPage';
import { ProjectPage } from './pages/ProjectPage';


export const App: React.FC = () => {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  const [navOpen, setNavOpen] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);

  useEffect(() => {
    const onHash = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => { projectsApi.list().then(setProjects).catch(() => setProjects([])); }, [route]);
  // Project pages set their own title once the project (and its name) has loaded.
  useEffect(() => { if (route.name !== 'project') document.title = routeTitle(route, null); }, [route]);

  return (
    <div className="shell">
      <header className="mobilebar">
        <strong style={{ fontFamily: 'var(--font-geist)', color: 'var(--c-accent-ink)' }}>qe FlowOps</strong>
        <button type="button" className="fbtn fbtn--ghost fbtn--sm" aria-expanded={navOpen} aria-controls="primary-nav" onClick={() => setNavOpen(!navOpen)}>
          <span className="material-symbols-outlined" aria-hidden="true">menu</span>Menu
        </button>
      </header>
      <Nav route={route} open={navOpen} projects={projects} onClose={() => setNavOpen(false)} />

      <main className="shell__main">
        <div className="shell__scroll custom-scroll">
          {route.name === 'connect' && <ConnectPage />}
          {route.name === 'project' && <ProjectPage key={route.projectId} projectId={route.projectId} step={route.step} evalId={route.evalId} campaignId={route.campaignId ?? null} />}
          {route.name === 'notfound' && (
            <div className="page"><div className="fempty">That page does not exist. <a href="#connect">Go to Connect your RAG app</a>.</div></div>
          )}
        </div>
      </main>
    </div>
  );
};
