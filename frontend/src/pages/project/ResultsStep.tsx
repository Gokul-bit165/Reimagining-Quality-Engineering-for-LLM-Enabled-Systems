import React, { useMemo, useState } from 'react';
import { describeError } from '../../api';
import { evaluationsApi } from '../../lib/projects';
import { EXECUTION_MODE_INFO, FAILURE_REASON_TEXT, num } from '../../lib/explain';
import { projectHref } from '../../lib/route';
import { exportEvaluationCsv, exportEvaluationDoc, exportEvaluationJson } from '../../utils/reportExporter';
import { Banner, MetricCard, SyntheticBadge, Tip, VerdictPanel } from '../../components/flow/ui';
import { FlowCanvas, type StageSpec } from '../../components/stitch/FlowCanvas';
import type { EvalItem, Evaluation, Project } from '../../types/api';

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
      desc: `${bySource('user')} yours, ${bySource('generated')} generated, ${bySource('security')} security`, meta: `${ev.items.length} items` },
    { id: 'execute', number: 'STAGE 03', title: 'Execution', icon: 'terminal', status: failed ? ev.state.toUpperCase() : finished ? 'DONE' : running ? 'RUNNING' : 'PENDING',
      tone: failed ? 'bad' : finished ? 'ok' : running ? 'run' : 'idle',
      desc: mode === 'static_only' ? 'Not executed: static analysis only' : `Asked your ${mode} app`, meta: `${ev.progress.done}/${ev.progress.total || '?'} done` },
    { id: 'score', number: 'STAGE 04', title: 'Scoring', icon: 'analytics', status: finished ? 'SCORED' : 'PENDING', tone: finished ? 'ok' : 'idle',
      desc: `${Object.keys(ev.scorecard ?? {}).length || Object.keys(ev.metrics).length} metrics with intervals`, meta: `${ev.items.filter((i) => i.passed === false).length} failures` },
    { id: 'decision', number: 'STAGE 05', title: 'Decision', icon: 'rule', status: v ?? 'PENDING',
      tone: v === 'RELEASE' ? 'ok' : v === 'REJECT' ? 'bad' : v ? 'warn' : 'idle',
      desc: ev.decision?.reasons[0] ?? 'Awaiting evidence', meta: ev.decision?.status === 'pending_review' ? 'needs sign-off' : 'rule-based' },
  ];
}

function fmtScore(v: EvalItem['scores'][string]): string {
  if (v === null || v === undefined) return 'n/a';
  if (typeof v === 'boolean') return v ? 'pass' : 'fail';
  if (Array.isArray(v)) return v.map((x) => (typeof x === 'boolean' ? (x ? 'pass' : 'fail') : num(x))).join(' / ');
  return num(v);
}

function detailLines(d: EvalItem['detail']): string[] {
  if (!d) return [];
  return Object.entries(d).flatMap(([k, v]) => (Array.isArray(v) ? v.map((x) => `${k.replace(/_/g, ' ')}: ${String(x)}`) : [`${k.replace(/_/g, ' ')}: ${String(v)}`]));
}

const ItemRow: React.FC<{ item: EvalItem }> = ({ item }) => {
  const [open, setOpen] = useState(false);
  const bodyId = `item-${item.id}`;
  return (
    <li className="item" data-testid="eval-item">
      <button type="button" className="item__head" aria-expanded={open} aria-controls={bodyId} onClick={() => setOpen(!open)}>
        <span className="badge" data-tone={item.passed === true ? 'ok' : item.passed === false ? 'bad' : ''}>
          {item.passed === true ? 'PASS' : item.passed === false ? 'FAIL' : 'N/A'}
        </span>
        <span className="item__q">{item.question}</span>
        <span className="fchip">{item.source}</span>
        <span className="material-symbols-outlined" aria-hidden="true">{open ? 'expand_less' : 'expand_more'}</span>
      </button>
      {open && (
        <div className="item__body" id={bodyId}>
          {item.failure_reason && <Banner tone="bad"><span><strong>Why it failed{item.failure_class ? ` (${item.failure_class})` : ''}:</strong> {FAILURE_REASON_TEXT[item.failure_reason] ?? item.failure_reason}</span></Banner>}
          {detailLines(item.detail).length > 0 && (
            <div><div className="h3">Evidence</div><ul style={{ margin: 0, paddingLeft: 18 }}>{detailLines(item.detail).map((l, i) => <li key={i}>{l}</li>)}</ul></div>
          )}
          <div><div className="h3">Question</div><p className="quote">{item.question}</p></div>
          <div><div className="h3">Reference answer</div><p className="quote">{item.reference_answer ?? 'None provided'}</p></div>
          <div><div className="h3">App answer</div><p className="quote">{item.answer ?? 'No answer produced (code was not executed, or the call failed).'}</p></div>
          <div>
            <div className="h3">Retrieved contexts ({item.contexts.length})</div>
            {item.contexts.length === 0 ? <p className="muted">No passages were retrieved.</p>
              : item.contexts.map((c, i) => <p key={i} className="quote quote--ctx">{c}</p>)}
          </div>
          {Object.keys(item.scores).length > 0 && (
            <div className="frow">{Object.entries(item.scores).map(([k, v]) => <span key={k} className="score">{k}: {fmtScore(v)}</span>)}</div>
          )}
        </div>
      )}
    </li>
  );
};

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
  const [filter, setFilter] = useState<'all' | 'failed' | 'passed'>('failed');
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
  const shown = ev.items.filter((i) => (filter === 'all' || (filter === 'failed' ? i.passed === false : i.passed === true))
    && (!klass || i.failure_class === klass));
  const pending = ev.decision?.status === 'pending_review';

  return (
    <div className="stack">
      <div className="frow">
        {ev.synthetic && <SyntheticBadge detail="The backend marked this result as synthetic: it is not a measurement of a real run." />}
        <button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={() => exportEvaluationDoc(ev)}>Export Word</button>
        <button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={() => exportEvaluationCsv(ev)}>Export CSV</button>
        <button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={() => exportEvaluationJson(ev)}>Export JSON</button>
      </div>
      {ev.synthetic && <Banner tone="warn" role="status">These numbers come from synthetic data or a simulated app. Do not use them to make a real release decision.</Banner>}
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

      <section aria-labelledby="sc-h">
        <h2 className="h2" id="sc-h">Scorecard <span className="muted">(95% confidence intervals)</span></h2>
        {Object.keys(headline).length === 0 ? <div className="fempty">No metrics were produced.</div> : (
          <div className="grid3">{Object.entries(headline).map(([k, m]) => <MetricCard key={k} name={k} m={m} tip={SCORE_TIPS[k]} />)}</div>
        )}
      </section>

      <FlowCanvas storageKey={`project:${project.id}`} stages={stages} selectedId={stage} onSelect={setStage}
        caption={`Pipeline: ${stages.length} stages`} />

      <section className="panel stack" aria-labelledby="ft-h">
        <h2 className="h2" id="ft-h" style={{ margin: 0 }}>Failures and evidence</h2>
        {tax.length > 0 && (
          <div className="chips" role="group" aria-label="Filter by failure class">
            {tax.map(([k, c]) => (
              <button key={k} type="button" className={`fbtn fbtn--sm ${klass === k ? '' : 'fbtn--ghost'}`} aria-pressed={klass === k}
                title={`Failure class ${k}`} onClick={() => setKlass(klass === k ? null : k)}>{c.name} ({c.count})</button>
            ))}
          </div>
        )}
        <div className="tabs" role="tablist" aria-label="Item filter">
          {(['failed', 'passed', 'all'] as const).map((f) => (
            <button key={f} type="button" role="tab" aria-selected={filter === f} onClick={() => setFilter(f)}>
              {f === 'all' ? `All (${ev.items.length})` : `${f[0].toUpperCase()}${f.slice(1)} (${ev.items.filter((i) => (i.passed === false) === (f === 'failed') && i.passed !== null).length})`}
            </button>
          ))}
        </div>
        {shown.length === 0 ? <div className="fempty">{ev.items.length === 0 ? 'No per-item results were returned.' : 'No items match this filter.'}</div>
          : <ul className="items">{shown.map((i) => <ItemRow key={i.id} item={i} />)}</ul>}
      </section>

      {pending && <SignoffForm ev={ev} onDone={onReload} />}

      <div className="frow">
        <a className="fbtn" href={projectHref(project.id, 'operate', ev.id)} data-testid="to-operate">Next: operate <span className="material-symbols-outlined" aria-hidden="true">arrow_forward</span></a>
      </div>
    </div>
  );
};
