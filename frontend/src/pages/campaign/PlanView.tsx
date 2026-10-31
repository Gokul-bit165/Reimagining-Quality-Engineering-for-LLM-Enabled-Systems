import React, { useMemo } from 'react';
import { describeError } from '../../api';
import { COVERAGE_TEXT, campaignsApi, groupCasesByScenario, planToJson } from '../../lib/campaign';
import { usePoll } from '../../hooks/usePoll';
import { Banner, Loading } from '../../components/flow/ui';
import type { Campaign, Plan } from '../../types/campaign';

function downloadJson(text: string, filename: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const scenarioName = (s: string | null | undefined) => (s ? s.replace(/_/g, ' ') : 'unmapped label');

const CoverageMatrix: React.FC<{ plan: Plan }> = ({ plan }) => {
  const rows = plan.coverage.matrix;
  const gaps = rows.filter((r) => r.status !== 'COVERED');
  return (
    <section className="panel stack" aria-labelledby="cov-mh" data-testid="coverage-matrix">
      <div>
        <h2 className="h2" id="cov-mh" style={{ margin: 0 }}>Coverage matrix</h2>
        <p className="muted" style={{ margin: '4px 0 0' }}>Which risks have tests. A gap is shown as a gap, with the reason: untested risks are never reported as passing.</p>
      </div>
      <ul className="chips" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {(['COVERED', 'CHECK_ONLY', 'GAP'] as const).map((s) => <li key={s} className="fchip">{COVERAGE_TEXT[s].label}: {rows.filter((r) => r.status === s).length}</li>)}
      </ul>
      <div className="tablewrap">
        <table className="table covtable">
          <thead><tr><th scope="col">Risk</th><th scope="col">Status</th><th scope="col">Tests</th><th scope="col">How it is checked</th><th scope="col">Why / notes</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.risk_id ?? r.label}-${i}`} data-testid={`cov-${r.scenario ?? 'unmapped'}`}>
                <th scope="row" style={{ textTransform: 'capitalize' }}>{scenarioName(r.scenario ?? r.label)}</th>
                <td><span className="badge" data-tone={r.status === 'COVERED' ? 'ok' : r.status === 'GAP' ? 'bad' : 'warn'} title={COVERAGE_TEXT[r.status]?.text}>{r.status.replace('_', ' ')}</span></td>
                <td>{r.n_tests}</td>
                <td>{r.oracle_types.length ? r.oracle_types.join(', ') : 'none'}{Object.keys(r.operators).length > 0 && <span className="field__hint"> operators: {Object.entries(r.operators).map(([k, v]) => `${k} ${v}`).join(', ')}</span>}</td>
                <td>{r.gap_reason || (r.taxonomy_ids.length ? <span className="muted">{r.taxonomy_ids.join(', ')}</span> : '')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {gaps.length > 0 && <Banner tone="warn" role="status"><span><strong>{gaps.length} risk{gaps.length === 1 ? ' is' : 's are'} not fully covered.</strong> The results say nothing about them.</span></Banner>}
    </section>
  );
};

/** The generated or imported plan: risks, cases grouped by scenario, coverage, and JSON export. */
export const PlanView: React.FC<{ campaign: Campaign }> = ({ campaign }) => {
  const ready = campaign.stages.test_plan?.status === 'done';
  const planState = usePoll<Plan | null>(() => (ready ? campaignsApi.plan(campaign.id) : Promise.resolve(null)), () => false, [campaign.id, ready]);
  const plan = planState.data;
  const groups = useMemo(() => (plan ? groupCasesByScenario(plan.cases) : []), [plan]);

  if (!ready) return <div className="fempty">The plan is built in stage 2. It appears here when that stage finishes.</div>;
  if (planState.loading && !plan) return <Loading label="Loading the plan…" />;
  if (!plan) return <Banner tone="bad" role="alert">Could not load the plan. {describeError(planState.error, 'the plan')}</Banner>;

  return (
    <div className="stack" data-testid="plan-view">
      <section className="panel stack" aria-labelledby="pl-h">
        <div className="frow frow--between">
          <h2 className="h2" id="pl-h" style={{ margin: 0 }}>Test plan <span className="muted">{plan.plan_id}</span></h2>
          <button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={() => downloadJson(planToJson(plan), `test-plan-${plan.plan_id}.json`)} data-testid="export-plan">
            <span className="material-symbols-outlined" aria-hidden="true">download</span>Export plan JSON
          </button>
        </div>
        <p style={{ margin: 0 }} data-testid="plan-authoring">{plan.authoring.statement}</p>
        <p className="field__hint" style={{ margin: 0 }}>
          {plan.cases.length} case{plan.cases.length === 1 ? '' : 's'}, each asked {plan.repeats} time{plan.repeats === 1 ? '' : 's'} per target · source: {plan.source} · seed {plan.seed}.
          Export the plan, edit it, and import it into a new campaign to rerun exactly the cases you want.
        </p>
        {plan.notes.length > 0 && <ul className="muted" style={{ margin: 0, paddingLeft: 18 }}>{plan.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
      </section>

      <section className="panel stack" aria-labelledby="rk-h">
        <h2 className="h2" id="rk-h" style={{ margin: 0 }}>Risks ({plan.risks.length})</h2>
        <ul className="items">
          {plan.risks.map((r) => (
            <li key={r.id} className="item" style={{ padding: '10px 14px' }}>
              <div className="frow" style={{ gap: 8 }}><strong style={{ textTransform: 'capitalize' }}>{r.label}</strong>{r.taxonomy.map((t) => <span key={`${t.taxonomy}:${t.id}`} className="fchip" title={t.title}>{t.id}</span>)}</div>
              <p className="muted" style={{ margin: '2px 0 0' }}>{r.rationale} <span className="field__hint">From: {r.sources.join(', ')}.</span></p>
            </li>
          ))}
        </ul>
        {plan.unmapped.length > 0 && <Banner tone="warn" role="status"><span>{plan.unmapped.length} label{plan.unmapped.length === 1 ? '' : 's'} could not be mapped to a test scenario: {plan.unmapped.map((u) => u.label).join(', ')}.</span></Banner>}
      </section>

      <CoverageMatrix plan={plan} />

      <section className="panel stack" aria-labelledby="cs-h">
        <h2 className="h2" id="cs-h" style={{ margin: 0 }}>Cases by scenario</h2>
        {groups.map((g) => (
          <details key={g.scenario} style={{ border: '1px solid var(--c-line)', borderRadius: 'var(--r-md)', padding: '0 14px' }} data-testid={`cases-${g.scenario}`}>
            <summary className="h3" style={{ cursor: 'pointer', margin: 0, minHeight: 40, display: 'flex', alignItems: 'center', textTransform: 'capitalize' }}>{scenarioName(g.scenario)} ({g.cases.length})</summary>
            <ul style={{ listStyle: 'none', margin: '0 0 8px', padding: 0 }}>
              {g.cases.map((c) => (
                <li key={c.id} style={{ padding: '8px 0', borderTop: '1px solid var(--c-line)' }}>
                  <p style={{ margin: 0 }}>{c.question}</p>
                  <div className="frow" style={{ gap: 6, marginTop: 4 }}>
                    <span className="fchip">{c.source}</span>
                    {c.oracles.map((o) => <span key={o} className="fchip">{o}</span>)}
                    {c.lineage?.advisory && <span className="badge" data-tone="warn">ADVISORY</span>}
                  </div>
                  <p className="field__hint" style={{ margin: '4px 0 0' }}>Expected: {c.expected_evidence}</p>
                </li>
              ))}
            </ul>
          </details>
        ))}
      </section>
    </div>
  );
};
