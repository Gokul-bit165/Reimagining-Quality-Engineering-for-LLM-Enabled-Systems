import React, { useState } from 'react';
import { describeError } from '../../api';
import { evaluationsApi } from '../../lib/projects';
import { ADVISORY_NOTE } from '../../lib/campaign';
import { Banner } from '../../components/flow/ui';
import type { EvalItem, Evaluation } from '../../types/api';

/** Confirm model-written (advisory) questions so they count towards the decision. Scores are recomputed from recorded answers. */
export const AdvisoryConfirm: React.FC<{ ev: Evaluation; advisory: EvalItem[]; onDone: () => void }> = ({ ev, advisory, onDone }) => {
  const [reviewer, setReviewer] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reviewed = ev.decision !== null && ev.decision.status !== 'pending_review';
  if (advisory.length === 0) return null;

  const confirm = async (id: string) => {
    if (!reviewer.trim()) { setError('Enter the reviewer name first.'); return; }
    setBusy(id); setError(null);
    try { await evaluationsApi.confirmItem(ev.id, id, reviewer.trim()); onDone(); }
    catch (e) { setError(describeError(e, 'confirming this question')); }
    finally { setBusy(null); }
  };

  return (
    <section className="panel stack" aria-labelledby="adv-ev-h" data-testid="advisory-confirm">
      <div>
        <h2 className="h2" id="adv-ev-h" style={{ margin: 0 }}>Advisory questions ({advisory.length})</h2>
        <p className="muted" style={{ margin: '4px 0 0' }}>{ADVISORY_NOTE} Confirming one includes it in the decision; scores are recomputed from the recorded answers.</p>
      </div>
      {reviewed && <Banner tone="info" role="status">The decision was already reviewed, so questions can no longer be confirmed. Run a new evaluation to include them.</Banner>}
      <div className="field" style={{ maxWidth: 360 }}>
        <label className="field__label" htmlFor="adv-ev-name">Reviewer name</label>
        <input id="adv-ev-name" className="input" value={reviewer} onChange={(e) => setReviewer(e.target.value)} autoComplete="name" />
      </div>
      {error && <Banner tone="bad" role="alert">{error}</Banner>}
      <ul className="items">
        {advisory.map((i) => (
          <li key={i.id} className="item frow frow--between" style={{ padding: '10px 14px' }}>
            <span style={{ flex: 1, minWidth: 200 }}>{i.question}</span>
            <button type="button" className="fbtn fbtn--ghost fbtn--sm" disabled={reviewed || busy !== null} onClick={() => void confirm(i.id)}
              aria-label={`Confirm question: ${i.question.slice(0, 80)}`} data-testid={`confirm-${i.id}`}>{busy === i.id ? 'Confirming…' : 'Confirm'}</button>
          </li>
        ))}
      </ul>
    </section>
  );
};
