import React, { useCallback, useEffect, useState } from 'react';
import type { BenchStatus, Config, Report, RunSummary, Taxonomy, Project } from './types/api';
import { api } from './api';
import { projectsApi } from './lib/projects';
import { parseRoute, type Route } from './lib/route';
import { Nav } from './components/flow/Nav';
import { TopBar } from './components/stitch/TopBar';
import { ConnectPage } from './pages/ConnectPage';
import { ProjectPage } from './pages/ProjectPage';
import { NewScenario } from './pages/NewScenario';
import { ReportView } from './pages/ReportView';
import { BenchForm } from './pages/BenchForm';
import { BenchView } from './pages/BenchView';
import { LLMTestingStudio } from './pages/LLMTestingStudio';

/** Demo/benchmark data. Loaded lazily and optionally: failures never block the main flow. */
function useLegacyData() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [taxonomy, setTaxonomy] = useState<Taxonomy>({ name: '', status: '', apps: [], entries: [] });
  const [config, setConfig] = useState<Config>({ real_available: false });
  const [benches, setBenches] = useState<BenchStatus[]>([]);
  const refresh = useCallback(async () => {
    const [r, t, c, b] = await Promise.allSettled([
      api<RunSummary[]>('/api/runs'), api<Taxonomy>('/api/taxonomy'), api<Config>('/api/config'), api<BenchStatus[]>('/api/benchmarks'),
    ]);
    if (r.status === 'fulfilled') setRuns(r.value);
    if (t.status === 'fulfilled') setTaxonomy(t.value);
    if (c.status === 'fulfilled') setConfig(c.value);
    if (b.status === 'fulfilled') setBenches(b.value);
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  return { runs, taxonomy, config, benches, refresh };
}

export const App: React.FC = () => {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  const [navOpen, setNavOpen] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentReport, setCurrentReport] = useState<Report | null>(null);
  const [lastFailures, setLastFailures] = useState<string[]>([]);
  const legacy = useLegacyData();

  useEffect(() => {
    const onHash = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => { projectsApi.list().then(setProjects).catch(() => setProjects([])); }, [route]);

  const legacyId = route.name === 'legacy' ? route.id : '';
  const isReport = Boolean(legacyId) && !['new', 'bench', 'test-llm'].includes(legacyId) && !legacyId.startsWith('bench-');

  useEffect(() => {
    if (!isReport) { setCurrentReport(null); return; }
    api<Report>(`/api/runs/${encodeURIComponent(legacyId)}/report`).then(setCurrentReport).catch(() => setCurrentReport(null));
  }, [isReport, legacyId]);

  const navigate = (r: string) => { window.location.hash = r; };

  return (
    <div className="shell">
      <header className="mobilebar">
        <strong style={{ fontFamily: 'var(--font-geist)', color: 'var(--c-accent-ink)' }}>qe FlowOps</strong>
        <button type="button" className="fbtn fbtn--ghost fbtn--sm" aria-expanded={navOpen} aria-controls="primary-nav" onClick={() => setNavOpen(!navOpen)}>
          <span className="material-symbols-outlined" aria-hidden="true">menu</span>Menu
        </button>
      </header>
      <Nav route={route} open={navOpen} projects={projects} runs={legacy.runs} benches={legacy.benches} onClose={() => setNavOpen(false)} />

      <main className="shell__main">
        {route.name === 'legacy' && <TopBar report={currentReport} currentRunId={isReport ? legacyId : legacyId} onNavigate={navigate} />}
        <div className="shell__scroll custom-scroll">
          {route.name === 'connect' && <ConnectPage />}
          {route.name === 'project' && <ProjectPage key={route.projectId} projectId={route.projectId} step={route.step} evalId={route.evalId} />}
          {route.name === 'notfound' && (
            <div className="page"><div className="fempty">That page does not exist. <a href="#connect">Go to Connect your RAG app</a>.</div></div>
          )}
          {legacyId === 'new' && (
            <div style={{ padding: '24px', maxWidth: '56rem' }}>
              <NewScenario taxonomy={legacy.taxonomy} config={legacy.config} lastFailures={lastFailures}
                onScenarioCreated={async (id) => { await legacy.refresh(); navigate(id); }} />
            </div>
          )}
          {legacyId === 'bench' && (
            <div style={{ padding: '24px', maxWidth: '56rem' }}>
              <BenchForm onBenchmarkStarted={async (id) => { await legacy.refresh(); navigate(id); }} />
            </div>
          )}
          {legacyId === 'test-llm' && <LLMTestingStudio />}
          {legacyId.startsWith('bench-') && <div style={{ padding: '24px', maxWidth: '64rem' }}><BenchView benchId={legacyId} /></div>}
          {isReport && <div style={{ height: 'calc(100dvh - 130px)' }}><ReportView runId={legacyId} onNavigate={navigate} onFailuresLoaded={setLastFailures} /></div>}
        </div>
      </main>
    </div>
  );
};
