import React, { useState } from 'react';
import { describeError } from '../../api';
import { campaignsApi } from '../../lib/campaign';
import { usePoll } from '../../hooks/usePoll';
import { Banner, Loading } from '../../components/flow/ui';
import type { Campaign, LedgerEntry } from '../../types/campaign';

const fmtAt = (at: LedgerEntry['at']): string => {
  if (at === null || at === undefined) return '';
  const d = typeof at === 'number' ? new Date(at * 1000) : new Date(at);
  return Number.isNaN(d.getTime()) ? String(at) : d.toLocaleString();
};

const HUMAN: Record<string, string> = { human: 'person', deterministic: 'rules', llm_agent: 'model' };

/** The hash-chained audit trail. A broken chain is shown as a failure, never hidden. */
export const AuditTrail: React.FC<{ campaign: Campaign }> = ({ campaign }) => {
  const [withRuns, setWithRuns] = useState(false);
  const ev = usePoll(() => campaignsApi.events(campaign.id, withRuns), () => false, [campaign.id, withRuns, campaign.state, campaign.stages.review?.status]);
  const data = ev.data;

  if (ev.loading && !data) return <Loading label="Reading the audit trail…" />;
  if (!data) return <Banner tone="bad" role="alert">Could not load the audit trail. {describeError(ev.error, 'the audit trail')}</Banner>;
  return (
    <section className="panel stack" aria-labelledby="au-h" data-testid="audit-trail">
      <div className="frow frow--between">
        <h2 className="h2" id="au-h" style={{ margin: 0 }}>Audit trail</h2>
        <span className="badge" data-tone={data.ledger_ok ? 'ok' : 'bad'} data-testid="ledger-badge" role="status">
          {data.ledger_ok ? 'LEDGER VERIFIED' : 'LEDGER BROKEN'}
        </span>
      </div>
      <p className="muted" style={{ margin: 0 }}>
        Every stage change, every human action and every call to a target is recorded in a hash chain: each entry carries the hash of the one before it.
        {data.ledger_ok
          ? ` The chain of ${data.ledger_entries} entries checks out, so nothing was changed after the fact.`
          : ' The chain does NOT check out: an entry was altered, removed or reordered. Do not rely on these results.'}
      </p>
      {!data.ledger_ok && <Banner tone="bad" role="alert">The ledger failed verification. Treat every result of this campaign as untrusted until the cause is found.</Banner>}
      <p className="field__hint" style={{ margin: 0 }}>{data.recorded_target_calls} recorded call{data.recorded_target_calls === 1 ? '' : 's'} to targets{withRuns ? ' (listed below)' : ' are hidden by default'}.</p>
      <label className="fcheck"><input type="checkbox" checked={withRuns} onChange={(e) => setWithRuns(e.target.checked)} /><span>Include every recorded target call</span></label>
      {data.entries.length === 0 ? <div className="fempty">No events recorded yet.</div> : (
        <div className="tablewrap">
          <table className="table">
            <thead><tr><th scope="col">#</th><th scope="col">When</th><th scope="col">Event</th><th scope="col">By</th><th scope="col">Hash</th></tr></thead>
            <tbody>
              {data.entries.map((e) => (
                <tr key={e.seq} data-testid="audit-row">
                  <td>{e.seq}</td>
                  <td>{fmtAt(e.at)}</td>
                  <td>
                    <strong>{e.action ?? e.type}</strong>
                    <div className="field__hint">{e.key}</div>
                    {Object.keys(e.payload).length > 0 && (
                      <details><summary className="field__hint" style={{ cursor: 'pointer' }}>Details</summary><pre className="fquote">{JSON.stringify(e.payload, null, 2)}</pre></details>
                    )}
                  </td>
                  <td>{e.producer} <span className="field__hint">({HUMAN[e.producer_kind] ?? e.producer_kind})</span></td>
                  <td><code className="fmono" title={e.hash}>{e.hash.slice(0, 12)}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.total > data.entries.length && <p className="field__hint" style={{ margin: 0 }}>Showing the first {data.entries.length} of {data.total} entries.</p>}
    </section>
  );
};
