import React, { useState } from 'react';
import { describeError } from '../../api';
import { projectsApi } from '../../lib/projects';
import { looksBinary, parseQaText } from '../../lib/parsers';
import { RISK_FOCUS_OPTIONS, labelOf } from '../../lib/explain';
import { projectHref } from '../../lib/route';
import { Banner, Field, Tip } from '../../components/flow/ui';
import type { Project, ProjectDocument, ProjectQaPair } from '../../types/api';
import { validateEndpoint } from '../ConnectPage';

const DEFAULT_FOCUS = ['hallucination', 'retrieval', 'prompt_injection'];
const MAX_DOC_BYTES = 2_000_000;

export const InputsStep: React.FC<{ project: Project }> = ({ project }) => {
  const prev = project.inputs ?? {};
  const [docs, setDocs] = useState<ProjectDocument[]>(prev.documents ?? []);
  const [qa, setQa] = useState<ProjectQaPair[]>(prev.qa_pairs ?? []);
  const [pasteDoc, setPasteDoc] = useState('');
  const [pasteQa, setPasteQa] = useState('');
  const [endpoint, setEndpoint] = useState(prev.endpoint_url ?? project.endpoint_url ?? '');
  const [notes, setNotes] = useState(prev.notes ?? '');
  const [focus, setFocus] = useState<string[]>(prev.risk_focus?.length ? prev.risk_focus : DEFAULT_FOCUS);
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [messages, setMessages] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const envNames = (project.analysis?.env_vars ?? []).map(labelOf).filter((n) => /^[A-Z][A-Z0-9_]*$/.test(n));
  const endpointError = validateEndpoint(endpoint);
  const staticOnly = project.analysis?.execution_mode === 'static_only' && !endpoint.trim();

  const addDocs = async (files: FileList | null) => {
    if (!files) return;
    const next: ProjectDocument[] = [];
    const warn: string[] = [];
    for (const f of Array.from(files)) {
      if (f.size > MAX_DOC_BYTES) { warn.push(`${f.name}: larger than 2 MB, skipped.`); continue; }
      const text = await f.text();
      if (looksBinary(text)) { warn.push(`${f.name}: looks like a binary file. Export it as text (.txt/.md) first; PDFs must be converted to text.`); continue; }
      next.push({ name: f.name, text });
    }
    setDocs((d) => [...d, ...next]);
    setMessages(warn);
  };

  const addQaText = (text: string, name = '') => {
    const res = parseQaText(text, name);
    setQa((q) => [...q, ...res.rows]);
    setMessages(res.errors.slice(0, 5).concat(res.rows.length === 0 ? ['No questions were found in that input.'] : []));
  };

  const addQaFile = async (files: FileList | null) => {
    const f = files?.[0];
    if (f) addQaText(await f.text(), f.name);
  };

  const suggestInputs = async () => {
    setError(null); setInfo(null);
    try {
      const s = await projectsApi.suggestedInputs(project.id);
      if (s.documents?.length) setDocs((d) => [...d, ...s.documents!]);
      if (s.qa_pairs?.length) setQa((q) => [...q, ...s.qa_pairs!]);
      if (s.risk_focus?.length) setFocus(s.risk_focus);
      if (s.notes) setNotes((n) => n || String(s.notes));
      if (s.endpoint_url) setEndpoint((e) => e || String(s.endpoint_url));
      const added = (s.documents?.length ?? 0) + (s.qa_pairs?.length ?? 0);
      setInfo(added > 0
        ? `Added ${s.documents?.length ?? 0} document(s) and ${s.qa_pairs?.length ?? 0} question(s). Review them below, then continue.`
        : 'No documents or questions could be suggested from this repository. Add your own below, or continue and let the tool generate questions.');
    } catch (err) {
      setError(describeError(err, 'suggested inputs'));
    }
  };

  const toggleFocus = (id: string) =>
    setFocus((f) => (f.includes(id) ? f.filter((x) => x !== id) : [...f, id]));

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (endpointError) return;
    setBusy(true); setError(null);
    const documents = pasteDoc.trim() ? [...docs, { name: 'pasted.txt', text: pasteDoc }] : docs;
    try {
      await projectsApi.saveInputs(project.id, {
        documents, qa_pairs: qa, risk_focus: focus,
        ...(endpoint.trim() ? { endpoint_url: endpoint.trim() } : {}),
        ...(notes.trim() ? { notes: notes.trim() } : {}),
      });
      const filled = Object.fromEntries(Object.entries(secrets).filter(([, v]) => v));
      if (Object.keys(filled).length > 0) await projectsApi.saveSecrets(project.id, filled);
      setSecrets({});
      window.location.hash = projectHref(project.id, 'run');
    } catch (err) {
      setError(describeError(err, 'saving inputs'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="stack" onSubmit={save} noValidate>
      <div className="panel panel--flat frow frow--between">
        <div>
          <h2 className="h2" style={{ margin: 0 }}>Not sure what to provide?</h2>
          <p className="muted" style={{ margin: '4px 0 0' }}>Everything here is optional. One click fills sensible defaults from your repository.</p>
        </div>
        <button type="button" className="fbtn" onClick={() => void suggestInputs()} data-testid="use-suggested">
          <span className="material-symbols-outlined" aria-hidden="true">auto_fix_high</span> Use suggested inputs
        </button>
      </div>
      {info && <Banner tone="ok" role="status">{info}</Banner>}
      {error && <Banner tone="bad" role="alert">{error}</Banner>}
      {messages.length > 0 && <Banner tone="warn" role="status"><ul style={{ margin: 0, paddingLeft: 18 }}>{messages.map((m, i) => <li key={i}>{m}</li>)}</ul></Banner>}

      <section className="panel stack" aria-labelledby="docs-h">
        <h2 className="h2" id="docs-h" style={{ margin: 0 }}>Knowledge documents <Tip text="The documents your app retrieves from. Used to check that answers are grounded in them." /></h2>
        <Field label="Upload .txt / .md files" htmlFor="doc-files" hint="PDFs: export to text first. Use non-sensitive or synthetic content.">
          <input id="doc-files" className="input" type="file" multiple accept=".txt,.md,.markdown,text/plain,text/markdown,.pdf" onChange={(e) => void addDocs(e.target.files)} />
        </Field>
        <Field label="Or paste text" htmlFor="doc-paste">
          <textarea id="doc-paste" className="textarea" value={pasteDoc} onChange={(e) => setPasteDoc(e.target.value)} placeholder="Paste a document here" />
        </Field>
        {docs.length > 0 && (
          <ul className="items" aria-label="Added documents">
            {docs.map((d, i) => (
              <li key={`${d.name}-${i}`} className="item frow frow--between" style={{ padding: '8px 14px' }}>
                <span className="fmono">{d.name} · {d.text.length.toLocaleString()} chars</span>
                <button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={() => setDocs((x) => x.filter((_, j) => j !== i))} aria-label={`Remove ${d.name}`}>Remove</button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel stack" aria-labelledby="qa-h">
        <h2 className="h2" id="qa-h" style={{ margin: 0 }}>Questions and reference answers <Tip text="Real questions your users ask, with the correct answer if you know it. Without any, we can generate questions from your documents." /></h2>
        <Field label="Upload CSV or JSONL" htmlFor="qa-file" hint='CSV columns: question, reference_answer. JSONL: {"question": "...", "reference_answer": "..."} per line.'>
          <input id="qa-file" className="input" type="file" accept=".csv,.jsonl,.ndjson,text/csv" onChange={(e) => void addQaFile(e.target.files)} />
        </Field>
        <Field label="Or paste CSV / JSONL" htmlFor="qa-paste">
          <textarea id="qa-paste" className="textarea" value={pasteQa} onChange={(e) => setPasteQa(e.target.value)} placeholder={'question,reference_answer\n"What is the refund window?","30 days"'} />
        </Field>
        <div className="frow">
          <button type="button" className="fbtn fbtn--ghost fbtn--sm" disabled={!pasteQa.trim()} onClick={() => { addQaText(pasteQa); setPasteQa(''); }}>Add pasted questions</button>
          <span className="muted" data-testid="qa-count">{qa.length} question{qa.length === 1 ? '' : 's'} loaded</span>
          {qa.length > 0 && <button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={() => setQa([])}>Clear</button>}
        </div>
      </section>

      <section className="panel stack" aria-labelledby="ep-h">
        <h2 className="h2" id="ep-h" style={{ margin: 0 }}>Running your app</h2>
        <Field label="Deployed endpoint URL" htmlFor="ep" error={endpointError}
          tip="Where we send questions. Without it, the run is code analysis only and cannot measure real answers."
          hint="A staging URL is ideal. Do not point this at production with real users.">
          <input id="ep" className="input" type="url" inputMode="url" value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder="https://staging.example.com/ask" autoComplete="off" />
        </Field>
        {staticOnly && <Banner tone="warn"><span>Without an endpoint this run will be <strong>static analysis only</strong>: your code is read but never executed, so no answers are measured.</span></Banner>}
        {envNames.length > 0 && (
          <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="field__label">Secrets your app needs <Tip text="Write-only. Sent once to the server, never shown again and never stored in your browser." /></legend>
            <span className="field__hint">Optional. Use test keys with low limits.</span>
            <div className="grid2">
              {envNames.map((n) => (
                <Field key={n} label={n} htmlFor={`sec-${n}`}>
                  <input id={`sec-${n}`} className="input" type="password" autoComplete="new-password" value={secrets[n] ?? ''} onChange={(e) => setSecrets((s) => ({ ...s, [n]: e.target.value }))} />
                </Field>
              ))}
            </div>
          </fieldset>
        )}
      </section>

      <section className="panel stack" aria-labelledby="rf-h">
        <h2 className="h2" id="rf-h" style={{ margin: 0 }}>Risk focus</h2>
        <div className="checks">
          {RISK_FOCUS_OPTIONS.map((o) => (
            <label key={o.id} className="fcheck">
              <input type="checkbox" checked={focus.includes(o.id)} onChange={() => toggleFocus(o.id)} />
              <span>{o.label}</span>
            </label>
          ))}
        </div>
        <Field label="Notes for the reviewer (optional)" htmlFor="notes">
          <textarea id="notes" className="textarea" style={{ minHeight: 72, fontFamily: 'var(--font-hanken)', fontSize: 14 }} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      </section>

      <div className="frow">
        <button type="submit" className="fbtn" disabled={busy || Boolean(endpointError)} data-testid="save-inputs">
          {busy ? <><span className="spinner" aria-hidden="true" /> Saving…</> : <>Save and continue <span className="material-symbols-outlined" aria-hidden="true">arrow_forward</span></>}
        </button>
        <a className="fbtn fbtn--ghost" href={projectHref(project.id, 'run')}>Skip, use defaults</a>
      </div>
    </form>
  );
};
