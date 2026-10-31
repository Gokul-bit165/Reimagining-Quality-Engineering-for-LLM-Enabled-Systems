import React, { useEffect, useState } from 'react';
import { describeError } from '../../api';
import { llmApi } from '../../lib/projects';
import { buildCampaignRequest, campaignsApi, emptyTarget, parsePlanFile, validateCampaignForm, type PlanParse, type TargetDraft } from '../../lib/campaign';
import { RISK_FOCUS_OPTIONS } from '../../lib/explain';
import { campaignHref } from '../../lib/route';
import { Banner, Field, Loading, Tip } from '../../components/flow/ui';
import { PolicyForm, type PolicyResolution } from '../project/PolicyForm';
import { TargetEditor } from './TargetEditor';
import type { LlmStatus, Project } from '../../types/api';

const UNRESOLVED: PolicyResolution = { ready: false, problems: ['The policy form has not loaded yet.'], useExample: false };
const DEFAULT_FOCUS = ['hallucination', 'retrieval', 'prompt_injection'];

const clamp = (v: string, lo: number, hi: number): number => Math.max(lo, Math.min(hi, Math.round(Number(v)) || lo));

export const CampaignForm: React.FC<{ project: Project }> = ({ project }) => {
  const [name, setName] = useState('');
  const [focus, setFocus] = useState<string[]>(project.inputs.risk_focus?.length ? project.inputs.risk_focus : DEFAULT_FOCUS);
  const [targets, setTargets] = useState<TargetDraft[]>([emptyTarget('endpoint', 'Current app')]);
  const [repeats, setRepeats] = useState(3);
  const [maxCases, setMaxCases] = useState(50);
  const [maxCalls, setMaxCalls] = useState(2000);
  const [security, setSecurity] = useState(true);
  const [generate, setGenerate] = useState(true);
  const [plan, setPlan] = useState<PlanParse | null>(null);
  const [planName, setPlanName] = useState('');
  const [policy, setPolicy] = useState<PolicyResolution>(UNRESOLVED);
  const [llm, setLlm] = useState<LlmStatus | null>(null);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    let live = true;
    llmApi.status().then((s) => { if (live) setLlm(s); }).catch((e: unknown) => { if (live) setLlmError(describeError(e, 'the language-model status')); });
    return () => { live = false; };
  }, []);

  const llmMissing = llm !== null && !llm.configured;
  const willGenerate = generate && !llmMissing && !plan?.plan;
  const hasInputs = (project.inputs.qa_pairs?.length ?? 0) > 0 || (project.inputs.documents?.length ?? 0) > 0;
  const problems = validateCampaignForm({ name, targets, repeats, maxCases, maxCalls, planPresent: Boolean(plan?.plan) });
  const blockers = [
    ...problems,
    ...(policy.ready ? [] : policy.problems),
    ...(!hasInputs && !plan?.plan ? ['The project has no documents or Q&A pairs. Add some in Inputs, or import a plan.'] : []),
  ];
  const secretNames = project.secrets_set ?? [];

  const onPlanFile = async (files: FileList | null) => {
    const f = files?.[0];
    if (!f) return;
    setPlanName(f.name);
    setPlan(parsePlanFile(await f.text()));
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    if (blockers.length > 0) return;
    setBusy(true); setError(null);
    try {
      const body = buildCampaignRequest({
        projectId: project.id, riskFocus: focus, includeSecurity: security, generate: willGenerate, plan: plan?.plan ?? null,
        policy: { useExample: policy.useExample, policy: policy.policy },
        form: { name, targets, repeats, maxCases, maxCalls, planPresent: Boolean(plan?.plan) },
      });
      const res = await campaignsApi.create(body);
      window.location.hash = campaignHref(project.id, res.id);
    } catch (err) {
      setError(describeError(err, 'campaigns'));
    } finally { setBusy(false); }
  };

  return (
    <form className="stack" onSubmit={submit} noValidate data-testid="campaign-form">
      <section className="panel stack" aria-labelledby="cf-h">
        <div>
          <h2 className="h2" id="cf-h" style={{ margin: 0 }}>New test campaign</h2>
          <p className="muted" style={{ margin: '4px 0 0' }}>A campaign plans tests from your risks, runs them against one or more targets, and compares the results with the uncertainty shown.</p>
        </div>
        <Field label="Campaign name" htmlFor="cf-name" hint="For example: chunk size 512 vs 1024.">
          <input id="cf-name" className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} autoComplete="off" />
        </Field>
        <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="field__label" style={{ marginBottom: 8 }}>Risk focus</legend>
          <div className="checks">
            {RISK_FOCUS_OPTIONS.map((o) => (
              <label key={o.id} className="fcheck">
                <input type="checkbox" checked={focus.includes(o.id)} onChange={() => setFocus((f) => (f.includes(o.id) ? f.filter((x) => x !== o.id) : [...f, o.id]))} />
                <span>{o.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
      </section>

      <TargetEditor targets={targets} secretNames={secretNames} onChange={setTargets} />

      <PolicyForm projectId={project.id} includeSecurity={security} onResolved={setPolicy} />

      <section className="panel stack" aria-labelledby="cb-h">
        <h2 className="h2" id="cb-h" style={{ margin: 0 }}>Budget and options</h2>
        <div className="grid3">
          <Field label="Repeats per case" htmlFor="cf-rep" hint="1 to 10. Default 3." tip="Each case is asked this many times on every target to measure consistency.">
            <input id="cf-rep" className="input" type="number" min={1} max={10} value={repeats} onChange={(e) => setRepeats(clamp(e.target.value, 1, 10))} />
          </Field>
          <Field label="Max cases" htmlFor="cf-cases" hint="1 to 200. Default 50.">
            <input id="cf-cases" className="input" type="number" min={1} max={200} value={maxCases} onChange={(e) => setMaxCases(clamp(e.target.value, 1, 200))} />
          </Field>
          <Field label="Max calls" htmlFor="cf-calls" hint={`1 to 20000. Needs at least repeats x targets = ${repeats * Math.max(1, targets.length)}.`} tip="A hard cap on calls to all targets together. If it runs out, the campaign stops and says it is incomplete.">
            <input id="cf-calls" className="input" type="number" min={1} max={20000} value={maxCalls} onChange={(e) => setMaxCalls(clamp(e.target.value, 1, 20000))} />
          </Field>
        </div>
        <label className="fcheck"><input type="checkbox" checked={security} onChange={(e) => setSecurity(e.target.checked)} data-testid="cf-security" /><span>Include security probes (prompt injection, data leakage)</span></label>
        {!security && <Banner tone="warn" role="status"><span>Without security probes no target can be recommended for RELEASE: attack resistance is required evidence.</span></Banner>}
        <div className="stack" style={{ gap: 4 }}>
          <label className="fcheck">
            <input type="checkbox" checked={willGenerate} disabled={llmMissing || Boolean(plan?.plan)} onChange={(e) => setGenerate(e.target.checked)} data-testid="cf-generate" />
            <span>Generate extra cases with a language model <Tip text="Questions written by a model from your documents. They stay advisory until a human confirms each one." /></span>
          </label>
          {llmMissing && (
            <span className="field__hint" data-testid="cf-generate-reason">
              Unavailable: no language model is configured on the server. Missing settings: {llm!.missing.map((n) => <code key={n} className="fchip" style={{ marginRight: 4 }}>{n}</code>)} (names only). Cases will be rule-based.
            </span>
          )}
          {plan?.plan && <span className="field__hint">Not used: you imported a plan, so the cases come from it.</span>}
          {llmError && <span className="field__hint">Could not check whether generation is available. {llmError}</span>}
          {llm === null && !llmError && <Loading label="Checking the language model…" />}
        </div>
      </section>

      <section className="panel stack" aria-labelledby="ip-h">
        <div>
          <h2 className="h2" id="ip-h" style={{ margin: 0 }}>Import a plan (optional)</h2>
          <p className="muted" style={{ margin: '4px 0 0' }}>Use a plan exported from an earlier campaign, after editing it if you like. The engine recomputes risks, oracles and coverage from your cases.</p>
        </div>
        <Field label="Plan JSON file" htmlFor="cf-plan" hint="A JSON object with a non-empty cases list. Each case needs an id and a question; security cases need a probe.">
          <input id="cf-plan" className="input" type="file" accept=".json,application/json" onChange={(e) => void onPlanFile(e.target.files)} data-testid="cf-plan-file" />
        </Field>
        {plan && plan.errors.length > 0 && (
          <Banner tone="bad" role="alert">
            <div data-testid="plan-errors"><strong>{planName} cannot be imported:</strong>
              <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>{plan.errors.map((m) => <li key={m}>{m}</li>)}</ul></div>
          </Banner>
        )}
        {plan?.plan && (
          <div className="frow">
            <Banner tone="ok" role="status"><span data-testid="plan-ok">{planName}: {plan.nCases} case{plan.nCases === 1 ? '' : 's'} ready to import.</span></Banner>
            <button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={() => { setPlan(null); setPlanName(''); }}>Remove plan</button>
          </div>
        )}
      </section>

      {error && <Banner tone="bad" role="alert"><span data-testid="campaign-error">{error}</span></Banner>}
      {(submitted || blockers.length > 0) && blockers.length > 0 && (
        <div role="status" data-testid="campaign-blockers" id="campaign-blockers">
          <p className="h3" style={{ marginBottom: 4 }}>Before you can start:</p>
          <ul style={{ margin: 0, paddingLeft: 18 }} className="muted">{blockers.map((b) => <li key={b}>{b}</li>)}</ul>
        </div>
      )}
      <div className="frow">
        <button type="submit" className="fbtn" disabled={busy || blockers.length > 0} aria-describedby={blockers.length > 0 ? 'campaign-blockers' : undefined} data-testid="start-campaign">
          {busy ? <><span className="spinner" aria-hidden="true" /> Starting…</> : <>Start campaign <span className="material-symbols-outlined" aria-hidden="true">play_arrow</span></>}
        </button>
        <a className="fbtn fbtn--ghost" href={campaignHref(project.id)}>Cancel</a>
      </div>
    </form>
  );
};
