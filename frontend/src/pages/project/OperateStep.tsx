import React, { useState } from 'react';
import { describeError } from '../../api';
import { evaluationsApi, projectsApi } from '../../lib/projects';
import { downloadText } from '../../utils/reportExporter';
import { Banner, Loading } from '../../components/flow/ui';
import type { Evaluation, MonitoringPlan, Project } from '../../types/api';

function renderValue(v: unknown): React.ReactNode {
  if (Array.isArray(v)) return <ul style={{ margin: 0, paddingLeft: 18 }}>{v.map((x, i) => <li key={i}>{renderValue(x)}</li>)}</ul>;
  if (v && typeof v === 'object') {
    return (
      <dl className="ffacts">
        {Object.entries(v as Record<string, unknown>).map(([k, x]) => (<React.Fragment key={k}><dt>{k.replace(/_/g, ' ')}</dt><dd>{renderValue(x)}</dd></React.Fragment>))}
      </dl>
    );
  }
  return String(v ?? '');
}

export const OperateStep: React.FC<{ project: Project; evaluation: Evaluation }> = ({ project, evaluation: ev }) => {
  const failed = ev.items.filter((i) => i.passed === false);
  const [picked, setPicked] = useState<string[]>(failed.map((i) => i.id));
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

  return (
    <div className="stack">
      {msg && <Banner tone={msg.tone} role={msg.tone === 'bad' ? 'alert' : 'status'}>{msg.text}</Banner>}

      <section className="panel stack" aria-labelledby="rg-h">
        <h2 className="h2" id="rg-h" style={{ margin: 0 }}>Keep failures from coming back</h2>
        <p className="muted" style={{ margin: 0 }}>Add failing cases to a regression suite so every future change is checked against them.</p>
        {failed.length === 0 ? <div className="fempty">No failing items in this evaluation, nothing to add.</div> : (
          <>
            <ul className="items">
              {failed.map((i) => (
                <li key={i.id} className="item" style={{ padding: '10px 14px' }}>
                  <label className="fcheck"><input type="checkbox" checked={picked.includes(i.id)} onChange={() => toggle(i.id)} /><span>{i.question}{i.failure_class ? ` (${i.failure_class})` : ''}</span></label>
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
        {plan && <div data-testid="monitoring-plan">{renderValue(plan)}</div>}
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
