import React, { useMemo, useState } from 'react';
import { describeError } from '../../api';
import { ADVISORY_NOTE, campaignsApi } from '../../lib/campaign';
import { Banner, Tip } from '../../components/flow/ui';
import type { Campaign } from '../../types/campaign';

const TargetSignoff: React.FC<{ campaign: Campaign; label: string; reviewer: string; onDone: () => void }> = ({ campaign, label, reviewer, onDone }) => {
  const [decision, setDecision] = useState<'approve' | 'reject'>('approve');
  const [rationale, setRationale] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const dec = campaign.results[label]?.decision;
  const id = `so-${label.replace(/\W+/g, '_')}`;

  if (!dec) return null;
  if (dec.status !== 'pending_review') {
    const approved = dec.signoff?.decision.startsWith('approve');
    return (
      <div className="panel panel--flat stack" style={{ gap: 6 }} data-testid={`signed-${label}`}>
        <div className="frow"><strong>{label}</strong><span className="badge" data-tone={approved ? 'ok' : 'bad'}>{approved ? 'APPROVED' : 'REJECTED'}</span></div>
        {dec.signoff && <p className="muted" style={{ margin: 0 }}>{dec.signoff.reviewer}{dec.signoff.rationale ? `: "${dec.signoff.rationale}"` : ''}</p>}
      </div>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reviewer.trim() || !rationale.trim()) { setErr('A reviewer name (above) and a written rationale are both required.'); return; }
    setBusy(true); setErr(null);
    try { await campaignsApi.signoff(campaign.id, { reviewer: reviewer.trim(), decision, rationale: rationale.trim(), target_label: label }); onDone(); }
    catch (x) { setErr(describeError(x, 'sign-off')); }
    finally { setBusy(false); }
  };

  return (
    <form className="panel panel--flat stack" onSubmit={submit} aria-labelledby={`${id}-h`} data-testid={`signoff-form-${label}`}>
      <div className="frow"><h3 className="h3" id={`${id}-h`} style={{ margin: 0 }}>Sign off: {label}</h3><span className="badge" data-tone="warn">PENDING REVIEW</span></div>
      <p className="muted" style={{ margin: 0 }}>Policy decision: <strong>{dec.verdict.replace('_', ' ')}</strong>{dec.policy_is_example ? ' (example policy, illustrative only)' : ''}. Confirm or override it for this target.</p>
      <div className="field">
        <label className="field__label" htmlFor={`${id}-d`}>Your decision</label>
        <select id={`${id}-d`} className="select" value={decision} onChange={(e) => setDecision(e.target.value as 'approve' | 'reject')}>
          <option value="approve">Approve the recommendation</option>
          <option value="reject">Reject the recommendation</option>
        </select>
      </div>
      <div className="field">
        <label className="field__label" htmlFor={`${id}-r`}>Rationale</label>
        <textarea id={`${id}-r`} className="textarea" style={{ fontFamily: 'var(--font-hanken)', fontSize: 14 }} value={rationale} onChange={(e) => setRationale(e.target.value)} />
      </div>
      {err && <Banner tone="bad" role="alert">{err}</Banner>}
      <div><button type="submit" className="fbtn" disabled={busy} data-testid={`record-signoff-${label}`}>{busy ? 'Recording…' : `Record sign-off for ${label}`}</button></div>
    </form>
  );
};

/** Human review: one sign-off per target, and confirmation of advisory (model-written) cases. */
export const ReviewPanel: React.FC<{ campaign: Campaign; onChanged: () => void }> = ({ campaign, onChanged }) => {
  const [reviewer, setReviewer] = useState('');
  const [confirming, setConfirming] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const labels = campaign.targets.map((t) => t.label).filter((l) => campaign.results[l]);
  const done = campaign.state === 'done';
  const anyReviewed = labels.some((l) => campaign.results[l].decision?.status !== 'pending_review');

  const advisory = useMemo(() => {
    const first = campaign.results[labels[0]]?.items ?? [];
    return first.filter((i) => i.advisory);
  }, [campaign.results, labels]);

  const confirm = async (itemId: string) => {
    if (!reviewer.trim()) { setError('Enter the reviewer name first.'); return; }
    setConfirming(itemId); setError(null);
    try { await campaignsApi.confirmItem(campaign.id, itemId, reviewer.trim()); onChanged(); }
    catch (e) { setError(describeError(e, 'confirming this case')); }
    finally { setConfirming(null); }
  };

  if (!done || labels.length === 0) return <div className="fempty">Human review opens when the campaign has finished.</div>;
  return (
    <div className="stack" data-testid="review-panel">
      <section className="panel stack" aria-labelledby="rv-h">
        <div>
          <h2 className="h2" id="rv-h" style={{ margin: 0 }}>Human review <Tip text="A named person confirms or overrides each target's decision. The reviewer, decision and reason go into the audit trail." /></h2>
          <p className="muted" style={{ margin: '4px 0 0' }}>The tool computes the decision; a person owns it. Each target is signed off separately.</p>
        </div>
        <div className="field" style={{ maxWidth: 360 }}>
          <label className="field__label" htmlFor="rv-name">Reviewer name</label>
          <input id="rv-name" className="input" value={reviewer} onChange={(e) => setReviewer(e.target.value)} autoComplete="name" data-testid="reviewer-name" />
        </div>
        {error && <Banner tone="bad" role="alert">{error}</Banner>}
      </section>

      {labels.map((l) => <TargetSignoff key={l} campaign={campaign} label={l} reviewer={reviewer} onDone={onChanged} />)}

      <section className="panel stack" aria-labelledby="adv-h" data-testid="advisory-section">
        <div>
          <h2 className="h2" id="adv-h" style={{ margin: 0 }}>Advisory cases ({advisory.length})</h2>
          <p className="muted" style={{ margin: '4px 0 0' }}>{ADVISORY_NOTE} Confirming a case includes it in every target&apos;s decision, then scores are recomputed from the recorded answers (no new calls).</p>
        </div>
        {anyReviewed && advisory.length > 0 && <Banner tone="info" role="status">A decision has already been reviewed, so cases can no longer be confirmed. Start a new campaign to include them.</Banner>}
        {advisory.length === 0 ? <p className="muted" style={{ margin: 0 }}>No advisory cases: every case was written by rules or by you.</p> : (
          <ul className="items">
            {advisory.map((i) => (
              <li key={i.id} className="item frow frow--between" style={{ padding: '10px 14px' }}>
                <span style={{ flex: 1, minWidth: 200 }}>{i.question}</span>
                <button type="button" className="fbtn fbtn--ghost fbtn--sm" disabled={anyReviewed || confirming !== null} onClick={() => void confirm(i.id)}
                  aria-label={`Confirm case: ${i.question.slice(0, 80)}`} data-testid={`confirm-${i.id}`}>
                  {confirming === i.id ? 'Confirming…' : 'Confirm'}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
};
