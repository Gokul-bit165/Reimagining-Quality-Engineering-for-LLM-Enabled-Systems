import React from 'react';
import { describeTarget, fmtCost, fmtSeconds, fmtTokens } from '../../lib/campaign';
import { pct } from '../../lib/explain';
import { MetricCard, VerdictPanel } from '../../components/flow/ui';
import type { EvalMetric } from '../../types/api';
import type { Campaign, Performance, TargetResult } from '../../types/campaign';

const SCORE_TIPS: Record<string, string> = {
  accuracy: 'Share of answers that match the reference or are judged correct.',
  grounding: 'Share of answer claims supported by the retrieved passages.',
  completeness: 'Whether answers cover everything the question needs.',
  safety: 'Share of probes where the app stayed within safe behaviour.',
  consistency: 'How often repeated asks give the same answer.',
  security: 'Resistance to prompt injection and data leakage probes.',
};

const PerformanceBlock: React.FC<{ perf: Performance | undefined }> = ({ perf }) => {
  if (!perf) return <p className="muted" style={{ margin: 0 }}>Performance was not recorded.</p>;
  return (
    <dl className="ffacts" data-testid="performance">
      <dt>Latency p50 / p95 / p99</dt>
      <dd>{fmtSeconds(perf.latency_p50_s)} / {fmtSeconds(perf.latency_p95_s)} / {fmtSeconds(perf.latency_p99_s)}<span className="field__hint"> over successful calls only</span></dd>
      <dt>Error rate</dt>
      <dd>{perf.error_rate_calls === null ? 'not measured' : `${pct(perf.error_rate_calls, 1)} (${perf.errors} of ${perf.calls} calls)`}</dd>
      <dt>Tokens</dt><dd data-testid="perf-tokens">{fmtTokens(perf.tokens, perf.calls)}</dd>
      <dt>Cost</dt><dd data-testid="perf-cost">{fmtCost(perf.cost)}{perf.cost === null && perf.cost_note ? <span className="field__hint"> {perf.cost_note}</span> : null}</dd>
    </dl>
  );
};

/** One target: scorecard with intervals, decision (example policy flagged), per-risk rates, performance. */
export const TargetCard: React.FC<{ result: TargetResult; campaign: Campaign }> = ({ result: r, campaign }) => {
  const spec = campaign.targets.find((t) => t.label === r.label);
  const headline: Record<string, EvalMetric> = Object.keys(r.scorecard ?? {}).length > 0 ? r.scorecard! : (r.metrics ?? {});
  const decision = r.decision;
  const risks = Object.entries(r.per_risk ?? {});
  const meta = Object.entries(r.metadata ?? {});
  return (
    <article className="panel stack" aria-labelledby={`tr-${r.label}`} data-testid={`target-result-${r.label}`}>
      <div>
        <h2 className="h2" id={`tr-${r.label}`} style={{ margin: 0 }}>{r.label}</h2>
        <p className="muted" style={{ margin: '2px 0 0' }}>{spec ? describeTarget(spec) : r.kind}</p>
        {meta.length > 0 && <div className="chips" style={{ marginTop: 6 }}>{meta.map(([k, v]) => <span key={k} className="fchip">{k}={String(v)}</span>)}</div>}
      </div>

      {decision ? (
        <VerdictPanel verdict={decision.verdict} reasons={decision.reasons} pendingReview={decision.status === 'pending_review'}
          explanation={decision.explanation} policyExample={decision.policy_is_example} policy={decision.policy} />
      ) : <p className="muted" style={{ margin: 0 }}>No decision was produced for this target.</p>}
      {decision?.signoff && (
        <p className="badge" data-tone={decision.signoff.decision.startsWith('approve') ? 'ok' : 'bad'} data-testid={`signoff-record-${r.label}`} style={{ alignSelf: 'flex-start' }}>
          {decision.signoff.decision.startsWith('approve') ? 'APPROVED' : 'REJECTED'} BY {decision.signoff.reviewer}
        </p>
      )}

      <section aria-label={`Scorecard for ${r.label}`} className="stack" style={{ gap: 8 }}>
        <h3 className="h3" style={{ margin: 0 }}>Scorecard <span className="muted">(95% confidence intervals)</span></h3>
        {r.sample && <p className="muted" style={{ margin: 0 }} data-testid={`sample-${r.label}`}><strong>n_roots = {r.sample.n_roots}</strong> distinct questions, {r.sample.n_items} test items. Variants and repeats count once.</p>}
        {Object.keys(headline).length === 0 ? <div className="fempty">No metrics were produced.</div>
          : <div className="grid2">{Object.entries(headline).map(([k, m]) => <MetricCard key={k} name={k} m={m} tip={SCORE_TIPS[k]} />)}</div>}
      </section>

      {risks.length > 0 && (
        <section aria-label={`Pass rate per risk for ${r.label}`}>
          <h3 className="h3">Pass rate by risk</h3>
          <div className="tablewrap">
            <table className="table">
              <thead><tr><th scope="col">Risk</th><th scope="col">Pass rate (95% CI)</th><th scope="col">n_roots</th></tr></thead>
              <tbody>{risks.map(([k, v]) => (
                <tr key={k}><th scope="row" style={{ textTransform: 'capitalize' }}>{k.replace(/_/g, ' ')}</th>
                  <td>{pct(v.rate, 1)} ({pct(v.ci_low, 1)} to {pct(v.ci_high, 1)}){v.note && <span className="field__hint"> {v.note}</span>}</td><td>{v.n_roots}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </section>
      )}

      <section aria-label={`Performance of ${r.label}`}>
        <h3 className="h3">Performance</h3>
        <PerformanceBlock perf={r.performance} />
      </section>
    </article>
  );
};

export const TargetResults: React.FC<{ campaign: Campaign }> = ({ campaign }) => {
  const labels = campaign.targets.map((t) => t.label);
  const have = labels.filter((l) => campaign.results[l]);
  if (have.length === 0) return <div className="fempty">Results appear once scoring (stage 6) finishes.</div>;
  return <div className="stack" data-testid="target-results">{have.map((l) => <TargetCard key={l} result={campaign.results[l]} campaign={campaign} />)}</div>;
};
