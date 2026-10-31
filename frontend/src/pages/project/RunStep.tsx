import React, { useEffect, useState } from 'react';
import { describeError } from '../../api';
import { evaluationsApi, llmApi } from '../../lib/projects';
import { EXECUTION_MODE_INFO, RISK_FOCUS_OPTIONS } from '../../lib/explain';
import { projectHref } from '../../lib/route';
import { sourceLabel } from '../../lib/provenance';
import { Banner, Field, Loading, Tip } from '../../components/flow/ui';
import { PolicyForm, type PolicyResolution } from './PolicyForm';
import { JudgeStatusPanel } from './JudgePanel';
import { judgeApi } from '../../lib/campaign';
import type { Evaluation, LlmStatus, Project } from '../../types/api';
import type { JudgeStatus } from '../../types/campaign';

const DEFAULTS = { max_questions: 50, repeats: 3 };
const UNRESOLVED: PolicyResolution = { ready: false, problems: ['The policy form has not loaded yet.'], useExample: false };

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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [llm, setLlm] = useState<LlmStatus | null>(null);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [policy, setPolicy] = useState<PolicyResolution>(UNRESOLVED);
  const [judge, setJudge] = useState<JudgeStatus | null>(null);
  const [judgeError, setJudgeError] = useState<string | null>(null);
  const mode = project.analysis?.execution_mode ?? 'static_only';
  const hasQa = (project.inputs.qa_pairs?.length ?? 0) > 0;
  const llmMissing = llm !== null && !llm.configured;
  const canGenerate = !llmMissing;
  const willGenerate = generate && canGenerate;
  const noQuestions = !hasQa && !willGenerate && llm !== null;

  useEffect(() => {
    let live = true;
    llmApi.status().then((s) => { if (live) setLlm(s); }).catch((e: unknown) => { if (live) setLlmError(describeError(e, 'the language-model status')); });
    judgeApi.status().then((s) => { if (live) setJudge(s); }).catch((e: unknown) => { if (live) setJudgeError(describeError(e, 'the judge status')); });
    return () => { live = false; };
  }, []);

  const blockers = [...(policy.ready ? [] : policy.problems), ...(noQuestions ? ['There are no questions to ask: add Q&A pairs in Inputs, or configure question generation.'] : [])];

  const start = async (e: React.FormEvent) => {
    e.preventDefault();
    if (blockers.length > 0) return;
    setBusy(true); setError(null);
    try {
      const res = await evaluationsApi.create({
        project_id: project.id, max_questions: maxQ, repeats, include_security: security, generate_questions: willGenerate,
        risk_focus: project.inputs.risk_focus ?? [],
        ...(policy.useExample ? { use_example_policy: true } : { policy: policy.policy }),
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
              {Object.entries(bySource).map(([s, n]) => <li key={s} className="fchip">{sourceLabel(s)}: {n}</li>)}
            </ul>
          )}
          <p className="muted" style={{ marginTop: 12 }}>
            Risk focus: {focus || 'default set'}. Items labelled "Security probe" test prompt injection and leakage,
            "Yours" are your questions, "Generated from your docs" are written from your documents, and "Regression" are past failures re-asked.
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
      {llmMissing && (
        <Banner tone="warn" role="alert">
          <span data-testid="llm-banner">
            <strong>No language model is configured on the server, so questions cannot be generated.</strong> Set these in the backend environment, then restart it:{' '}
            {llm!.missing.map((n) => <code key={n} className="fchip" style={{ marginRight: 6 }}>{n}</code>)}
            Only the names are shown, never values. You can still run with your own Q&amp;A pairs.
          </span>
        </Banner>
      )}
      {llmError && <Banner tone="info" role="status">Could not check whether question generation is available. {llmError}</Banner>}

      <PolicyForm projectId={project.id} includeSecurity={security} onResolved={setPolicy} />

      <section className="panel stack" aria-labelledby="judge-h" data-testid="run-judge">
        <div className="frow frow--between">
          <h2 className="h2" id="judge-h" style={{ margin: 0 }}>Semantic judge <Tip text="A second model that reads answers for meaning. Advisory unless your policy sets a minimum agreement and a fresh calibration meets it." /></h2>
          <a className="fbtn fbtn--ghost fbtn--sm" href={projectHref(project.id, 'judge')}>Judge &amp; calibration</a>
        </div>
        <JudgeStatusPanel status={judge} error={judgeError} compact />
      </section>

      <section className="panel stack" aria-labelledby="opt-h">
        <h2 className="h2" id="opt-h" style={{ margin: 0 }}>Run options</h2>
        <p className="muted" style={{ margin: 0 }}>Defaults are a good first run. More questions and repeats give tighter confidence intervals but take longer.</p>
        <div className="grid2">
          <Field label="Maximum questions" htmlFor="maxq" tip="A hard cap on every test item that runs, including regression, security and variant items." hint="1 to 200. Default 50.">
            <input id="maxq" className="input" type="number" min={1} max={200} value={maxQ} onChange={(e) => setMaxQ(Math.max(1, Math.min(200, Number(e.target.value) || 1)))} />
          </Field>
          <Field label="Repeats per question" htmlFor="rep" tip="Each question is asked several times to check the app answers consistently." hint="1 to 10. Default 3.">
            <input id="rep" className="input" type="number" min={1} max={10} value={repeats} onChange={(e) => setRepeats(Math.max(1, Math.min(10, Number(e.target.value) || 1)))} />
          </Field>
        </div>
        <p className="field__hint" style={{ margin: 0 }} data-testid="cap-hint">
          The maximum is a hard cap on the total number of test items, not just base questions. When there are more candidates than the cap, items are kept in this order:
          regression suite first, then security probes, then question variants, then your base questions. Raise the cap if you need all of them.
        </p>
        <label className="fcheck"><input type="checkbox" checked={security} onChange={(e) => setSecurity(e.target.checked)} /><span>Include security probes (prompt injection, data leakage)</span></label>
        {!security && (
          <Banner tone="warn" role="status">
            <span data-testid="security-off-warning"><strong>Without security probes this run cannot be recommended for RELEASE.</strong> The decision will say &quot;security not tested&quot; and falls back to insufficient evidence, because attack resistance is required evidence.</span>
          </Banner>
        )}
        <div className="stack" style={{ gap: 4 }}>
          <label className="fcheck">
            <input type="checkbox" checked={willGenerate} disabled={!canGenerate} onChange={(e) => setGenerate(e.target.checked)} data-testid="generate-questions" />
            <span>Generate extra questions from my documents <Tip text="Adds questions written by a model from your documents, labelled 'generated'. They are advisory until a human confirms them." /></span>
          </label>
          {!canGenerate && <span className="field__hint" data-testid="generate-disabled-reason">Unavailable: no language model is configured on the server (see the notice above).</span>}
        </div>
      </section>
      {error && <Banner tone="bad" role="alert">{error}</Banner>}
      {blockers.length > 0 && (
        <div role="status" data-testid="run-blockers" id="run-blockers">
          <p className="h3" style={{ marginBottom: 4 }}>Before you can run:</p>
          <ul style={{ margin: 0, paddingLeft: 18 }} className="muted">{blockers.map((b) => <li key={b}>{b}</li>)}</ul>
        </div>
      )}
      <div className="frow">
        <button type="submit" className="fbtn" disabled={busy || blockers.length > 0} aria-describedby={blockers.length > 0 ? 'run-blockers' : undefined} data-testid="start-eval">
          {busy ? <Loading label="Starting…" /> : <>Run evaluation <span className="material-symbols-outlined" aria-hidden="true">play_arrow</span></>}
        </button>
        <a className="fbtn fbtn--ghost" href={projectHref(project.id, 'inputs')}>Back to inputs</a>
      </div>
    </form>
  );
};
