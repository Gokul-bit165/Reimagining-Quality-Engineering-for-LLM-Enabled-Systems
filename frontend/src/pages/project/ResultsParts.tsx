import React, { useMemo, useState } from 'react';
import { FAILURE_REASON_TEXT, num, pct } from '../../lib/explain';
import { SOURCE_INFO, sourceLabel } from '../../lib/provenance';
import { loadChoice, metricLabel, parsePercent } from '../../lib/policy';
import { CONTEXTS_KIND_TEXT } from '../../lib/targetConfig';
import { projectHref } from '../../lib/route';
import { Banner } from '../../components/flow/ui';
import { ItemJudgeDetail } from './JudgeResults';
import type { ContextsKind, EvalItem, EvalMetric, Evaluation } from '../../types/api';

const JUDGE_KEYS = ['judge_correct_untrusted', 'judge_advisory'];

export const isAdvisoryItem = (i: EvalItem): boolean => Boolean(i.lineage?.advisory && !i.lineage?.confirmed);

const passWord = (v: boolean | null) => (v === null ? 'not checked' : v ? 'pass' : 'fail');

/** null is "not measured", never zero and never a failure. */
export function fmtScore(v: EvalItem['scores'][string]): string {
  if (v === null || v === undefined) return 'not measured';
  if (typeof v === 'boolean') return passWord(v);
  if (Array.isArray(v)) return v.map((x) => (typeof x === 'number' ? num(x) : passWord(x))).join(' / ');
  return num(v);
}

const SKIP_DETAIL = ['contexts_kind'];

function detailLines(d: EvalItem['detail']): string[] {
  if (!d) return [];
  return Object.entries(d).filter(([k]) => !SKIP_DETAIL.includes(k)).flatMap(([k, v]) => {
    const name = k.replace(/_/g, ' ');
    if (Array.isArray(v)) return v.map((x) => `${name}: ${String(x)}`);
    if (v === null || v === undefined || v === '') return [];
    return [`${name}: ${String(v)}`];
  });
}

function judgeText(v: EvalItem['scores'][string]): string {
  if (v === true) return 'The model judge thought the answer was correct.';
  if (v === false) return 'The model judge thought the answer was not correct.';
  return 'The model judge gave no opinion.';
}

export const ItemRow: React.FC<{ item: EvalItem }> = ({ item }) => {
  const [open, setOpen] = useState(false);
  const bodyId = `item-${item.id}`;
  const kind = (item.detail?.contexts_kind ?? null) as ContextsKind | null;
  const unchecked = item.passed === null;
  const judge = JUDGE_KEYS.find((k) => k in item.scores);
  const scoreEntries = Object.entries(item.scores).filter(([k]) => !JUDGE_KEYS.includes(k));
  const lines = detailLines(item.detail);
  return (
    <li className="item" data-testid="eval-item" data-passed={String(item.passed)}>
      <button type="button" className="item__head" aria-expanded={open} aria-controls={bodyId} onClick={() => setOpen(!open)}>
        <span className="badge" data-tone={item.passed === true ? 'ok' : item.passed === false ? 'bad' : 'unchecked'}>
          {item.passed === true ? 'PASS' : item.passed === false ? 'FAIL' : 'NOT CHECKED'}
        </span>
        {isAdvisoryItem(item) && <span className="badge" data-tone="warn" title="Written by a model; excluded from the decision until a human confirms it">ADVISORY</span>}
        <span className="item__q">{item.question}</span>
        <span className="fchip" title={SOURCE_INFO[item.source]?.text}>{sourceLabel(item.source)}</span>
        <span className="material-symbols-outlined" aria-hidden="true">{open ? 'expand_less' : 'expand_more'}</span>
      </button>
      {open && (
        <div className="item__body" id={bodyId}>
          {unchecked && (
            <Banner tone="info"><span><strong>Not checked.</strong> This item has no reference answer and was not marked answerable or not answerable, so it cannot be scored. It is left out of every rate: it is neither a pass nor a failure.</span></Banner>
          )}
          {item.failure_reason && <Banner tone="bad"><span><strong>Why it failed{item.failure_class ? ` (${item.failure_class})` : ''}:</strong> {FAILURE_REASON_TEXT[item.failure_reason] ?? item.failure_reason}</span></Banner>}
          {(lines.length > 0 || kind) && (
            <div>
              <div className="h3">Evidence</div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {kind && <li data-testid="contexts-kind">Retrieved contexts: {CONTEXTS_KIND_TEXT[kind]}</li>}
                {lines.map((l, i) => <li key={i}>{l}</li>)}
              </ul>
            </div>
          )}
          <div><div className="h3">Question <span className="muted">({sourceLabel(item.source)})</span></div><p className="quote">{item.question}</p>
            <p className="field__hint">{SOURCE_INFO[item.source]?.text}</p></div>
          <div><div className="h3">Reference answer</div><p className="quote">{item.reference_answer ?? 'None provided'}</p></div>
          <div><div className="h3">App answer</div><p className="quote">{item.answer ?? 'No answer produced (code was not executed, or the call failed).'}</p></div>
          <div>
            <div className="h3">Retrieved contexts ({item.contexts.length})</div>
            {item.contexts.length === 0 ? <p className="muted">No passages were retrieved.</p>
              : item.contexts.map((c, i) => <p key={i} className="quote quote--ctx">{c}</p>)}
          </div>
          {judge && (
            <div data-testid="judge-advisory">
              <div className="h3">Model judge <span className="badge" data-tone="warn">ADVISORY</span></div>
              <p className="muted" style={{ margin: 0 }}>{judgeText(item.scores[judge])} This opinion is shown for information only and never changes the pass/fail result or the recommendation.</p>
            </div>
          )}
          <ItemJudgeDetail item={item} />
          {scoreEntries.length > 0 && (
            <div className="frow">{scoreEntries.map(([k, v]) => <span key={k} className="score">{k.replace(/_/g, ' ')}: {fmtScore(v)}</span>)}</div>
          )}
        </div>
      )}
    </li>
  );
};

const SECONDS = ['latency_p50_s', 'latency_p95_s'];

function metricRow(name: string, m: EvalMetric) {
  const seconds = SECONDS.includes(name);
  const known = m.value !== null && m.value !== undefined;
  const value = !known ? 'not measured' : seconds ? `${m.value!.toFixed(2)} s` : pct(m.value, 1);
  const ci = !seconds && known && m.ci_low !== null && m.ci_high !== null ? `${pct(m.ci_low, 1)} to ${pct(m.ci_high, 1)}` : 'n/a';
  return { name, value, ci, roots: seconds ? m.n : (m.n_roots ?? m.n), items: m.n_items ?? m.n, note: m.note ?? '' };
}

/** Every metric the engine produced, including ones the headline scorecard hides. */
export const AllMetrics: React.FC<{ metrics: Record<string, EvalMetric> }> = ({ metrics }) => {
  const rows = Object.entries(metrics).map(([k, m]) => metricRow(k, m));
  if (rows.length === 0) return null;
  return (
    <details data-testid="all-metrics">
      <summary className="h3" style={{ cursor: 'pointer' }}>All metrics ({rows.length})</summary>
      <div className="tablewrap">
        <table className="table">
          <thead><tr><th scope="col">Metric</th><th scope="col">Value</th><th scope="col">95% interval</th><th scope="col">Distinct questions</th><th scope="col">Items</th><th scope="col">Note</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name}>
                <th scope="row">{metricLabel(r.name)}</th><td>{r.value}</td><td>{r.ci}</td><td>{r.roots}</td><td>{r.items}</td><td>{r.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
};

/** "N distinct questions, M test items" and how many could not be checked. */
export const SampleSummary: React.FC<{ ev: Evaluation; projectId: string }> = ({ ev, projectId }) => {
  const sample = ev.sample ?? { n_roots: new Set(ev.items.map((i) => i.lineage?.parent ?? i.id)).size, n_items: ev.items.length };
  const unchecked = ev.unchecked?.count ?? ev.items.filter((i) => i.passed === null).length;
  return (
    <div className="stack" style={{ gap: 8 }}>
      <p style={{ margin: 0 }} data-testid="sample-summary">
        <strong>{sample.n_roots} distinct question{sample.n_roots === 1 ? '' : 's'}</strong>, {sample.n_items} test item{sample.n_items === 1 ? '' : 's'}.
        <span className="muted"> Variants and repeats of a question count once in every interval.</span>
      </p>
      {unchecked > 0 && (
        <Banner tone="info" role="status">
          <span data-testid="unchecked-banner"><strong>{unchecked} item{unchecked === 1 ? '' : 's'} not checked.</strong> They have no reference answer and no answerable setting, so they are excluded from every rate (not counted as passes).{' '}
            <a href={projectHref(projectId, 'inputs')}>Set answerable in Inputs</a> to include them next time.</span>
        </Banner>
      )}
      {(ev.advisory?.unconfirmed ?? 0) > 0 && (
        <Banner tone="warn" role="status"><span><strong>{ev.advisory!.unconfirmed} generated item{ev.advisory!.unconfirmed === 1 ? ' is' : 's are'} advisory.</strong> They are scored and shown but excluded from the recommendation until a human confirms them.</span></Banner>
      )}
    </div>
  );
};

/** The policy the decision was made under, flagged when it is the illustrative example. */
export const PolicyUsed: React.FC<{ ev: Evaluation; projectId: string }> = ({ ev, projectId }) => {
  const d = ev.decision;
  const stored = useMemo(() => loadChoice(projectId), [projectId]);
  if (!d) return null;
  const example = Boolean(d.policy_is_example);
  const local = !example && stored.mode === 'custom' && `${stored.draft.policyId.trim()}@${stored.draft.version.trim()}` === d.policy ? stored.draft : null;
  const limits = local ? Object.entries(local.required).filter(([, on]) => on).map(([m]) => ({ m, p: parsePercent(local.maxPct[m] ?? '') })) : [];
  return (
    <section className="panel stack" aria-labelledby="pu-h" data-testid="policy-used">
      <div className="frow">
        <h2 className="h2" id="pu-h" style={{ margin: 0 }}>Policy used</h2>
        {example && <span className="badge" data-tone="warn" data-testid="policy-example-badge">EXAMPLE POLICY</span>}
      </div>
      <p style={{ margin: 0 }}>{d.policy ?? 'Unnamed policy'}{example ? '. Illustrative thresholds, not a real risk appetite: treat this recommendation as a demonstration.' : '.'}</p>
      {limits.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {limits.map(({ m, p }) => <li key={m}>{metricLabel(m)}: failure rate at most {p === null ? 'not set' : `${p}%`}</li>)}
        </ul>
      ) : !example && <p className="muted" style={{ margin: 0 }}>The limits were set in another browser or session, so they are not shown here. The monitoring plan lists the thresholds.</p>}
      {ev.params && (
        <p className="field__hint" style={{ margin: 0 }}>
          Run settings: up to {ev.params.max_questions} items, {ev.params.repeats} repeat{ev.params.repeats === 1 ? '' : 's'}, security probes {ev.params.include_security ? 'on' : 'off'}.
        </p>
      )}
    </section>
  );
};
