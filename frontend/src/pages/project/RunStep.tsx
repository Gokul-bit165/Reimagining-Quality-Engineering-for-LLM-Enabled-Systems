import React, { useState } from 'react';
import { describeError } from '../../api';
import { evaluationsApi } from '../../lib/projects';
import { EXECUTION_MODE_INFO, RISK_FOCUS_OPTIONS } from '../../lib/explain';
import { projectHref } from '../../lib/route';
import { Banner, Field, Loading, SyntheticBadge, Tip } from '../../components/flow/ui';
import type { Evaluation, Project } from '../../types/api';

const DEFAULTS = { max_questions: 20, repeats: 3 };

const STATE_TEXT: Record<string, string> = {
  queued: 'Queued. Waiting for a worker to pick this up.',
  running: 'Running. Questions are being asked and scored.',
  done: 'Finished.',
  failed: 'The run failed.',
  cancelled: 'Cancelled.',
};

interface RunStepProps {
  project: Project;
  evaluation: Evaluation | null;
  evalError: unknown;
  onChanged: () => void;
}

export const RunStep: React.FC<RunStepProps> = ({ project, evaluation, evalError, onChanged }) => {
  const [maxQ, setMaxQ] = useState(DEFAULTS.max_questions);
  const [repeats, setRepeats] = useState(DEFAULTS.repeats);
  const [security, setSecurity] = useState(true);
  const [generate, setGenerate] = useState(true);
  const [allowSynthetic, setAllowSynthetic] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mode = project.analysis?.execution_mode ?? 'static_only';

  const start = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const res = await evaluationsApi.create({
        project_id: project.id, max_questions: maxQ, repeats, include_security: security, generate_questions: generate,
        allow_synthetic: allowSynthetic, risk_focus: project.inputs.risk_focus ?? [],
      });
      window.location.hash = projectHref(project.id, 'run', res.id);
    } catch (err) {
      setError(describeError(err, 'evaluations'));
    } finally { setBusy(false); }
  };

  const cancel = async () => {
    if (!evaluation) return;
    try { await evaluationsApi.cancel(evaluation.id); onChanged(); } catch (err) { setError(describeError(err, 'cancelling')); }
  };

  if (evaluation) {
    const { done, total } = evaluation.progress;
    const pctDone = total > 0 ? Math.round((done / total) * 100) : 0;
    const active = evaluation.state === 'queued' || evaluation.state === 'running';
    const bySource = evaluation.items.reduce<Record<string, number>>((m, i) => ({ ...m, [i.source]: (m[i.source] ?? 0) + 1 }), {});
    const focus = (project.inputs.risk_focus ?? []).map((id) => RISK_FOCUS_OPTIONS.find((o) => o.id === id)?.label ?? id).join(', ');
    return (
      <div className="stack">
        {evaluation.synthetic && <div><SyntheticBadge detail="The backend marked this evaluation as synthetic." /></div>}
        <section className="panel stack" aria-live="polite" aria-labelledby="prog-h">
          <h2 className="h2" id="prog-h" style={{ margin: 0 }}>Live progress</h2>
          <div className="frow">
            {active && <span className="spinner" aria-hidden="true" />}
            <strong data-testid="eval-state">{evaluation.state}</strong>
            <span className="muted">{STATE_TEXT[evaluation.state]}</span>
          </div>
          <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={total || 100} aria-valuenow={done} aria-label="Evaluation progress">
            <div className="progress__bar" style={{ width: `${pctDone}%` }} />
          </div>
          <p className="muted" data-testid="eval-progress" style={{ margin: 0 }}>{done} of {total || '?'} items complete ({pctDone}%)</p>
          {evaluation.error && <Banner tone="bad" role="alert"><span><strong>Error:</strong> {evaluation.error}</span></Banner>}
          {error && <Banner tone="bad" role="alert">{error}</Banner>}
          <div className="frow">
            {active && <button type="button" className="fbtn fbtn--ghost" onClick={() => void cancel()}>Cancel run</button>}
            {evaluation.state === 'done' && (
              <a className="fbtn" href={projectHref(project.id, 'results', evaluation.id)} data-testid="to-results">
                See results <span className="material-symbols-outlined" aria-hidden="true">arrow_forward</span>
              </a>
            )}
            {(evaluation.state === 'failed' || evaluation.state === 'cancelled') && (
              <a className="fbtn fbtn--ghost" href={projectHref(project.id, 'run')}>Start a new run</a>
            )}
          </div>
        </section>
        <section className="panel" aria-labelledby="cov-h">
          <h2 className="h2" id="cov-h">What is being covered</h2>
          {Object.keys(bySource).length === 0 ? (
            <p className="muted">Items will appear here as they are generated.</p>
          ) : (
            <ul className="chips" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {Object.entries(bySource).map(([s, n]) => <li key={s} className="fchip">{s}: {n}</li>)}
            </ul>
          )}
          <p className="muted" style={{ marginTop: 12 }}>
            Risk focus: {focus || 'default set'}. Items labelled "security" probe prompt injection and leakage,
            "user" are your questions, and "generated" are written from your documents.
          </p>
        </section>
      </div>
    );
  }

  return (
    <form className="stack" onSubmit={start}>
      {Boolean(evalError) && <Banner tone="warn" role="status">Could not load that evaluation: {describeError(evalError, 'this evaluation')}</Banner>}
      <Banner tone={mode === 'static_only' ? 'warn' : 'info'}>
        <span><strong>{EXECUTION_MODE_INFO[mode].label}.</strong> {EXECUTION_MODE_INFO[mode].text}</span>
      </Banner>
      <section className="panel stack" aria-labelledby="opt-h">
        <h2 className="h2" id="opt-h" style={{ margin: 0 }}>Run options</h2>
        <p className="muted" style={{ margin: 0 }}>Defaults are a good first run. More questions and repeats give tighter confidence intervals but take longer.</p>
        <div className="grid2">
          <Field label="Maximum questions" htmlFor="maxq" tip="Upper limit on how many questions are asked." hint="1 to 200">
            <input id="maxq" className="input" type="number" min={1} max={200} value={maxQ} onChange={(e) => setMaxQ(Math.max(1, Math.min(200, Number(e.target.value) || 1)))} />
          </Field>
          <Field label="Repeats per question" htmlFor="rep" tip="Each question is asked several times to check the app answers consistently." hint="1 to 10">
            <input id="rep" className="input" type="number" min={1} max={10} value={repeats} onChange={(e) => setRepeats(Math.max(1, Math.min(10, Number(e.target.value) || 1)))} />
          </Field>
        </div>
        <label className="fcheck"><input type="checkbox" checked={security} onChange={(e) => setSecurity(e.target.checked)} /><span>Include security probes (prompt injection, data leakage)</span></label>
        <label className="fcheck">
          <input type="checkbox" checked={generate} onChange={(e) => setGenerate(e.target.checked)} />
          <span>Generate extra questions from my documents <Tip text="Adds questions written by a model from your documents, labelled 'generated'." /></span>
        </label>
        <label className="fcheck">
          <input type="checkbox" checked={allowSynthetic} onChange={(e) => setAllowSynthetic(e.target.checked)} data-testid="allow-synthetic" />
          <span>Allow the offline synthetic question generator <Tip text="Only needed if you have no questions and no model API key configured. Results are then clearly labelled SYNTHETIC DATA." /></span>
        </label>
      </section>
      {error && <Banner tone="bad" role="alert">{error}</Banner>}
      <div className="frow">
        <button type="submit" className="fbtn" disabled={busy} data-testid="start-eval">
          {busy ? <Loading label="Starting…" /> : <>Run evaluation <span className="material-symbols-outlined" aria-hidden="true">play_arrow</span></>}
        </button>
        <a className="fbtn fbtn--ghost" href={projectHref(project.id, 'inputs')}>Back to inputs</a>
      </div>
    </form>
  );
};
