import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { describeError } from '../../api';
import { policyApi } from '../../lib/projects';
import {
  buildPolicy, emptyDraft, hasErrors, loadChoice, metricLabel, parsePercent, saveChoice, validateDraft, FAILURE_RATE_METRICS, SECURITY_METRIC,
  type PolicyChoice, type PolicyDraft,
} from '../../lib/policy';
import { Banner, Field, Loading, Tip } from '../../components/flow/ui';
import type { PolicyMetricDoc, PolicyPayload, PolicyTemplate } from '../../types/api';

/** What the Run step needs to know: can we start, and what to send. */
export interface PolicyResolution {
  ready: boolean;
  /** Plain-language reasons the run cannot start yet. Empty when ready. */
  problems: string[];
  policy?: PolicyPayload;
  useExample: boolean;
}

interface Props {
  projectId: string;
  includeSecurity: boolean;
  onResolved: (r: PolicyResolution) => void;
}

const EXAMPLE_LABEL = 'Use the example policy (illustrative thresholds, not a real risk appetite)';

export const PolicyForm: React.FC<Props> = ({ projectId, includeSecurity, onResolved }) => {
  const [choice, setChoice] = useState<PolicyChoice>(() => loadChoice(projectId));
  const [template, setTemplate] = useState<PolicyTemplate | null>(null);
  const [tplError, setTplError] = useState<string | null>(null);
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  const loadTemplate = useCallback(() => {
    setTplError(null);
    policyApi.template().then(setTemplate).catch((e: unknown) => setTplError(describeError(e, 'the policy template')));
  }, []);
  useEffect(() => { loadTemplate(); }, [loadTemplate]);

  const metrics: PolicyMetricDoc[] = useMemo(() => template?.metrics ?? [], [template]);
  const useExample = choice.mode === 'example';
  const draft: PolicyDraft = useMemo(() => (choice.mode === 'custom' ? choice.draft : emptyDraft()), [choice]);
  const errors = useMemo(() => validateDraft(draft, metrics, includeSecurity), [draft, metrics, includeSecurity]);

  const update = (patch: Partial<PolicyDraft>) => {
    const next: PolicyChoice = { mode: 'custom', draft: { ...draft, ...patch } };
    setChoice(next);
    saveChoice(projectId, next);
  };
  const toggleExample = (on: boolean) => {
    const next: PolicyChoice = on ? { mode: 'example' } : { mode: 'custom', draft };
    setChoice(next);
    saveChoice(projectId, next);
  };

  useEffect(() => {
    if (useExample) { onResolved({ ready: true, problems: [], useExample: true }); return; }
    const problems = [
      ...errors.general,
      ...(errors.policyId ? [errors.policyId] : []),
      ...(errors.version ? [errors.version] : []),
      ...(errors.judgeMinAgreement ? [`Judge minimum agreement: ${errors.judgeMinAgreement}`] : []),
      ...Object.entries(errors.metrics).map(([m, msg]) => `${metricLabel(m)}: ${msg}`),
    ];
    if (!template) { onResolved({ ready: false, problems: ['The policy form has not loaded yet.'], useExample: false }); return; }
    if (hasErrors(errors)) { onResolved({ ready: false, problems, useExample: false }); return; }
    onResolved({ ready: true, problems: [], policy: buildPolicy(draft, metrics), useExample: false });
  }, [useExample, errors, template, draft, metrics, onResolved]);

  return (
    <section className="panel stack" aria-labelledby="pol-h" data-testid="policy-form">
      <div>
        <h2 className="h2" id="pol-h" style={{ margin: 0 }}>Release policy <Tip text="The release recommendation is computed against limits you set here. The tool never picks them for you." /></h2>
        <p className="muted" style={{ margin: '4px 0 0' }}>
          Decide how much failure you accept before shipping. For each check you require, set the highest failure rate you tolerate.
          A check passes only when the whole 95% confidence interval of its failure rate is at or below your limit. No limits are pre-filled.
        </p>
      </div>

      <label className="fcheck" data-testid="use-example-policy">
        <input type="checkbox" checked={useExample} onChange={(e) => toggleExample(e.target.checked)} />
        <span><strong>{EXAMPLE_LABEL}</strong></span>
      </label>
      {useExample && (
        <Banner tone="warn" role="status">
          <span>The decision will be labelled <strong>EXAMPLE policy</strong>. Its thresholds are illustrative only, so treat the recommendation as a demonstration, not a release decision.</span>
        </Banner>
      )}

      {!useExample && (
        <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="h3">Your policy</legend>
          {tplError && (
            <Banner tone="bad" role="alert">
              <span>Could not load the policy form. {tplError} <button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={loadTemplate}>Retry</button></span>
            </Banner>
          )}
          {!template && !tplError && <Loading label="Loading the policy form…" />}
          {template && (
            <>
              <div className="grid2">
                <Field label="Policy name" htmlFor="pol-name" error={touched.name ? errors.policyId : null}>
                  <input id="pol-name" className="input" value={draft.policyId} aria-invalid={Boolean(touched.name && errors.policyId)}
                    onChange={(e) => update({ policyId: e.target.value })} onBlur={() => setTouched((t) => ({ ...t, name: true }))} autoComplete="off" />
                </Field>
                <Field label="Version" htmlFor="pol-ver" error={touched.ver ? errors.version : null} hint="Your own label, for example a date or a number.">
                  <input id="pol-ver" className="input" value={draft.version} aria-invalid={Boolean(touched.ver && errors.version)}
                    onChange={(e) => update({ version: e.target.value })} onBlur={() => setTouched((t) => ({ ...t, ver: true }))} autoComplete="off" />
                </Field>
              </div>
              <div className="tablewrap">
                <table className="table" data-testid="policy-metrics">
                  <caption className="muted" style={{ textAlign: 'left', padding: '0 0 8px' }}>
                    Tick the checks that must be within your limit before a release, then enter the maximum failure rate you accept (0 to 100).
                  </caption>
                  <thead><tr><th scope="col">Require</th><th scope="col">Check</th><th scope="col">Highest failure rate you accept</th></tr></thead>
                  <tbody>
                    {metrics.map((m) => {
                      const on = Boolean(draft.required[m.name]);
                      const text = draft.maxPct[m.name] ?? '';
                      const msg = on ? errors.metrics[m.name] : undefined;
                      const pct = parsePercent(text);
                      return (
                        <tr key={m.name}>
                          <td>
                            <input type="checkbox" id={`req-${m.name}`} checked={on} aria-label={`Require ${metricLabel(m.name)}`}
                              onChange={(e) => update({ required: { ...draft.required, [m.name]: e.target.checked } })} style={{ width: 18, height: 18 }} />
                          </td>
                          <td>
                            <label htmlFor={`req-${m.name}`} className="h3" style={{ margin: 0, cursor: 'pointer' }}>{metricLabel(m.name)}</label>
                            <div className="field__hint">{m.description}</div>
                            {m.name === SECURITY_METRIC && includeSecurity && <div className="field__hint"><strong>Required while security probes are on.</strong></div>}
                          </td>
                          <td>
                            <div className="frow" style={{ gap: 6, flexWrap: 'nowrap' }}>
                              <input className="input" style={{ maxWidth: 96 }} inputMode="decimal" disabled={!on} value={text}
                                aria-label={`Highest failure rate you accept for ${metricLabel(m.name)}, percent`} aria-invalid={Boolean(msg)}
                                onChange={(e) => update({ maxPct: { ...draft.maxPct, [m.name]: e.target.value } })} />
                              <span aria-hidden="true">%</span>
                            </div>
                            {msg ? <span className="field__error" role="alert">{msg}</span>
                              : on && pct !== null ? <span className="field__hint">{FAILURE_RATE_METRICS.includes(m.name) ? `At most ${pct}% of questions may error.` : `At most ${pct}% of questions may fail this check.`}</span> : null}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <Field label="Minimum judge agreement (optional)" htmlFor="pol-judge" error={errors.judgeMinAgreement}
                tip="Lets the semantic judge influence correctness and faithfulness verdicts, but only after a calibration against your own labels shows it agrees at least this often."
                hint="Percent, for example 90. The judge may gate only if a fresh calibration's lower confidence bound reaches it. Blank keeps the judge advisory: verdicts then come from the rule-based checks alone.">
                <div className="frow" style={{ gap: 6, flexWrap: 'nowrap' }}>
                  <input id="pol-judge" className="input" style={{ maxWidth: 96 }} inputMode="decimal" value={draft.judgeMinPct ?? ''} aria-invalid={Boolean(errors.judgeMinAgreement)}
                    onChange={(e) => update({ judgeMinPct: e.target.value })} data-testid="policy-judge-min" />
                  <span aria-hidden="true">%</span>
                </div>
              </Field>
              {errors.general.length > 0 && (
                <Banner tone="warn" role="status"><ul style={{ margin: 0, paddingLeft: 18 }}>{errors.general.map((g) => <li key={g}>{g}</li>)}</ul></Banner>
              )}
            </>
          )}
        </fieldset>
      )}
      <p className="field__hint" style={{ margin: 0 }}>Your choice is remembered for this project in this browser.</p>
    </section>
  );
};
