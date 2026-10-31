import React, { useState, useEffect, useCallback } from 'react';
import type { RunSummary, Taxonomy, Config, BenchStatus, Report } from './types/api';
import { api } from './api';
import { Sidebar } from './components/stitch/Sidebar';
import { TopBar } from './components/stitch/TopBar';
import { NewScenario } from './pages/NewScenario';
import { ReportView } from './pages/ReportView';
import { BenchForm } from './pages/BenchForm';
import { BenchView } from './pages/BenchView';
import { LLMTestingStudio } from './pages/LLMTestingStudio';

export const App: React.FC = () => {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [taxonomy, setTaxonomy] = useState<Taxonomy>({ name: '', status: '', apps: [], entries: [] });
  const [config, setConfig] = useState<Config>({ real_available: false });
  const [benches, setBenches] = useState<BenchStatus[]>([]);
  const [lastFailures, setLastFailures] = useState<string[]>([]);
  const [route, setRoute] = useState<string>('new');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Active report reference for TopBar
  const [currentReport, setCurrentReport] = useState<Report | null>(null);

  const getHash = () => decodeURIComponent(window.location.hash.slice(1)) || 'new';

  const refreshAll = useCallback(async () => {
    try {
      const [runsData, taxData, configData, benchData] = await Promise.all([
        api<RunSummary[]>('/api/runs'),
        api<Taxonomy>('/api/taxonomy'),
        api<Config>('/api/config'),
        api<BenchStatus[]>('/api/benchmarks'),
      ]);
      setRuns(runsData);
      setTaxonomy(taxData);
      setConfig(configData);
      setBenches(benchData);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshAll();

    const handleHash = () => {
      const h = getHash();
      setRoute(h);
      if (h !== 'new' && h !== 'bench' && h !== 'test-llm' && !h.startsWith('bench-')) {
        api<Report>(`/api/runs/${encodeURIComponent(h)}/report`)
          .then(setCurrentReport)
          .catch(() => setCurrentReport(null));
      } else {
        setCurrentReport(null);
      }
    };

    window.addEventListener('hashchange', handleHash);
    handleHash();

    return () => window.removeEventListener('hashchange', handleHash);
  }, [refreshAll]);

  const handleNavigate = (newRoute: string) => {
    window.location.hash = newRoute;
  };

  const handleScenarioCreated = async (seededRunId: string) => {
    try {
      const updatedRuns = await api<RunSummary[]>('/api/runs');
      setRuns(updatedRuns);
    } catch { /* ignore */ }
    window.location.hash = seededRunId;
  };

  const handleBenchmarkStarted = async (benchId: string) => {
    try {
      const updatedBenches = await api<BenchStatus[]>('/api/benchmarks');
      setBenches(updatedBenches);
    } catch { /* ignore */ }
    window.location.hash = benchId;
  };

  if (loading) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b' }}>
        <p className="empty">Loading verification platform…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#e11d48' }}>
        <p className="error">{`Could not load: ${error}`}</p>
      </div>
    );
  }

  const isReportRoute = route !== 'new' && route !== 'bench' && route !== 'test-llm' && !route.startsWith('bench-');

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw', overflow: 'hidden' }}>
      {/* Stitch Sidebar */}
      <Sidebar
        activeRoute={route}
        runs={runs}
        benches={benches}
        onNavigate={handleNavigate}
      />

      {/* Main Container */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
        {/* Stitch TopBar */}
        <TopBar
          report={currentReport}
          currentRunId={isReportRoute ? route : undefined}
          onNavigate={handleNavigate}
        />

        {/* Viewport Content */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {route === 'new' && (
            <div className="custom-scroll" style={{ flex: 1, overflowY: 'auto', padding: '32px 48px', maxWidth: '56rem' }}>
              <NewScenario
                taxonomy={taxonomy}
                config={config}
                lastFailures={lastFailures}
                onScenarioCreated={handleScenarioCreated}
              />
            </div>
          )}

          {route === 'bench' && (
            <div className="custom-scroll" style={{ flex: 1, overflowY: 'auto', padding: '32px 48px', maxWidth: '56rem' }}>
              <BenchForm onBenchmarkStarted={handleBenchmarkStarted} />
            </div>
          )}

          {route === 'test-llm' && (
            <div className="custom-scroll" style={{ flex: 1, overflowY: 'auto' }}>
              <LLMTestingStudio />
            </div>
          )}

          {route.startsWith('bench-') && (
            <div className="custom-scroll" style={{ flex: 1, overflowY: 'auto', padding: '32px 48px', maxWidth: '64rem' }}>
              <BenchView benchId={route} />
            </div>
          )}

          {isReportRoute && (
            <ReportView
              runId={route}
              onNavigate={handleNavigate}
              onFailuresLoaded={setLastFailures}
            />
          )}
        </div>
      </div>
    </div>
  );
};
