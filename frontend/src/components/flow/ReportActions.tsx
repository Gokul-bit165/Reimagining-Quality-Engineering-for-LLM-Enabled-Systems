import React, { useState } from 'react';
import { ApiError, describeError } from '../../api';
import { describeReportError, reportApi, reportUrl, type ReportFormat, type ReportOwner } from '../../lib/campaign';
import { Banner } from './ui';

/** Trigger a browser download for a blob. Revokes the object URL right after the click. */
function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.rel = 'noopener';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** "QA report" actions for an evaluation or a campaign. Refusals (409/413) are shown in words. */
export const ReportActions: React.FC<{ owner: ReportOwner; disabledReason?: string | null }> = ({ owner, disabledReason }) => {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const disabled = Boolean(disabledReason);

  const run = async (key: string, what: 'report' | 'bundle', job: () => Promise<void>) => {
    setBusy(key); setError(null);
    try { await job(); } catch (e) {
      setError(e instanceof ApiError ? describeReportError(e.status, e.detail, what) : describeError(e, `the ${what}`));
    } finally { setBusy(null); }
  };

  const download = (format: ReportFormat) => run(format, 'report', async () => {
    const d = await reportApi.report(owner, format);
    saveBlob(d.blob, d.filename);
  });

  const openHtml = (e: React.MouseEvent) => {
    e.preventDefault();
    if (disabled) return;
    void run('html', 'report', async () => {
      const d = await reportApi.report(owner, 'html');
      const url = URL.createObjectURL(new Blob([d.blob], { type: 'text/html' }));
      window.open(url, '_blank', 'noopener');
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    });
  };

  const bundle = () => run('bundle', 'bundle', async () => {
    const d = await reportApi.bundle(owner);
    saveBlob(d.blob, d.filename);
  });

  return (
    <section className="panel stack" aria-labelledby={`rep-h-${owner.id}`} data-testid="report-actions">
      <div>
        <h2 className="h2" id={`rep-h-${owner.id}`} style={{ margin: 0 }}>QA report</h2>
        <p className="muted" style={{ margin: '4px 0 0' }}>
          A written report for the quality team, built from the recorded evidence. The bundle is for auditors: it carries the recorded calls and a hash chain.
        </p>
      </div>
      {disabledReason && <Banner tone="info" role="status">{disabledReason}</Banner>}
      <div className="frow">
        <a className="fbtn" href={reportUrl(owner, 'html')} target="_blank" rel="noopener noreferrer" onClick={openHtml}
          aria-disabled={disabled || busy === 'html'} data-testid="report-open-html">
          <span className="material-symbols-outlined" aria-hidden="true">open_in_new</span>{busy === 'html' ? 'Building…' : 'Open report (HTML)'}
        </a>
        <button type="button" className="fbtn fbtn--ghost" disabled={disabled || busy !== null} onClick={() => void download('md')} data-testid="report-md">Download Markdown</button>
        <button type="button" className="fbtn fbtn--ghost" disabled={disabled || busy !== null} onClick={() => void download('json')} data-testid="report-json">Download JSON</button>
        <button type="button" className="fbtn fbtn--ghost" disabled={disabled || busy !== null} onClick={() => void bundle()} data-testid="report-bundle">
          <span className="material-symbols-outlined" aria-hidden="true">folder_zip</span>{busy === 'bundle' ? 'Building bundle…' : 'Download evidence bundle (zip)'}
        </button>
      </div>
      {error && <Banner tone="bad" role="alert"><span data-testid="report-error">{error}</span></Banner>}
      <details>
        <summary className="h3" style={{ cursor: 'pointer', margin: 0 }}>How an auditor checks the bundle</summary>
        <div className="stack" style={{ marginTop: 8, gap: 8 }}>
          <p className="muted" style={{ margin: 0 }}>
            The bundle holds every recorded call and verdict in a tamper-evident ledger. Each entry includes the hash of the one before it, so changing any entry breaks every hash after it.
            The <strong>ledger head hash</strong> is the hash of the last entry: it summarises the whole record. Copy it into a ticket or sign it, and anyone can later confirm the bundle is unchanged.
          </p>
          <pre className="fquote" style={{ margin: 0 }}>qe verify-bundle evidence-bundle-{owner.id}.zip</pre>
          <p className="muted" style={{ margin: 0 }}>
            That command recomputes the hash chain and prints the head hash. If it differs from the anchor you saved, the evidence was altered.
            The bundle is withheld, never partially exported, if a secret value is found in it.
          </p>
        </div>
      </details>
    </section>
  );
};
