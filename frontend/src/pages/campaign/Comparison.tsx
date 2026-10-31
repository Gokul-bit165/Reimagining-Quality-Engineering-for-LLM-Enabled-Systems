import React, { useMemo } from 'react';
import { OUTCOME_TEXT, buildMetricTable, explainPair, fmtDiff, fmtP, fmtRate } from '../../lib/campaign';
import { metricLabel } from '../../lib/policy';
import { Banner, Tip } from '../../components/flow/ui';
import type { Campaign } from '../../types/campaign';

export const RecommendationPanel: React.FC<{ campaign: Campaign }> = ({ campaign }) => {
  const rec = campaign.recommendation;
  if (!rec) return null;
  const winner = rec.better_target;
  return (
    <section className="panel stack" aria-labelledby="rec-h" data-testid="recommendation" data-winner={winner ?? 'none'}>
      <h2 className="h2" id="rec-h" style={{ margin: 0 }}>Recommendation</h2>
      {winner ? (
        <>
          <p style={{ margin: 0, fontSize: 18, fontWeight: 600 }} data-testid="rec-winner">{winner} is supported as the better target.</p>
          <p style={{ margin: 0 }}>{rec.summary.charAt(0).toUpperCase() + rec.summary.slice(1)}</p>
        </>
      ) : (
        <>
          <p style={{ margin: 0, fontSize: 18, fontWeight: 600 }} data-testid="rec-none">No target is established as better.</p>
          <p style={{ margin: 0 }}>{rec.summary.charAt(0).toUpperCase() + rec.summary.slice(1)}</p>
        </>
      )}
      <div className="chips" aria-label="Policy decision per target">
        {Object.entries(rec.decisions).map(([label, v]) => <span key={label} className="fchip">{label}: {v.replace('_', ' ')}</span>)}
      </div>
      {rec.caveats.length > 0 && (
        <Banner tone="warn" role="status">
          <div data-testid="rec-caveats"><strong>Caveats</strong>
            <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>{rec.caveats.map((c) => <li key={c}>{c}</li>)}</ul></div>
        </Banner>
      )}
      <p className="field__hint" style={{ margin: 0 }}>Computed by fixed rules from the paired tests, not by a language model. Better than the others is not the same as safe to release: each target&apos;s own policy decision still applies.</p>
    </section>
  );
};

export const Comparison: React.FC<{ campaign: Campaign }> = ({ campaign }) => {
  const labels = useMemo(() => campaign.targets.map((t) => t.label).filter((l) => campaign.results[l]), [campaign]);
  const table = useMemo(() => buildMetricTable(campaign.results, labels), [campaign.results, labels]);
  const cmp = campaign.comparisons;
  if (labels.length === 0) return <div className="fempty">The comparison appears once scoring finishes.</div>;
  const single = labels.length < 2;
  return (
    <div className="stack" data-testid="comparison">
      <section className="panel stack" aria-labelledby="cmp-h">
        <div>
          <h2 className="h2" id="cmp-h" style={{ margin: 0 }}>Side by side</h2>
          <p className="muted" style={{ margin: '4px 0 0' }}>Each cell is a pass rate over distinct questions with its 95% confidence interval. Overlapping intervals mean the difference may be noise: read the paired tests below before concluding anything.</p>
        </div>
        <div className="tablewrap">
          <table className="table ctable" data-testid="metric-table">
            <thead><tr><th scope="col">Metric</th>{labels.map((l) => <th key={l} scope="col">{l}</th>)}</tr></thead>
            <tbody>
              {table.map((row) => (
                <tr key={row.metric}>
                  <th scope="row">{metricLabel(row.metric)}</th>
                  {row.cells.map((c) => {
                    const m = c.metric;
                    const roots = m ? (m.n_roots ?? m.n) : 0;
                    return (
                      <td key={c.label} data-testid={`cell-${row.metric}-${c.label}`}>
                        <div>{fmtRate(m)}</div>
                        <div className="field__hint">{m ? `n_roots = ${roots}` : 'not reported for this target'}</div>
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr>
                <th scope="row">Latency p50 / p95</th>
                {labels.map((l) => { const p = campaign.results[l].performance; return <td key={l}>{p?.latency_p50_s == null ? 'not measured' : `${p.latency_p50_s.toFixed(2)} s / ${p.latency_p95_s?.toFixed(2) ?? 'n/a'} s`}</td>; })}
              </tr>
              <tr>
                <th scope="row">Policy decision</th>
                {labels.map((l) => <td key={l}>{campaign.results[l].decision?.verdict.replace('_', ' ') ?? 'none'}{campaign.results[l].decision?.policy_is_example ? <span className="field__hint"> example policy</span> : null}</td>)}
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {single ? (
        <Banner tone="info" role="status">This campaign has one target, so there is nothing to compare. Start another campaign with two or more targets to benchmark them.</Banner>
      ) : cmp && cmp.pairs.length > 0 ? (
        <section className="panel stack" aria-labelledby="pair-h" data-testid="pair-table-section">
          <div>
            <h2 className="h2" id="pair-h" style={{ margin: 0 }}>Paired comparisons <Tip text="Both targets answer the same questions, so each question is a pair. The tests look only at questions where the two disagree." /></h2>
            <p className="muted" style={{ margin: '4px 0 0' }}>A is the first target in each row, B the second. The difference is A minus B in percentage points, with a 95% interval.</p>
          </div>
          <Banner tone="warn" role="status">
            <span data-testid="multiplicity-caution"><strong>Many tests, one decision.</strong> {cmp.multiplicity}. Reading the unadjusted p-value alone would find &quot;winners&quot; by chance. The label uses the adjusted p-value against alpha = {cmp.alpha}, and a significant result still depends on the questions you chose.</span>
          </Banner>
          <div className="tablewrap">
            <table className="table" data-testid="pair-table">
              <thead><tr><th scope="col">Metric</th><th scope="col">A vs B</th><th scope="col">Outcome</th><th scope="col">Difference (95% CI)</th><th scope="col">Adjusted p</th><th scope="col">Pairs</th></tr></thead>
              <tbody>
                {cmp.pairs.map((p) => {
                  const o = OUTCOME_TEXT[p.outcome];
                  return (
                    <React.Fragment key={`${p.a}-${p.b}-${p.metric}`}>
                      <tr data-testid={`pair-${p.metric}`} data-outcome={p.outcome}>
                        <th scope="row">{metricLabel(p.metric)}</th>
                        <td>{p.a} vs {p.b}</td>
                        <td><span className="badge" data-tone={o.tone === 'ok' ? 'ok' : o.tone === 'warn' ? 'warn' : p.outcome === 'NOT_MEASURABLE' ? 'unchecked' : undefined}>{(p.winner ? `${p.winner} is better` : o.label).toUpperCase()}</span></td>
                        <td>{fmtDiff(p)}</td>
                        <td>{fmtP(p.p_adjusted)}</td>
                        <td>{p.n_pairs}</td>
                      </tr>
                      <tr className="explain-row"><td colSpan={6} className="field__hint">{explainPair(p)}{p.note && (p.outcome === 'A_BETTER' || p.outcome === 'B_BETTER') ? ` ${p.note}.` : ''}</td></tr>
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="field__hint" style={{ margin: 0 }}>{cmp.pairs.find((p) => p.ci_method)?.ci_method ?? ''}{cmp.pairs.find((p) => p.test) ? `; ${cmp.pairs.find((p) => p.test)!.test}` : ''}.</p>
        </section>
      ) : <Banner tone="info" role="status">{cmp?.note ?? 'No paired comparison was produced yet.'}</Banner>}

      <RecommendationPanel campaign={campaign} />
    </div>
  );
};
