import React, { useMemo, useState } from 'react';
import { describeError } from '../../api';
import { evaluationsApi } from '../../lib/projects';
import { EXECUTION_MODE_INFO } from '../../lib/explain';
import { projectHref } from '../../lib/route';
import { SOURCE_INFO } from '../../lib/provenance';
import { exportEvaluationCsv, exportEvaluationDoc, exportEvaluationJson } from '../../utils/reportExporter';
import { Banner, MetricCard, Tip, VerdictPanel } from '../../components/flow/ui';
import { FlowCanvas, type StageSpec } from '../../components/stitch/FlowCanvas';
import { AllMetrics, ItemRow, PolicyUsed, SampleSummary, isAdvisoryItem } from './ResultsParts';
import { JudgeSummary } from './JudgeResults';
import { AdvisoryConfirm } from './AdvisoryConfirm';
import { ReportActions } from '../../components/flow/ReportActions';
import type { Evaluation, Project } from '../../types/api';

const SCORE_TIPS: Record<string, string> = {
  accuracy: 'Share of answers that match the reference or are judged correct.',
  grounding: 'Share of answer claims supported by the retrieved passages.',
  completeness: 'Whether answers cover everything the question needs.',
  safety: 'Share of probes where the app stayed within safe behaviour.',
  consistency: 'How often repeated asks give the same answer.',
  security: 'Resistance to prompt injection and data leakage probes.',
};

export function evalStages(project: Project, ev: Evaluation): StageSpec[] {
  const finished = ev.state === 'done';
  const running = ev.state === 'running' || ev.state === 'queued';
  const failed = ev.state === 'failed' || ev.state === 'cancelled';
  const mode = project.analysis?.execution_mode ?? 'static_only';
  const bySource = (s: string) => ev.items.filter((i) => i.source === s).length;
  const v = ev.decision?.verdict;
  return [
    { id: 'analyse', number: 'STAGE 01', title: 'Code analysis', icon: 'manage_search', status: project.analysis ? 'DONE' : 'PENDING', tone: project.analysis ? 'ok' : 'idle',
      desc: `${project.analysis?.risk_flags.length ?? 0} risk flags in ${project.analysis?.framework ?? 'unknown framework'}`, meta: mode },
    { id: 'questions', number: 'STAGE 02', title: 'Questions', icon: 'quiz', status: ev.items.length ? 'READY' : 'PENDING', tone: ev.items.length ? 'ok' : 'idle',
      desc: `${bySource('user')} yours, ${bySource('generated')} from your docs, ${bySource('security')} security probes, ${bySource('regression')} regression`, meta: `${ev.items.length} items` },
    { id: 'execute', number: 'STAGE 03', title: 'Execution', icon: 'terminal', status: failed ? ev.state.toUpperCase() : finished ? 'DONE' : running ? 'RUNNING' : 'PENDING',
      tone: failed ? 'bad' : finished ? 'ok' : running ? 'run' : 'idle',
      desc: mode === 'static_only' ? 'Not executed: static analysis only' : `Asked your ${mode} app`, meta: `${ev.progress.done}/${ev.progress.total || '?'} done` },
    { id: 'score', number: 'STAGE 04', title: 'Scoring', icon: 'analytics', status: finished ? 'SCORED' : 'PENDING', tone: finished ? 'ok' : 'idle',
      desc: `${Object.keys(ev.scorecard ?? {}).length || Object.keys(ev.metrics).length} metrics with intervals`, meta: `${ev.items.filter((i) => i.passed === false).length} failures, ${ev.items.filter((i) => i.passed === null).length} not checked` },
    { id: 'decision', number: 'STAGE 05', title: 'Decision', icon: 'rule', status: v ?? 'PENDING',
      tone: v === 'RELEASE' ? 'ok' : v === 'REJECT' ? 'bad' : v ? 'warn' : 'idle',
      desc: ev.decision?.reasons[0] ?? 'Awaiting evidence', meta: ev.decision?.status === 'pending_review' ? 'needs sign-off' : 'rule-based' },
  ];
}

const SignoffForm: React.FC<{ ev: Evaluation; onDone: () => void }> = ({ ev, onDone }) => {
  const [reviewer, setReviewer] = useState('');
  const [decision, setDecision] = useState<'approve' | 'reject'>('approve');
  const [rationale, setRationale] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reviewer.trim() || !rationale.trim()) { setErr('Reviewer name and a written rationale are both required.'); return; }
    setBusy(true); setErr(null);
    try { await evaluationsApi.signoff(ev.id, { reviewer: reviewer.trim(), decision, rationale: rationale.trim() }); onDone(); }
    catch (x) { setErr(describeError(x, 'sign-off')); }
    finally { setBusy(false); }
  };
  return (
    <form className="panel stack" onSubmit={submit} aria-labelledby="so-h" data-testid="signoff-form">
      <h2 className="h2" id="so-h" style={{ margin: 0 }}>Human review sign-off <Tip text="A named person confirms or overrides the recommendation. The decision and rationale are recorded." /></h2>
      <p className="muted" style={{ margin: 0 }}>This recommendation is pending review. Read the evidence above, then record your decision.</p>
      <div className="grid2">
        <div className="field"><label className="field__label" htmlFor="so-name">Reviewer name</label><input id="so-name" className="input" value={reviewer} onChange={(e) => setReviewer(e.target.value)} autoComplete="name" /></div>
        <div className="field"><label className="field__label" htmlFor="so-dec">Your decision</label>
          <select id="so-dec" className="select" value={decision} onChange={(e) => setDecision(e.target.value as 'approve' | 'reject')}>
            <option value="approve">Approve the recommendation</option>
            <option value="reject">Reject the recommendation</option>
          </select></div>
      </div>
      <div className="field"><label className="field__label" htmlFor="so-why">Rationale</label><textarea id="so-why" className="textarea" style={{ fontFamily: 'var(--font-hanken)', fontSize: 14 }} value={rationale} onChange={(e) => setRationale(e.target.value)} /></div>
      {err && <Banner tone="bad" role="alert">{err}</Banner>}
      <div><button type="submit" className="fbtn" disabled={busy}>{busy ? 'Recording…' : 'Record sign-off'}</button></div>
    </form>
  );
};

interface ResultsStepProps { project: Project; evaluation: Evaluation; onReload: () => void }

export const ResultsStep: React.FC<ResultsStepProps> = ({ project, evaluation: ev, onReload }) => {
  const [filter, setFilter] = useState<'all' | 'failed' | 'passed' | 'unchecked'>('failed');
  const [klass, setKlass] = useState<string | null>(null);
  const [stage, setStage] = useState('decision');
  const mode = project.analysis?.execution_mode ?? 'static_only';
  const stages = useMemo(() => evalStages(project, ev), [project, ev]);

  if (ev.state !== 'done') {
    return (
      <div className="stack">
        <Banner tone={ev.state === 'failed' ? 'bad' : 'info'} role="status">
          <span>This evaluation is <strong>{ev.state}</strong>{ev.error ? `: ${ev.error}` : '. Results appear when it finishes.'}</span>
        </Banner>
        <a className="fbtn fbtn--ghost" href={projectHref(project.id, 'run', ev.id)}>Back to progress</a>
      </div>
    );
  }

  const headline = Object.keys(ev.scorecard ?? {}).length > 0 ? ev.scorecard! : ev.metrics;
  const tax = Object.entries(ev.failure_taxonomy ?? {}).sort((a, b) => b[1].count - a[1].count);
  const matches = (i: Evaluation['items'][number], f: typeof filter) =>
    f === 'all' || (f === 'failed' ? i.passed === false : f === 'passed' ? i.passed === true : i.passed === null);
  const shown = ev.items.filter((i) => matches(i, filter)
    && (!klass || i.failure_class === klass));
  const pending = ev.decision?.status === 'pending_review';

  return (
    <div className="stack">
      <div className="frow">
        <button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={() => exportEvaluationDoc(ev)}>Export Word</button>
        <button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={() => exportEvaluationCsv(ev)}>Export CSV</button>
        <button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={() => exportEvaluationJson(ev)}>Export JSON</button>
      </div>
      {mode === 'static_only' && <Banner tone="warn" role="status"><span><strong>{EXECUTION_MODE_INFO.static_only.label}.</strong> {EXECUTION_MODE_INFO.static_only.text}</span></Banner>}

      {ev.decision ? (
        <VerdictPanel verdict={ev.decision.verdict} reasons={ev.decision.reasons} pendingReview={pending}
          explanation={ev.decision.explanation} policyExample={ev.decision.policy_is_example} policy={ev.decision.policy} />
      ) : <Banner tone="warn">The backend returned no decision for this evaluation.</Banner>}

      {ev.decision?.signoff && (
        <Banner tone="ok" role="status">
          <span data-testid="signoff-record"><strong>Human sign-off recorded.</strong> {ev.decision.signoff.reviewer} chose to {ev.decision.signoff.decision}
            {ev.decision.signoff.rationale ? `: "${ev.decision.signoff.rationale}"` : '.'}</span>
        </Banner>
      )}

      <PolicyUsed ev={ev} projectId={project.id} />

      {ev.judge?.enabled && <JudgeSummary judge={ev.judge} items={ev.items} />}

      <section aria-labelledby="sc-h" className="stack">
        <h2 className="h2" id="sc-h" style={{ margin: 0 }}>Scorecard <span className="muted">(95% confidence intervals)</span></h2>
        <SampleSummary ev={ev} projectId={project.id} />
        {Object.keys(headline).length === 0 ? <div className="fempty">No metrics were produced.</div> : (
          <div className="grid3">{Object.entries(headline).map(([k, m]) => <MetricCard key={k} name={k} m={m} tip={SCORE_TIPS[k]} />)}</div>
        )}
        <AllMetrics metrics={ev.metrics} />
      </section>

      <FlowCanvas storageKey={`project:${project.id}`} stages={stages} selectedId={stage} onSelect={setStage}
        caption={`Pipeline: ${stages.length} stages`} />

      <section className="panel stack" aria-labelledby="ft-h">
        <h2 className="h2" id="ft-h" style={{ margin: 0 }}>Failures and evidence</h2>
        <p className="muted" style={{ margin: 0 }} data-testid="source-legend">
          Each question is labelled by where it came from: {Object.values(SOURCE_INFO).map((s) => `${s.label} (${s.text.replace(/\.$/, '').toLowerCase()})`).join('; ')}.
        </p>
        {tax.length > 0 && (
          <div className="chips" role="group" aria-label="Filter by failure class">
            {tax.map(([k, c]) => (
              <button key={k} type="button" className={`fbtn fbtn--sm ${klass === k ? '' : 'fbtn--ghost'}`} aria-pressed={klass === k}
                title={`Failure class ${k}`} onClick={() => setKlass(klass === k ? null : k)}>{c.name} ({c.count})</button>
            ))}
          </div>
        )}
        <div className="tabs" role="tablist" aria-label="Item filter">
          {(['failed', 'passed', 'unchecked', 'all'] as const).map((f) => (
            <button key={f} type="button" role="tab" aria-selected={filter === f} onClick={() => setFilter(f)}>
              {f === 'all' ? 'All' : f === 'unchecked' ? 'Not checked' : `${f[0].toUpperCase()}${f.slice(1)}`} ({ev.items.filter((i) => matches(i, f)).length})
            </button>
          ))}
        </div>
        {shown.length === 0 ? <div className="fempty">{ev.items.length === 0 ? 'No per-item results were returned.' : 'No items match this filter.'}</div>
          : <ul className="items">{shown.map((i) => <ItemRow key={i.id} item={i} />)}</ul>}
      </section>

      <AdvisoryConfirm ev={ev} advisory={ev.items.filter(isAdvisoryItem)} onDone={onReload} />

      {pending && <SignoffForm ev={ev} onDone={onReload} />}

      <ReportActions owner={{ kind: 'evaluation', id: ev.id }} />

      <div className="frow">
        <a className="fbtn" href={projectHref(project.id, 'operate', ev.id)} data-testid="to-operate">Next: operate <span className="material-symbols-outlined" aria-hidden="true">arrow_forward</span></a>
      </div>
    </div>
  );
};
