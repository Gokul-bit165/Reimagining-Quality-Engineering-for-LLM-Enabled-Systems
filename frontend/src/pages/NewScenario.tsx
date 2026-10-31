import React, { useState, useEffect } from 'react';
import type { Taxonomy, Config } from '../types/api';
import { api } from '../api';
import { ProcessingState } from '../components/stitch/ProcessingState';

const EXAMPLES: Record<string, [string, string]> = {
  rag: ['LLM09', 'Customers receive wrong or invented shipping and returns policy facts'],
  toolagent: ['LLM06', "The agent may act on a user's false claim of authority or post data to look-alike hosts"],
};

interface NewScenarioProps {
  taxonomy: Taxonomy;
  config: Config;
  lastFailures: string[];
  onScenarioCreated: (runId: string) => void;
}

export const NewScenario: React.FC<NewScenarioProps> = ({
  taxonomy,
  config,
  lastFailures,
  onScenarioCreated,
}) => {
  const [app, setApp] = useState<string>(taxonomy.apps[0] || 'rag');
  const [tax, setTax] = useState<string>('LLM09');
  const [text, setText] = useState<string>('');
  const [budget, setBudget] = useState<number>(12);
  const [mode, setMode] = useState<'simulated' | 'real'>('simulated');
  const [feedFailures, setFeedFailures] = useState<boolean>(false);
  const [status, setStatus] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Pre-fill defaults based on selected app
  useEffect(() => {
    if (EXAMPLES[app]) {
      const [defaultTax, defaultText] = EXAMPLES[app];
      setTax(defaultTax);
      setText(defaultText);
    }
  }, [app]);

  const handleSubmit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setIsSubmitting(true);
    setStatus('');

    try {
      const res = await api<{ scenario_id: string; runs: [string, string] }>('/api/scenarios', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          app,
          taxonomy_id: tax,
          scenario: text,
          budget: Number(budget),
          previous_failures: feedFailures ? lastFailures : [],
          mode,
        }),
      });
      // res.runs[1] is the seeded run
      onScenarioCreated(res.runs[1]);
    } catch (e: any) {
      setStatus(`Execution failed: ${e.message}`);
      setIsSubmitting(false);
    }
  };

  if (isSubmitting) {
    return (
      <ProcessingState
        title={`Executing Pipeline: ${app.toUpperCase()} • ${tax}`}
        subtitle={
          mode === 'real'
            ? `Running real OpenRouter model (${config.tester_model}) across clean & seeded variants...`
            : `Synthesizing ${budget} test variations & running adversarial sink checks...`
        }
        estimatedSeconds={mode === 'real' ? 180 : 10}
      />
    );
  }

  return (
    <div style={{ maxWidth: '48rem', margin: '0 auto', padding: '16px 0' }}>
      <div style={{ marginBottom: '24px' }}>
        <span style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: '#4f46e5', fontWeight: 600 }}>
          STEP 1 • PIPELINE ORCHESTRATION
        </span>
        <h1 style={{ margin: '6px 0 8px 0', fontSize: '24px', fontFamily: 'var(--font-geist)', color: '#0f172a', fontWeight: 700 }}>
          New Risk Scenario Trigger
        </h1>
        <p style={{ margin: 0, fontSize: '14px', color: '#64748b', lineHeight: 1.5 }}>
          Describe a target risk. The pipeline synthesizes dynamic test cases from application sources,
          dispatches tests to clean and seeded target apps, applies adversarial probes, and evaluates policy appetite compliance.
        </p>
      </div>

      <div
        style={{
          backgroundColor: '#ffffff',
          borderRadius: '12px',
          border: '1px solid #e2e8f0',
          padding: '24px',
          boxShadow: '0 1px 3px rgba(15, 23, 42, 0.04)',
        }}
      >
        <form className="form" onSubmit={handleSubmit} style={{ margin: 0 }}>
          <label htmlFor="f-app">Target Sandbox Application</label>
          <select id="f-app" value={app} onChange={(e) => setApp(e.target.value)}>
            {taxonomy.apps.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>

          <label htmlFor="f-tax">OWASP LLM Vulnerability Category</label>
          <select id="f-tax" value={tax} onChange={(e) => setTax(e.target.value)}>
            {taxonomy.entries.map((t) => (
              <option key={t.id} value={t.id}>
                {`${t.id} — ${t.title}`}
              </option>
            ))}
          </select>

          <label htmlFor="f-text">Risk Scenario Narrative</label>
          <textarea
            id="f-text"
            rows={3}
            maxLength={500}
            required
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Describe what failure mode or exploit you want to evaluate..."
          />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div>
              <label htmlFor="f-budget">Test Budget (Cases to Generate)</label>
              <input
                id="f-budget"
                type="number"
                min={1}
                max={40}
                value={budget}
                onChange={(e) => setBudget(Number(e.target.value))}
              />
            </div>

            <div>
              <label htmlFor="f-mode">Execution Mode</label>
              <select
                id="f-mode"
                value={mode}
                onChange={(e) => setMode(e.target.value as 'simulated' | 'real')}
              >
                <option value="simulated">Simulated (Deterministic, offline — 1s)</option>
                {config.real_available && (
                  <option value="real">
                    {`Real models via OpenRouter (${config.tester_model})`}
                  </option>
                )}
              </select>
              <p style={{ margin: '4px 0 0', fontSize: '11px', color: '#64748b' }}>
                {mode === 'real'
                  ? '⚠️ Real free-tier OpenRouter models queue requests (~35s/call, ~3 mins total).'
                  : '⚡ Simulated mode runs locally and completes in ~1 second.'}
              </p>
            </div>
          </div>

          <label className="check" style={{ marginTop: '12px' }}>
            <input
              id="f-feed"
              type="checkbox"
              checked={feedFailures}
              disabled={!lastFailures.length}
              onChange={(e) => setFeedFailures(e.target.checked)}
            />
            {` Also target previous failures${
              lastFailures.length ? ` (${lastFailures.join(', ')})` : ' (open a run with failures first)'
            }`}
          </label>

          {status && (
            <div
              style={{
                marginTop: '16px',
                padding: '12px 16px',
                backgroundColor: '#fff1f2',
                border: '1px solid #fecdd3',
                borderRadius: '8px',
                color: '#e11d48',
                fontSize: '13px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                error
              </span>
              <span>{status}</span>
            </div>
          )}

          <div style={{ marginTop: '20px', display: 'flex', alignItems: 'center', gap: '16px' }}>
            <button
              className="btn"
              type="submit"
              disabled={isSubmitting}
              style={{
                backgroundColor: '#4f46e5',
                padding: '10px 20px',
                borderRadius: '8px',
                fontSize: '13px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>
                play_arrow
              </span>
              <span>Generate Tests and Run Pipeline</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
