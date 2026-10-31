import React, { useId } from 'react';
import type { EvalMetric, Verdict } from '../../types/api';
import { VERDICT_INFO, pct } from '../../lib/explain';

export const Tip: React.FC<{ text: string; label?: string }> = ({ text, label = 'More information' }) => {
  const id = useId();
  return (
    <span className="tip">
      <button type="button" className="tip__btn" aria-label={label} aria-describedby={id}>?</button>
      <span role="tooltip" id={id} className="tip__body">{text}</span>
    </span>
  );
};

export const Banner: React.FC<{
  tone: 'warn' | 'bad' | 'info' | 'ok';
  children: React.ReactNode;
  role?: 'alert' | 'status';
}> = ({ tone, children, role }) => (
  <div className="banner" data-tone={tone} role={role}>{children}</div>
);

export const Loading: React.FC<{ label: string }> = ({ label }) => (
  <p className="muted frow" role="status"><span className="spinner" aria-hidden="true" />{label}</p>
);

export const Field: React.FC<{
  label: string;
  hint?: string;
  tip?: string;
  error?: string | null;
  htmlFor: string;
  children: React.ReactNode;
}> = ({ label, hint, tip, error, htmlFor, children }) => (
  <div className="field">
    <label className="field__label" htmlFor={htmlFor}>{label}{tip && <Tip text={tip} label={`About ${label}`} />}</label>
    {children}
    {hint && <span className="field__hint" id={`${htmlFor}-hint`}>{hint}</span>}
    {error && <span className="field__error" role="alert">{error}</span>}
  </div>
);

/** Point estimate is always shown with its interval and n. Never a bare number. */
export const CiBar: React.FC<{ m: EvalMetric }> = ({ m }) => {
  if (m.value === null || m.ci_low === null || m.ci_high === null) return null;
  const lo = Math.max(0, Math.min(1, m.ci_low)) * 100;
  const hi = Math.max(0, Math.min(1, m.ci_high)) * 100;
  const v = Math.max(0, Math.min(1, m.value)) * 100;
  return (
    <div className="ci" aria-hidden="true">
      <div className="ci__range" style={{ left: `${lo}%`, width: `${Math.max(hi - lo, 1)}%` }} />
      <div className="ci__point" style={{ left: `calc(${v}% - 1px)` }} />
    </div>
  );
};

export const MetricCard: React.FC<{ name: string; m: EvalMetric; tip?: string }> = ({ name, m, tip }) => {
  const known = m.value !== null && m.ci_low !== null && m.ci_high !== null;
  const roots = m.n_roots ?? m.n;
  const items = m.n_items ?? roots;
  return (
    <div className="fmetric" data-testid={`metric-${name}`}>
      <div className="fmetric__name">{name.replace(/_/g, ' ')}{tip && <Tip text={tip} label={`About ${name}`} />}</div>
      {known ? (
        <>
          <div className="fmetric__val">{pct(m.value, 1)}</div>
          <CiBar m={m} />
          <div className="fmetric__ci">95% CI {pct(m.ci_low, 1)} to {pct(m.ci_high, 1)} · n={roots}{items !== roots ? ` questions from ${items} items` : ' questions'}</div>
        </>
      ) : (
        <>
          <div className="fmetric__val" style={{ fontSize: 16 }}>Not measured</div>
          <div className="fmetric__ci">n={roots} questions. Nothing to measure here, so no interval.</div>
        </>
      )}
      {m.note && <div className="field__hint">{m.note}</div>}
    </div>
  );
};

export const VerdictPanel: React.FC<{
  verdict: Verdict;
  reasons: string[];
  pendingReview?: boolean;
  explanation?: string | null;
  policyExample?: boolean;
  policy?: string | null;
}> = ({ verdict, reasons, pendingReview, explanation, policyExample, policy }) => {
  const info = VERDICT_INFO[verdict];
  return (
    <section className="verdict" data-tone={info.tone} data-testid="verdict" aria-label="Release recommendation">
      <div className="frow">
        <span className="h3" style={{ margin: 0 }}>Release recommendation</span>
        {pendingReview && <span className="badge" data-tone="warn">PENDING HUMAN REVIEW</span>}
      </div>
      <h2 className="verdict__name">{verdict === 'INSUFFICIENT_EVIDENCE' ? 'INSUFFICIENT EVIDENCE' : info.label.toUpperCase()}</h2>
      <p className="muted" style={{ color: 'inherit', margin: 0 }}>{info.text}</p>
      {explanation && <p style={{ margin: '8px 0 0', fontSize: 14 }}>{explanation}</p>}
      {policyExample && (
        <p className="field__hint" style={{ margin: '8px 0 0', color: 'inherit' }} data-testid="example-policy">
          Policy {policy ?? ''} is an EXAMPLE policy, not your organisation&apos;s real risk appetite. Treat this recommendation as illustrative.
        </p>
      )}
      {reasons.length > 0 && (
        <ul>{reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
      )}
      <p className="field__hint" style={{ marginTop: 12, color: 'inherit' }}>
        The recommendation is computed by deterministic rules from the measured evidence, not by a language model.
        {pendingReview ? ' A human reviewer must sign off before it is final.' : ''}
      </p>
    </section>
  );
};
