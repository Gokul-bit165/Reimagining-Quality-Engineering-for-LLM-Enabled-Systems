import React, { useState } from 'react';
import { describeError } from '../../api';
import { evaluationsApi, projectsApi } from '../../lib/projects';
import { sourceLabel } from '../../lib/provenance';
import { downloadText } from '../../utils/reportExporter';
import { metricLabel } from '../../lib/policy';
import { Banner, Loading } from '../../components/flow/ui';
import type { Evaluation, MonitoringPlan, Project, WatchEntry, WatchStatus } from '../../types/api';

const pct = (v: number | null | undefined) => (v === null || v === undefined ? 'not set' : `${(v * 100).toFixed(1)}%`);

const WATCH_TEXT: Record<WatchStatus, { label: string; tone: string; text: string }> = {
  failing: { label: 'FAILING', tone: 'bad', text: 'The whole 95% interval of the failure rate is above your limit.' },
  uncertain: { label: 'UNCERTAIN', tone: 'warn', text: 'The interval straddles your limit: more evidence is needed.' },
  within: { label: 'WITHIN LIMIT', tone: 'ok', text: 'The whole interval is at or below your limit.' },
  unmeasured: { label: 'NOT MEASURED', tone: 'unchecked', text: 'This run produced no evidence for it.' },
};

const rate = (v: number | null | undefined) => (v === null || v === undefined ? 'n/a' : `${(v * 100).toFixed(1)}%`);

const WatchTable: React.FC<{ watch: WatchEntry[] }> = ({ watch }) => (
  <div className="tablewrap">
    <table className="table" data-testid="watch-table">
      <caption className="muted" style={{ textAlign: 'left', padding: '0 0 8px' }}>Failure rate seen in this evaluation against the limit in your policy.</caption>
      <thead><tr><th scope="col">Metric</th><th scope="col">Status</th><th scope="col">Failure rate (95% interval)</th><th scope="col">Your limit</th><th scope="col">Questions</th></tr></thead>
      <tbody>
        {watch.map((w) => (
          <tr key={w.metric}>
            <th scope="row">{metricLabel(w.metric)}{w.required ? '' : <span className="muted"> (optional)</span>}</th>
            <td><span className="badge" data-tone={WATCH_TEXT[w.status].tone} title={WATCH_TEXT[w.status].text}>{WATCH_TEXT[w.status].label}</span></td>
            <td>{w.status === 'unmeasured' ? 'not measured' : `${rate(w.failure_rate)} (${rate(w.failure_rate_ci?.[0])} to ${rate(w.failure_rate_ci?.[1])})`}</td>
            <td>{rate(w.appetite)}</td>
            <td>{w.n_roots}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

/** Readable summary of the plan. Internal ids and the markdown blob stay out of the view. */
export const PlanSummary: React.FC<{ plan: MonitoringPlan; onDownload: () => void }> = ({ plan, onDownload }) => {
  const rerun = plan.rerun ?? {};
  const thresholds = Object.entries(plan.thresholds ?? {});
  return (
    <div className="stack" data-testid="monitoring-plan">
      {plan.status && <Banner tone="info" role="status">{plan.status[0].toUpperCase()}{plan.status.slice(1)}.</Banner>}
      {plan.derived_from && (
        <p style={{ margin: 0 }} data-testid="plan-derived">
          Derived from this evaluation: {plan.derived_from.failed_items ?? 0} failed item(s)
          {Object.keys(plan.derived_from.failure_classes ?? {}).length > 0 && <> in {Object.entries(plan.derived_from.failure_classes!).map(([k, n]) => `${k} (${n})`).join(', ')}</>}
          , {plan.derived_from.unchecked_items ?? 0} item(s) not checked.
        </p>
      )}
      {(plan.unmeasured_required?.length ?? 0) > 0 && (
        <Banner tone="warn" role="status">
          <span data-testid="plan-unmeasured"><strong>Required but not measured:</strong> {plan.unmeasured_required!.map(metricLabel).join(', ')}. A release cannot be recommended on these until a run measures them.</span>
        </Banner>
      )}
      {(plan.attention?.length ?? 0) > 0 && (
        <Banner tone="bad" role="status">
          <span data-testid="plan-attention"><strong>Needs attention:</strong> {plan.attention!.map(metricLabel).join(', ')}.</span>
        </Banner>
      )}
      {(plan.watch?.length ?? 0) > 0 && (
        <div>
          <div className="h3">What to watch</div>
          <WatchTable watch={plan.watch!} />
        </div>
      )}
      <div>
        <div className="h3">What to re-run</div>
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          <li>{rerun.failed_items?.length ?? 0} failed question(s) from this evaluation</li>
          <li>{rerun.security_probes?.length ?? 0} security probe(s)</li>
          {rerun.regression_suite && <li>Every case in the project regression suite</li>}
        </ul>
      </div>
      <div>
        <div className="h3">When</div>
        <p style={{ margin: 0 }}>{plan.cadence_days ? `Every ${plan.cadence_days} day(s) (declared by you).` : 'No schedule is set. Choosing how often to re-run is your policy decision.'}</p>
        {(plan.drift_triggers?.length ?? 0) > 0 && (
          <>
            <p style={{ margin: '8px 0 0' }}>Also re-evaluate when any of these change:</p>
            <ul style={{ margin: 0, paddingLeft: 18 }}>{plan.drift_triggers!.map((t) => <li key={t}>{t.replace(/_/g, ' ')}</li>)}</ul>
          </>
        )}
      </div>
      <div>
        <div className="h3">Thresholds</div>
        {thresholds.length === 0 ? <p className="muted" style={{ margin: 0 }}>No thresholds are defined.</p> : (
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {thresholds.map(([m, t]) => (
              <li key={m}>{m.replace(/_/g, ' ')}: failure rate at most {pct(t.max_failure_rate)}{t.example ? ' (example policy, not your organisation’s own)' : ''}</li>
            ))}
          </ul>
        )}
        {plan.alert_rule && <p style={{ margin: '8px 0 0' }}>Alert rule: {plan.alert_rule}.</p>}
      </div>
      {plan.markdown && <div><button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={onDownload}>Download full plan (Markdown)</button></div>}
    </div>
  );
};

export const OperateStep: React.FC<{ project: Project; evaluation: Evaluation }> = ({ project, evaluation: ev }) => {
  const failed = ev.items.filter((i) => i.passed === false);
  const [picked, setPicked] = useState<string[]>([]);
  const [msg, setMsg] = useState<{ tone: 'ok' | 'bad'; text: string } | null>(null);
  const [plan, setPlan] = useState<MonitoringPlan | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [suite, setSuite] = useState<unknown>(null);

  const run = async (fn: () => Promise<void>, what: string) => {
    setMsg(null);
    try { await fn(); } catch (e) { setMsg({ tone: 'bad', text: describeError(e, what) }); }
  };

  const addRegression = () => run(async () => {
    await evaluationsApi.addRegression(ev.id, picked);
    setSuite(await projectsApi.regression(project.id).catch(() => null));
    setMsg({ tone: 'ok', text: `${picked.length} failing case(s) added to the regression suite. They will be re-run on future evaluations.` });
  }, 'the regression suite');

  const loadPlan = async () => {
    setPlanLoading(true);
    await run(async () => { setPlan(await evaluationsApi.monitoringPlan(ev.id)); }, 'the monitoring plan');
    setPlanLoading(false);
  };

  const dl = (kind: 'dataset' | 'report') => run(async () => {
    const text = kind === 'dataset' ? await evaluationsApi.dataset(ev.id) : await evaluationsApi.report(ev.id);
    downloadText(text, kind === 'dataset' ? `${ev.id}_dataset.jsonl` : `${ev.id}_report.md`);
  }, kind === 'dataset' ? 'dataset export' : 'report export');

  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const allSelected = failed.length > 0 && picked.length === failed.length;

  return (
    <div className="stack">
      {msg && <Banner tone={msg.tone} role={msg.tone === 'bad' ? 'alert' : 'status'}>{msg.text}</Banner>}

      <section className="panel stack" aria-labelledby="rg-h">
        <h2 className="h2" id="rg-h" style={{ margin: 0 }}>Keep failures from coming back</h2>
        <p className="muted" style={{ margin: 0 }}>Choose the failing cases worth guarding. They join a regression suite that every future evaluation re-asks. Nothing is selected for you.</p>
        {failed.length === 0 ? <div className="fempty">No failing items in this evaluation, nothing to add.</div> : (
          <>
            <div className="frow">
              <button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={() => setPicked(allSelected ? [] : failed.map((i) => i.id))}>
                {allSelected ? 'Clear selection' : 'Select all failures'}
              </button>
              <span className="muted" data-testid="picked-count">{picked.length} of {failed.length} selected</span>
            </div>
            <ul className="items">
              {failed.map((i) => (
                <li key={i.id} className="item" style={{ padding: '10px 14px' }}>
                  <label className="fcheck">
                    <input type="checkbox" checked={picked.includes(i.id)} onChange={() => toggle(i.id)} />
                    <span>{i.question} <span className="fchip">{sourceLabel(i.source)}</span>{i.failure_class ? <span className="muted"> ({i.failure_class})</span> : null}</span>
                  </label>
                </li>
              ))}
            </ul>
            <div><button type="button" className="fbtn" disabled={picked.length === 0} onClick={() => void addRegression()} data-testid="add-regression">Add {picked.length} to regression suite</button></div>
          </>
        )}
        {suite !== null && <details><summary>Current regression suite</summary><pre className="fmono" style={{ overflowX: 'auto' }}>{JSON.stringify(suite, null, 2)}</pre></details>}
      </section>

      <section className="panel stack" aria-labelledby="mp-h">
        <h2 className="h2" id="mp-h" style={{ margin: 0 }}>Monitoring plan</h2>
        <p className="muted" style={{ margin: 0 }}>What to watch after release, derived from the failures found.</p>
        {!plan && <div><button type="button" className="fbtn fbtn--ghost" onClick={() => void loadPlan()} disabled={planLoading}>Generate monitoring plan</button></div>}
        {planLoading && <Loading label="Building plan…" />}
        {plan && <PlanSummary plan={plan} onDownload={() => downloadText(plan.markdown ?? '', `${ev.id}_monitoring_plan.md`)} />}
      </section>

      <section className="panel stack" aria-labelledby="ex-h">
        <h2 className="h2" id="ex-h" style={{ margin: 0 }}>Export</h2>
        <div className="frow">
          <button type="button" className="fbtn fbtn--ghost" onClick={() => void dl('dataset')}>Download dataset (JSONL)</button>
          <button type="button" className="fbtn fbtn--ghost" onClick={() => void dl('report')}>Download report</button>
        </div>
      </section>
    </div>
  );
};
