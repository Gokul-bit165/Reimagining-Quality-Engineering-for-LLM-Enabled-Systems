import React, { useMemo, useState } from 'react';
import { describeError } from '../../api';
import {
  CONTEXTS_KIND_TEXT, RESPONSE_FORMATS, TEMPLATE_PRESETS, hasTargetErrors, headerSecretNames, validateTargetForm,
  type TargetForm,
} from '../../lib/targetConfig';
import { Banner, Field, Loading, Tip } from '../../components/flow/ui';
import type { ResponseFormat, TargetTestResult } from '../../types/api';

/** Readable outcome of one probe question. Never shows secret values (the backend scrubs the preview). */
export const TargetTestOutcome: React.FC<{ result: TargetTestResult }> = ({ result }) => (
  <div className="stack" data-testid="target-test-result">
    <div className="frow">
      <span className="badge" data-tone={result.ok ? 'ok' : 'bad'} data-testid="target-test-status">{result.ok ? 'CONNECTED' : 'FAILED'}</span>
      <span className="muted">Answered in {result.latency_s.toFixed(2)} s</span>
    </div>
    {result.error && <Banner tone="bad" role="alert"><span><strong>The call failed.</strong> {result.error}</span></Banner>}
    {result.warnings.filter((w) => !(result.contexts_kind === 'ids' && /^contexts look like ids/i.test(w))).map((w) => <Banner key={w} tone="warn" role="status"><span data-testid="target-test-warning">{w}</span></Banner>)}
    {result.contexts_kind === 'ids' && (
      <Banner tone="warn" role="status"><span>Your app returned ids, not passage text: <strong>faithfulness will not be measured</strong>. Point the context paths at the passage text.</span></Banner>
    )}
    {result.contexts_kind === 'none' && result.ok && (
      <Banner tone="warn" role="status"><span>No contexts were found in the response: <strong>faithfulness and retrieval cannot be measured</strong>. Set context paths if your app returns its sources.</span></Banner>
    )}
    <div><div className="h3">Answer</div>{result.answer ? <p className="quote">{result.answer}</p> : <p className="muted" style={{ margin: 0 }}>No answer text was extracted.</p>}</div>
    <div>
      <div className="h3">Contexts found ({result.contexts.length}) <span className="muted" data-testid="target-test-kind">{CONTEXTS_KIND_TEXT[result.contexts_kind]}</span></div>
      {result.contexts.length === 0 ? <p className="muted" style={{ margin: 0 }}>None.</p> : result.contexts.map((c, i) => <p key={i} className="quote quote--ctx">{c}</p>)}
    </div>
    {result.raw_preview && (
      <details>
        <summary className="h3" style={{ cursor: 'pointer' }}>Raw response preview (truncated, secrets removed)</summary>
        <pre className="fquote quote" data-testid="target-test-raw" style={{ margin: 0, maxHeight: 220, overflow: 'auto' }}>{result.raw_preview}</pre>
      </details>
    )}
  </div>
);

interface Props {
  endpoint: string;
  onEndpoint: (v: string) => void;
  endpointError: string | null;
  staticOnly: boolean;
  form: TargetForm;
  onForm: (f: TargetForm) => void;
  /** secret name -> value typed this session (write-only; never read back) */
  secrets: Record<string, string>;
  onSecrets: (s: Record<string, string>) => void;
  /** names the analyser says the app needs */
  envNames: string[];
  /** names already in the server vault (values are never returned) */
  storedNames: string[];
  defaultQuestion: string;
  /** Saves endpoint, secrets and config, then sends one probe. Throws a readable Error on failure. */
  onTest: (question: string) => Promise<TargetTestResult>;
}

export const TargetConfigPanel: React.FC<Props> = ({
  endpoint, onEndpoint, endpointError, staticOnly, form, onForm, secrets, onSecrets, envNames, storedNames, defaultQuestion, onTest,
}) => {
  // Follows the first loaded question until the user types their own.
  const [typedQuestion, setQuestion] = useState<string | null>(null);
  const question = typedQuestion ?? defaultQuestion;
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<TargetTestResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const errors = useMemo(() => validateTargetForm(form), [form]);
  const headerSecrets = useMemo(() => headerSecretNames(form.headers), [form.headers]);
  const secretNames = useMemo(() => [...new Set([...envNames, ...headerSecrets])], [envNames, headerSecrets]);
  const dropped = storedNames.filter((n) => !(secrets[n] ?? '').trim());
  const typed = Object.values(secrets).some((v) => v.trim());
  const set = (patch: Partial<TargetForm>) => onForm({ ...form, ...patch });
  const preset = TEMPLATE_PRESETS.find((p) => p.template === form.template);

  const test = async () => {
    setBusy(true); setTestError(null); setResult(null);
    try { setResult(await onTest(question.trim())); }
    catch (e) { setTestError(e instanceof Error ? e.message : describeError(e, 'the connection test')); }
    finally { setBusy(false); }
  };
  const blocked = Boolean(endpointError) || !endpoint.trim() || hasTargetErrors(errors) || !question.trim();

  return (
    <section className="panel stack" aria-labelledby="ep-h" data-testid="target-panel">
      <div>
        <h2 className="h2" id="ep-h" style={{ margin: 0 }}>Connect to your app</h2>
        <p className="muted" style={{ margin: '4px 0 0' }}>Tell us how to ask your app a question and where to find the answer in its reply, then test it with one question.</p>
      </div>

      <div className="grid2">
        <Field label="Endpoint URL" htmlFor="ep" error={endpointError}
          tip="Where we send questions. Without it, the run is code analysis only and cannot measure real answers."
          hint="A staging URL is ideal. Do not point this at production with real users.">
          <input id="ep" className="input" type="url" inputMode="url" value={endpoint} onChange={(e) => onEndpoint(e.target.value)} placeholder="https://staging.example.com/ask" autoComplete="off" />
        </Field>
        <Field label="HTTP method" htmlFor="tc-method" hint="GET sends the request fields as query parameters.">
          <select id="tc-method" className="select" value={form.method} onChange={(e) => set({ method: e.target.value as 'POST' | 'GET' })}>
            <option value="POST">POST (JSON body)</option>
            <option value="GET">GET (query string)</option>
          </select>
        </Field>
      </div>
      {staticOnly && <Banner tone="warn"><span>Without an endpoint this run will be <strong>static analysis only</strong>: your code is read but never executed, so no answers are measured.</span></Banner>}

      <div className="stack" style={{ gap: 8 }}>
        <Field label="Request body" htmlFor="tc-template" error={errors.template}
          tip="JSON your app accepts. {question} is replaced by each test question (only inside text values)."
          hint="Leave empty to send {question, query, input} together. Use {question} where the question goes.">
          <textarea id="tc-template" className="textarea" spellCheck={false} value={form.template} aria-invalid={Boolean(errors.template)}
            onChange={(e) => set({ template: e.target.value })} placeholder={'{\n  "question": "{question}"\n}'} data-testid="tc-template" />
        </Field>
        <div className="frow" role="group" aria-label="Request presets">
          {TEMPLATE_PRESETS.map((p) => (
            <button key={p.id} type="button" className="fbtn fbtn--ghost fbtn--sm" data-testid={`preset-${p.id}`}
              onClick={() => set({ template: p.template, ...(p.answerPath ? { answerPath: p.answerPath } : {}) })}>{p.label}</button>
          ))}
        </div>
        {preset && <span className="field__hint">{preset.note}</span>}
      </div>

      <div className="grid2">
        <Field label="Response format" htmlFor="tc-format" hint={RESPONSE_FORMATS.find((f) => f.id === form.format)?.text}>
          <select id="tc-format" className="select" value={form.format} onChange={(e) => set({ format: e.target.value as ResponseFormat })}>
            {RESPONSE_FORMATS.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
          </select>
        </Field>
        <Field label="Answer path" htmlFor="tc-answer" error={errors.answerPath}
          tip="Where the answer text sits in the JSON reply, for example data.answer or choices.0.message.content."
          hint="Optional. Common locations are tried when empty.">
          <input id="tc-answer" className="input fmono" value={form.answerPath} aria-invalid={Boolean(errors.answerPath)} onChange={(e) => set({ answerPath: e.target.value })} placeholder="data.answer" autoComplete="off" />
        </Field>
      </div>
      <Field label="Context paths" htmlFor="tc-ctx" error={errors.contextPaths}
        tip="Where the retrieved passages sit in the reply. Use * for every item in a list, for example sources.*.text."
        hint="One per line. Point these at passage text, not ids, so faithfulness can be measured.">
        <textarea id="tc-ctx" className="textarea" style={{ minHeight: 64 }} spellCheck={false} value={form.contextPaths} aria-invalid={Boolean(errors.contextPaths)}
          onChange={(e) => set({ contextPaths: e.target.value })} placeholder="sources.*.text" />
      </Field>

      <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="field__label">Headers <Tip text="Credentials never go in the value itself. Write a reference such as Bearer ${API_TOKEN}, then enter the secret below." /></legend>
        <span className="field__hint">Use a secret reference like <code className="fmono">Bearer ${'{API_TOKEN}'}</code> for credentials. Plain values are only accepted for Accept, Content-Type, User-Agent, Accept-Language and X-Request-Id.</span>
        {form.headers.map((h, i) => (
          <div key={i} className="stack" style={{ gap: 4 }} data-testid="header-row">
            <div className="grid2">
              <input className="input" aria-label={`Header ${i + 1} name`} placeholder="Authorization" value={h.name} autoComplete="off"
                onChange={(e) => set({ headers: form.headers.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) })} />
              <div className="frow" style={{ flexWrap: 'nowrap' }}>
                <input className="input fmono" aria-label={`Header ${i + 1} value (secret reference)`} placeholder={'Bearer ${API_TOKEN}'} value={h.value} autoComplete="off" aria-invalid={Boolean(errors.headers[i])}
                  onChange={(e) => set({ headers: form.headers.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)) })} />
                <button type="button" className="fbtn fbtn--ghost fbtn--sm" aria-label={`Remove header ${i + 1}`} onClick={() => set({ headers: form.headers.filter((_, j) => j !== i) })}>Remove</button>
              </div>
            </div>
            {errors.headers[i] && <span className="field__error" role="alert">{errors.headers[i]}</span>}
          </div>
        ))}
        <div><button type="button" className="fbtn fbtn--ghost fbtn--sm" data-testid="add-header" onClick={() => set({ headers: [...form.headers, { name: '', value: '' }] })}>Add header</button></div>
      </fieldset>

      {secretNames.length > 0 && (
        <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0 }} data-testid="secrets-fieldset">
          <legend className="field__label">Secret values <Tip text="Write-only. Sent to the server's in-memory vault, never shown again and never stored in your browser." /></legend>
          <span className="field__hint">Saving replaces the whole vault for this project, so enter every value you want kept. Use test keys with low limits.</span>
          <div className="grid2">
            {secretNames.map((n) => (
              <Field key={n} label={n} htmlFor={`sec-${n}`} hint={storedNames.includes(n) ? 'A value is stored on the server (hidden). Type to replace it.' : headerSecrets.includes(n) ? 'Used by a header above.' : 'Needed by your app.'}>
                <input id={`sec-${n}`} className="input" type="password" autoComplete="new-password" value={secrets[n] ?? ''} onChange={(e) => onSecrets({ ...secrets, [n]: e.target.value })} />
              </Field>
            ))}
          </div>
          {typed && dropped.length > 0 && (
            <Banner tone="warn" role="status"><span data-testid="secrets-drop-warning">Saving will replace the vault, so <strong>{dropped.join(', ')}</strong> (stored, not re-entered) will be removed.</span></Banner>
          )}
        </fieldset>
      )}

      <div className="stack" style={{ borderTop: '1px solid var(--c-line)', paddingTop: 'var(--s-4)' }}>
        <h3 className="h3" style={{ margin: 0 }}>Test the connection</h3>
        <Field label="Probe question" htmlFor="tc-probe" hint="One question is sent through the settings above. Saving the endpoint, secrets and these settings happens first.">
          <input id="tc-probe" className="input" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="A question your app should be able to answer" />
        </Field>
        <div className="frow">
          <button type="button" className="fbtn" disabled={busy || blocked} onClick={() => void test()} data-testid="test-connection">
            {busy ? <Loading label="Testing…" /> : <>Test connection <span className="material-symbols-outlined" aria-hidden="true">wifi_tethering</span></>}
          </button>
          {blocked && !busy && <span className="field__hint">{!endpoint.trim() ? 'Enter an endpoint URL to test.' : !question.trim() ? 'Enter a probe question.' : 'Fix the highlighted fields to test.'}</span>}
        </div>
        {testError && <Banner tone="bad" role="alert">{testError}</Banner>}
        {result && <TargetTestOutcome result={result} />}
      </div>
    </section>
  );
};
