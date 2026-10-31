import React from 'react';
import { fmtInterval } from '../../lib/campaign';
import { num, pct } from '../../lib/explain';
import { Banner } from '../../components/flow/ui';
import type { EvalItem } from '../../types/api';
import type { ClaimDetail, JudgeBlock } from '../../types/campaign';

const KIND_LABEL: Record<string, string> = { correctness: 'Answer correctness', faithfulness: 'Faithfulness' };

/** Evaluation Results: is the judge gating or advisory, how the panel agrees, what needs a human. */
export const JudgeSummary: React.FC<{ judge: JudgeBlock; items: EvalItem[] }> = ({ judge, items }) => {
  const reviewItems = items.filter((i) => judge.conflicts.includes(i.id));
  const corrected = Object.entries(judge.corrected ?? {});
  return (
    <section className="panel stack" aria-labelledby="jr-h" data-testid="judge-block">
      <div className="frow">
        <h2 className="h2" id="jr-h" style={{ margin: 0 }}>Semantic judge</h2>
        <span className="badge" data-tone={judge.gating ? 'ok' : 'warn'} data-testid="judge-role">{judge.gating ? 'GATING' : 'ADVISORY'}</span>
      </div>
      <p style={{ margin: 0 }} data-testid="judge-gate-reason">{judge.gate.reason}</p>
      <p className="field__hint" style={{ margin: 0 }}>
        {judge.gating
          ? 'The judge may change correctness and faithfulness verdicts because a fresh calibration met your policy minimum. Disagreements on checkable facts still go to a human.'
          : 'Shown for information. Verdicts and the recommendation come from the rule-based checks only.'}
        {judge.models.length > 0 && ` Judge: ${judge.models.join(', ')}.`}
      </p>
      {judge.panel && (
        <dl className="ffacts" data-testid="judge-panel">
          <dt>Panel agreement</dt><dd>{judge.panel.agreement === null ? 'not measured' : `${pct(judge.panel.agreement, 1)} over ${judge.panel.n_pairs} paired verdicts`}</dd>
          <dt>Cohen&apos;s kappa</dt><dd>{judge.panel.kappa === null ? 'not measured' : num(judge.panel.kappa, 2)}</dd>
          <dt>Disagreements</dt><dd>{judge.panel.disagreements}</dd>
          {judge.panel.same_family && <><dt>Note</dt><dd>Both judges are from the same model family, so they are less independent than two different families.</dd></>}
        </dl>
      )}
      {judge.conflicts.length > 0 ? (
        <Banner tone="warn" role="status">
          <span data-testid="judge-conflicts"><strong>{judge.conflicts.length} item{judge.conflicts.length === 1 ? '' : 's'} need human review.</strong> The judge and the rules disagree on a checkable fact, or the judges disagree with each other.
            {reviewItems.length > 0 && <> For example: {reviewItems.slice(0, 3).map((i) => `"${i.question.slice(0, 60)}"`).join('; ')}.</>}</span>
        </Banner>
      ) : <p className="muted" style={{ margin: 0 }}>No conflicts were sent to human review.</p>}
      {corrected.length > 0 && (
        <div className="tablewrap" data-testid="judge-corrected">
          <table className="table">
            <caption className="muted" style={{ textAlign: 'left', paddingBottom: 6 }}>Defect rates corrected for the judge&apos;s own measured error (interval includes that uncertainty)</caption>
            <thead><tr><th scope="col">Check</th><th scope="col">Judge-flagged</th><th scope="col">Corrected rate</th><th scope="col">Interval</th><th scope="col">Judged</th></tr></thead>
            <tbody>{corrected.map(([kind, c]) => (
              <tr key={kind}>
                <th scope="row">{KIND_LABEL[kind] ?? kind}</th>
                {c.corrected_defect_rate === undefined
                  ? <td colSpan={3}>Not computed: {c.reason ?? 'not enough calibration data'}</td>
                  : <><td>{pct(c.observed_defect_rate, 1)}</td><td>{pct(c.corrected_defect_rate, 1)}</td><td>{fmtInterval([c.ci_low ?? 0, c.ci_high ?? 0])}</td></>}
                <td>{c.n_judged}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
};

const CLAIM_TEXT: Record<string, string> = {
  supported: 'supported', unsupported: 'not supported', contradicted: 'contradicted', unverified: 'could not be verified',
};

/** Per-item judge detail: the judge's label, each claim, and the passage quote that backs it. */
export const ItemJudgeDetail: React.FC<{ item: EvalItem }> = ({ item }) => {
  const detail = item.detail as { judge?: Record<string, string>; judge_detail?: Record<string, { label?: string; labels?: Record<string, string>; claims?: ClaimDetail[]; needs_review?: string[] }>; judge_gating?: boolean; needs_review?: string[] } | null | undefined;
  const jd = detail?.judge_detail;
  if (!jd || Object.keys(jd).length === 0) return null;
  const needsReview = detail?.needs_review ?? [];
  const claims = jd.faithfulness?.claims ?? [];
  const corr = jd.correctness;
  return (
    <div data-testid="item-judge" className="stack" style={{ gap: 8 }}>
      <div className="frow">
        <span className="h3" style={{ margin: 0 }}>Semantic judge</span>
        <span className="badge" data-tone={detail?.judge_gating ? 'ok' : 'warn'}>{detail?.judge_gating ? 'GATING' : 'ADVISORY'}</span>
        {needsReview.length > 0 && <span className="badge" data-tone="bad" data-testid="item-needs-review">NEEDS HUMAN REVIEW</span>}
      </div>
      {needsReview.length > 0 && <ul style={{ margin: 0, paddingLeft: 18 }}>{needsReview.map((r) => <li key={r}>{r}</li>)}</ul>}
      {corr && (
        <p style={{ margin: 0 }}>
          Correctness: the judge says <strong>{corr.label ?? 'no opinion'}</strong>
          {corr.labels && Object.keys(corr.labels).length > 1 && <> (panel: {Object.entries(corr.labels).map(([m, l]) => `${m}: ${l}`).join('; ')})</>}.
        </p>
      )}
      {claims.length > 0 && (
        <div>
          <div className="h3">Claims in the answer ({claims.length})</div>
          <ul className="items">
            {claims.map((c, i) => (
              <li key={i} className="item" style={{ padding: '8px 12px' }}>
                <div className="frow" style={{ gap: 8 }}>
                  <span className="badge" data-tone={c.status === 'supported' ? 'ok' : c.status === 'unverified' ? 'unchecked' : 'bad'}>{CLAIM_TEXT[c.status] ?? c.status}</span>
                  {c.judge_disagrees && <span className="badge" data-tone="warn">JUDGE DISAGREES WITH RULES</span>}
                  {c.verifiable && <span className="fchip">checkable fact</span>}
                </div>
                <p style={{ margin: '6px 0 0' }}>{c.claim}</p>
                {c.quote ? <blockquote className="quote quote--ctx" style={{ margin: '6px 0 0' }}>{c.quote}</blockquote>
                  : <p className="field__hint" style={{ margin: '6px 0 0' }}>No supporting quote was found in the passages.</p>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
