import React, { useEffect, useState } from 'react';
import { describeError } from '../../api';
import { badgeTone, STATE_TEXT, STAGE_LABEL, campaignsApi, fmtDuration, isCampaignActive, stageTone, stateTone } from '../../lib/campaign';
import { Banner } from '../../components/flow/ui';
import { STAGE_ORDER, type Campaign, type StageRecord } from '../../types/campaign';

const STATUS_WORD: Record<string, string> = {
  pending: 'PENDING', running: 'RUNNING', done: 'DONE', failed: 'FAILED', cancelled: 'CANCELLED', awaiting_review: 'AWAITING REVIEW',
};

/** One-line, honest summary of what a finished stage recorded. */
function stageDetail(name: string, st: StageRecord, c: Campaign): string {
  const d = st.detail ?? {};
  if (name === 'execution') return `${c.progress.done} of ${c.progress.total || '?'} calls recorded`;
  if (name === 'verification' && typeof d.n_cases_compared === 'number') {
    const ex = typeof d.excluded_cases === 'number' && d.excluded_cases > 0 ? `, ${d.excluded_cases} excluded (not answered by every target)` : '';
    return `${d.n_cases_compared} cases compared${ex}`;
  }
  if (name === 'scoring' && typeof d.targets_scored === 'number') return `${d.targets_scored} target${d.targets_scored === 1 ? '' : 's'} scored`;
  if (name === 'comparison' && typeof d.pairs === 'number') return `${d.pairs} paired comparison${d.pairs === 1 ? '' : 's'}`;
  if (name === 'review' && Array.isArray(d.awaiting)) return d.awaiting.length ? `awaiting sign-off: ${d.awaiting.join(', ')}` : 'all targets signed off';
  return '';
}

export const StageTracker: React.FC<{ campaign: Campaign; onChanged: () => void }> = ({ campaign: c, onChanged }) => {
  const [now, setNow] = useState(() => Date.now() / 1000);
  const [busy, setBusy] = useState<'resume' | 'cancel' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const active = isCampaignActive(c.state);
  useEffect(() => {
    if (!active) return undefined;
    const t = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(t);
  }, [active]);

  const act = async (kind: 'resume' | 'cancel') => {
    setBusy(kind); setError(null);
    try { await (kind === 'resume' ? campaignsApi.resume(c.id) : campaignsApi.cancel(c.id)); onChanged(); }
    catch (e) { setError(describeError(e, kind === 'resume' ? 'resuming' : 'cancelling')); }
    finally { setBusy(null); }
  };

  const { done, total } = c.progress;
  const pctDone = total > 0 ? Math.round((done / total) * 100) : 0;
  return (
    <div className="stack" data-testid="stage-tracker">
      <section className="panel stack" aria-live="polite" aria-labelledby="st-h">
        <div className="frow frow--between">
          <h2 className="h2" id="st-h" style={{ margin: 0 }}>Progress</h2>
          <span className="badge" data-tone={badgeTone(stateTone(c.state))} data-testid="campaign-state">{c.state.toUpperCase()}</span>
        </div>
        <div className="frow">{active && <span className="spinner" aria-hidden="true" />}<span className="muted">{STATE_TEXT[c.state]}</span></div>
        {total > 0 && (
          <>
            <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done} aria-label="Calls to targets"><div className="progress__bar" style={{ width: `${pctDone}%` }} /></div>
            <p className="muted" style={{ margin: 0 }} data-testid="campaign-progress">{done} of {total} calls to targets ({pctDone}%)</p>
          </>
        )}
        {c.error && <Banner tone="bad" role="alert"><span><strong>Error:</strong> {c.error}</span></Banner>}
        {c.incomplete && <Banner tone="warn" role="status"><span data-testid="campaign-incomplete"><strong>Incomplete.</strong> {c.incomplete} Results below cover only what finished, and decisions fall back to insufficient evidence.</span></Banner>}
        {c.resumable && (
          <Banner tone="info" role="status">
            <span data-testid="resume-banner"><strong>This campaign can be resumed.</strong> Everything already recorded is kept; only the missing work runs.
              {' '}If the project&apos;s documents or questions changed since it started, the server will refuse and you will need a new campaign.</span>
          </Banner>
        )}
        {error && <Banner tone="bad" role="alert">{error}</Banner>}
        <div className="frow">
          {c.resumable && <button type="button" className="fbtn" disabled={busy !== null} onClick={() => void act('resume')} data-testid="resume-campaign">{busy === 'resume' ? 'Resuming…' : 'Resume'}</button>}
          {active && c.state !== 'cancelling' && <button type="button" className="fbtn fbtn--ghost" disabled={busy !== null} onClick={() => void act('cancel')} data-testid="cancel-campaign">{busy === 'cancel' ? 'Cancelling…' : 'Cancel'}</button>}
          {c.state === 'cancelled' && !c.resumable && <span className="muted">Cancelled.</span>}
        </div>
      </section>

      <ol className="stagelist" aria-label="Pipeline stages">
        {STAGE_ORDER.map((name, i) => {
          const st = c.stages[name];
          if (!st) return null;
          const tone = stageTone(st.status);
          const info = STAGE_LABEL[name];
          const summary = stageDetail(name, st, c);
          const dur = fmtDuration(st.started, st.ended, now);
          return (
            <li key={name} className="stagerow" data-tone={tone} data-status={st.status} data-testid={`stage-${name}`}>
              <span className="stagerow__n" aria-hidden="true">{i + 1}</span>
              <div className="stagerow__main">
                <div className="frow" style={{ gap: 8 }}>
                  <strong>{info.title}</strong>
                  <span className="badge" data-tone={badgeTone(tone)}>{STATUS_WORD[st.status] ?? st.status}</span>
                  {dur && <span className="muted">{dur}{st.status === 'running' ? ' so far' : ''}</span>}
                </div>
                <p className="field__hint" style={{ margin: '2px 0 0' }}>{info.text}{summary ? ` ${summary}.` : ''}</p>
                {st.error && <p className="field__error" role="alert" style={{ margin: '4px 0 0' }}>{st.error}</p>}
              </div>
            </li>
          );
        })}
      </ol>
      {c.notes.length > 0 && (
        <section className="panel panel--flat" aria-labelledby="cn-h">
          <h2 className="h3" id="cn-h">Notes from the run</h2>
          <ul style={{ margin: 0, paddingLeft: 18 }} className="muted">{c.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </section>
      )}
    </div>
  );
};
