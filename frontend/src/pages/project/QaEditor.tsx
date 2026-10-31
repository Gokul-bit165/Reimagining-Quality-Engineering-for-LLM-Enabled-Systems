import React, { useState } from 'react';
import type { ProjectQaPair } from '../../types/api';

type Tri = 'unknown' | 'yes' | 'no';

export const triOf = (a: boolean | null | undefined): Tri => (a === true ? 'yes' : a === false ? 'no' : 'unknown');
export const answerableOf = (t: Tri): boolean | null => (t === 'yes' ? true : t === 'no' ? false : null);

const TRI_LABEL: Record<Tri, string> = { unknown: 'Unknown', yes: 'Answerable', no: 'Not answerable' };

/** Drop empty answerable and, for "not answerable", the reference answer (the backend rejects both together). */
export function cleanPairs(pairs: ProjectQaPair[]): ProjectQaPair[] {
  return pairs.filter((p) => p.question.trim()).map((p) => {
    const out: ProjectQaPair = { question: p.question.trim() };
    if (p.answerable === false) out.answerable = false;
    else {
      if (p.reference_answer?.trim()) out.reference_answer = p.reference_answer.trim();
      if (p.answerable === true) out.answerable = true;
    }
    return out;
  });
}

interface Props { pairs: ProjectQaPair[]; onChange: (next: ProjectQaPair[]) => void }

export const QaEditor: React.FC<Props> = ({ pairs, onChange }) => {
  const [q, setQ] = useState('');
  const [ref, setRef] = useState('');
  const [tri, setTri] = useState<Tri>('unknown');

  const patch = (i: number, p: Partial<ProjectQaPair>) => onChange(pairs.map((x, j) => (j === i ? { ...x, ...p } : x)));
  const setAnswerable = (i: number, t: Tri) => {
    const answerable = answerableOf(t);
    patch(i, answerable === false ? { answerable, reference_answer: '' } : { answerable });
  };
  const add = () => {
    if (!q.trim()) return;
    const a = answerableOf(tri);
    onChange([...pairs, { question: q.trim(), ...(a === false || !ref.trim() ? {} : { reference_answer: ref.trim() }), ...(a === null ? {} : { answerable: a }) }]);
    setQ(''); setRef(''); setTri('unknown');
  };
  const unchecked = pairs.filter((p) => !p.reference_answer?.trim() && (p.answerable === undefined || p.answerable === null)).length;

  return (
    <div className="stack" data-testid="qa-editor">
      <p className="field__hint" style={{ margin: 0 }}>
        Mark each question <strong>Answerable</strong> if your documents answer it, <strong>Not answerable</strong> if they do not (the app should then refuse), or leave it <strong>Unknown</strong>.
        A question with no reference answer and an unknown status cannot be checked: it is reported as &quot;Not checked&quot; and left out of every rate.
        {unchecked > 0 && <> <strong data-testid="qa-unchecked">{unchecked} of {pairs.length} would currently be unchecked.</strong></>}
      </p>
      {pairs.length > 0 && (
        <ul className="items" aria-label="Questions" style={{ maxHeight: 420, overflowY: 'auto' }}>
          {pairs.map((p, i) => (
            <li key={i} className="item stack" style={{ padding: 12, gap: 8 }} data-testid="qa-row">
              <div className="field">
                <label className="field__label" htmlFor={`qa-q-${i}`}>Question {i + 1}</label>
                <input id={`qa-q-${i}`} className="input" value={p.question} onChange={(e) => patch(i, { question: e.target.value })} />
              </div>
              <div className="grid2">
                <div className="field">
                  <label className="field__label" htmlFor={`qa-r-${i}`}>Reference answer</label>
                  <input id={`qa-r-${i}`} className="input" value={p.reference_answer ?? ''} disabled={p.answerable === false}
                    placeholder={p.answerable === false ? 'Not used: the expected behaviour is a refusal' : 'Optional'} onChange={(e) => patch(i, { reference_answer: e.target.value })} />
                </div>
                <div className="field">
                  <label className="field__label" htmlFor={`qa-a-${i}`}>Can the documents answer it?</label>
                  <select id={`qa-a-${i}`} className="select" value={triOf(p.answerable)} onChange={(e) => setAnswerable(i, e.target.value as Tri)}>
                    {(Object.keys(TRI_LABEL) as Tri[]).map((t) => <option key={t} value={t}>{TRI_LABEL[t]}</option>)}
                  </select>
                </div>
              </div>
              <div><button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={() => onChange(pairs.filter((_, j) => j !== i))} aria-label={`Remove question ${i + 1}`}>Remove</button></div>
            </li>
          ))}
        </ul>
      )}
      <fieldset className="stack" style={{ border: '1px dashed var(--c-line)', borderRadius: 'var(--r-md)', padding: 'var(--s-3)', margin: 0 }}>
        <legend className="h3" style={{ padding: '0 6px' }}>Add a question</legend>
        <div className="field">
          <label className="field__label" htmlFor="qa-new-q">Question</label>
          <input id="qa-new-q" className="input" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="grid2">
          <div className="field">
            <label className="field__label" htmlFor="qa-new-r">Reference answer (optional)</label>
            <input id="qa-new-r" className="input" value={ref} disabled={tri === 'no'} onChange={(e) => setRef(e.target.value)} />
          </div>
          <div className="field">
            <label className="field__label" htmlFor="qa-new-a">Can the documents answer it?</label>
            <select id="qa-new-a" className="select" value={tri} onChange={(e) => setTri(e.target.value as Tri)}>
              {(Object.keys(TRI_LABEL) as Tri[]).map((t) => <option key={t} value={t}>{TRI_LABEL[t]}</option>)}
            </select>
          </div>
        </div>
        <div><button type="button" className="fbtn fbtn--ghost fbtn--sm" disabled={!q.trim()} onClick={add}>Add question</button></div>
      </fieldset>
    </div>
  );
};
