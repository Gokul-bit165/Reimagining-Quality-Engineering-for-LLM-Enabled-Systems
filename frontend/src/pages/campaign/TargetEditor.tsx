import React from 'react';
import { MAX_METADATA, MAX_TARGETS, emptyTarget, validateTarget, type MetaRow, type TargetDraft } from '../../lib/campaign';
import { Field, Tip } from '../../components/flow/ui';
import type { TargetKind } from '../../types/campaign';

const META_KEYS = ['chunk_size', 'chunk_overlap', 'retriever', 'top_k', 'embedding_model', 'model', 'prompt_version'];

const KIND_TEXT: Record<TargetKind, string> = {
  endpoint: 'A RAG app reachable over HTTP. Leave the URL blank to test this project\'s own endpoint.',
  model: 'A bare chat model (OpenAI-compatible) given your documents directly, with no retriever. A useful baseline.',
};

interface RowProps {
  index: number;
  target: TargetDraft;
  all: TargetDraft[];
  secretNames: string[];
  onChange: (t: TargetDraft) => void;
  onRemove: () => void;
}

const TargetRow: React.FC<RowProps> = ({ index, target: t, all, secretNames, onChange, onRemove }) => {
  const errors = validateTarget(t, all);
  const id = `t${index}`;
  const set = (patch: Partial<TargetDraft>) => onChange({ ...t, ...patch });
  const setMeta = (i: number, patch: Partial<MetaRow>) => set({ meta: t.meta.map((r, j) => (j === i ? { ...r, ...patch } : r)) });
  return (
    <fieldset className="panel panel--flat stack" style={{ margin: 0 }} data-testid={`target-${index}`}>
      <legend className="h3" style={{ padding: '0 6px' }}>Target {index + 1}{t.label.trim() ? `: ${t.label.trim()}` : ''}</legend>
      <div className="grid2">
        <Field label="Label" htmlFor={`${id}-label`} error={errors.label} hint="Shown in every table and chart. Letters, digits, space . _ -">
          <input id={`${id}-label`} className="input" value={t.label} onChange={(e) => set({ label: e.target.value })} aria-invalid={Boolean(errors.label)} autoComplete="off" maxLength={40} />
        </Field>
        <div className="field" role="radiogroup" aria-label={`Kind of target ${index + 1}`}>
          <span className="field__label">Kind <Tip text={KIND_TEXT[t.kind]} label="About target kinds" /></span>
          <div className="seg">
            {(['endpoint', 'model'] as TargetKind[]).map((k) => (
              <label key={k} className="seg__opt" data-on={t.kind === k}>
                <input type="radio" name={`${id}-kind`} value={k} checked={t.kind === k} onChange={() => set({ kind: k })} />
                {k === 'endpoint' ? 'RAG endpoint' : 'Bare model'}
              </label>
            ))}
          </div>
          <span className="field__hint">{KIND_TEXT[t.kind]}</span>
        </div>
      </div>

      {t.kind === 'endpoint' ? (
        <Field label="Endpoint URL (optional)" htmlFor={`${id}-url`} error={errors.endpointUrl} hint="Blank = this project's own endpoint, with its saved request settings.">
          <input id={`${id}-url`} className="input" value={t.endpointUrl} onChange={(e) => set({ endpointUrl: e.target.value })} aria-invalid={Boolean(errors.endpointUrl)} placeholder="https://staging.example.com/ask" autoComplete="off" spellCheck={false} />
        </Field>
      ) : (
        <div className="grid3">
          <Field label="Model" htmlFor={`${id}-model`} error={errors.model}>
            <input id={`${id}-model`} className="input" value={t.model} onChange={(e) => set({ model: e.target.value })} aria-invalid={Boolean(errors.model)} placeholder="gpt-4o-mini" autoComplete="off" spellCheck={false} />
          </Field>
          <Field label="Base URL" htmlFor={`${id}-base`} error={errors.baseUrl} hint="OpenAI-compatible, for example https://api.openai.com/v1">
            <input id={`${id}-base`} className="input" value={t.baseUrl} onChange={(e) => set({ baseUrl: e.target.value })} aria-invalid={Boolean(errors.baseUrl)} autoComplete="off" spellCheck={false} />
          </Field>
          <Field label="API key secret name" htmlFor={`${id}-key`} error={errors.apiKeySecret} hint="The NAME of a secret saved for this project (Inputs). The value is never shown or sent from here.">
            <input id={`${id}-key`} className="input" list={`${id}-secrets`} value={t.apiKeySecret} onChange={(e) => set({ apiKeySecret: e.target.value })} aria-invalid={Boolean(errors.apiKeySecret)} placeholder="OPENAI_API_KEY" autoComplete="off" spellCheck={false} />
            <datalist id={`${id}-secrets`}>{secretNames.map((n) => <option key={n} value={n} />)}</datalist>
          </Field>
        </div>
      )}

      <div className="stack" style={{ gap: 8 }}>
        <span className="field__label">Settings that differ <Tip text="Recorded with the results so a table row can be traced to the exact configuration, for example chunk size or retriever." label="About metadata" /></span>
        {t.meta.map((r, i) => (
          <div key={i} className="frow" style={{ gap: 8, flexWrap: 'nowrap' }}>
            <input className="input" list="meta-keys" aria-label={`Setting name ${i + 1} for target ${index + 1}`} value={r.key} onChange={(e) => setMeta(i, { key: e.target.value })} placeholder="chunk_size" autoComplete="off" />
            <input className="input" aria-label={`Setting value ${i + 1} for target ${index + 1}`} value={r.value} onChange={(e) => setMeta(i, { value: e.target.value })} placeholder="512" autoComplete="off" />
            <button type="button" className="fbtn fbtn--ghost fbtn--sm" aria-label={`Remove setting ${i + 1} from target ${index + 1}`} onClick={() => set({ meta: t.meta.filter((_, j) => j !== i) })}>
              <span className="material-symbols-outlined" aria-hidden="true">close</span>
            </button>
          </div>
        ))}
        {errors.meta && <span className="field__error" role="alert">{errors.meta}</span>}
        <div><button type="button" className="fbtn fbtn--ghost fbtn--sm" disabled={t.meta.length >= MAX_METADATA} onClick={() => set({ meta: [...t.meta, { key: '', value: '' }] })}>Add a setting</button></div>
      </div>

      {all.length > 1 && (
        <div><button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={onRemove} data-testid={`remove-target-${index}`}>Remove target {index + 1}</button></div>
      )}
    </fieldset>
  );
};

export const TargetEditor: React.FC<{ targets: TargetDraft[]; secretNames: string[]; onChange: (t: TargetDraft[]) => void }> = ({ targets, secretNames, onChange }) => (
  <section className="stack" aria-labelledby="targets-h" data-testid="target-editor">
    <div>
      <h2 className="h2" id="targets-h" style={{ margin: 0 }}>Targets to compare <Tip text="Every target is asked the same questions the same number of times, so results are paired and can be compared fairly." /></h2>
      <p className="muted" style={{ margin: '4px 0 0' }}>Add up to {MAX_TARGETS}. With two or more you get a paired comparison; with one you get its own scorecard and decision.</p>
    </div>
    <datalist id="meta-keys">{META_KEYS.map((k) => <option key={k} value={k} />)}</datalist>
    {targets.map((t, i) => (
      <TargetRow key={i} index={i} target={t} all={targets} secretNames={secretNames}
        onChange={(next) => onChange(targets.map((x, j) => (j === i ? next : x)))} onRemove={() => onChange(targets.filter((_, j) => j !== i))} />
    ))}
    <div className="frow">
      <button type="button" className="fbtn fbtn--ghost" disabled={targets.length >= MAX_TARGETS} onClick={() => onChange([...targets, emptyTarget('endpoint')])} data-testid="add-target">
        <span className="material-symbols-outlined" aria-hidden="true">add</span>Add target
      </button>
      {targets.length >= MAX_TARGETS && <span className="muted">Maximum of {MAX_TARGETS} reached.</span>}
    </div>
  </section>
);
