import React, { useCallback, useEffect, useState } from 'react';
import { describeError } from '../../api';
import { fmtInterval, judgeApi, parseCalibrationText, MAX_CALIBRATION_ITEMS } from '../../lib/campaign';
import { num, pct } from '../../lib/explain';
import { Banner, Field, Loading, Tip } from '../../components/flow/ui';
import type { CalibrationHistory, CalibrationItem, CalibrationRecord, JudgeStatus } from '../../types/campaign';

const FORMAT_HELP = 'JSONL: one object per line, for example {"question":"…","reference":"30 days","answer":"90 days","label":"incorrect"}. CSV: header row with answer, label and reference (correctness) or context (faithfulness); optional question and kind. Labels: correct, incorrect, partial, refusal, unanswerable.';

export const CalibrationRecordView: React.FC<{ record: CalibrationRecord }> = ({ record }) => (
  <div className="stack" data-testid="calibration-record" style={{ gap: 8 }}>
    <dl className="ffacts">
      <dt>Items labelled by you</dt><dd>{record.n}</dd>
      <dt>Agreement with your labels</dt><dd>{record.agreement === null ? 'not measured' : `${pct(record.agreement, 1)} (${Math.round(record.confidence * 100)}% CI ${fmtInterval(record.agreement_ci)})`}</dd>
      <dt>Cohen&apos;s kappa</dt><dd>{record.kappa === null ? 'not measured' : num(record.kappa, 2)}</dd>
      <dt>False passes</dt>
      <dd>{record.false_pass_rate === null ? 'No defective answers in the set, so not measured'
        : `${pct(record.false_pass_rate, 1)} of defective answers were passed by the judge (${fmtInterval(record.false_pass_ci)})`}</dd>
      <dt>Recorded</dt><dd>{record.created_at} · record <code className="fmono">{record.id.slice(0, 12)}</code></dd>
    </dl>
    {record.members.length > 1 && (
      <div className="tablewrap">
        <table className="table">
          <caption className="muted" style={{ textAlign: 'left', paddingBottom: 6 }}>Panel members, each measured on its own</caption>
          <thead><tr><th scope="col">Model</th><th scope="col">Family</th><th scope="col">Agreement (CI)</th><th scope="col">Decided / abstained</th></tr></thead>
          <tbody>{record.members.map((m) => (
            <tr key={m.model}><th scope="row">{m.model}</th><td>{m.family ?? 'unknown'}</td>
              <td>{m.agreement === null ? 'n/a' : `${pct(m.agreement, 1)} (${fmtInterval(m.agreement_ci)})`}</td><td>{m.n_decided} / {m.n_abstain}</td></tr>
          ))}</tbody>
        </table>
      </div>
    )}
    {record.panel?.correlated_errors && <Banner tone="warn" role="status">The two judges make the same mistakes together, so a second judge adds less independent evidence than it appears to.</Banner>}
    {record.budget_exhausted && <Banner tone="warn" role="status">The judge call budget ran out, so some items were not judged. The record covers the items that were.</Banner>}
  </div>
);

export const JudgeStatusPanel: React.FC<{ status: JudgeStatus | null; error: string | null; onRetry?: () => void; compact?: boolean }> = ({ status, error, onRetry, compact }) => {
  if (error) {
    return <Banner tone="bad" role="alert"><span>Could not read the judge status. {error}{onRetry && <> <button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={onRetry}>Retry</button></>}</span></Banner>;
  }
  if (!status) return <Loading label="Checking the judge…" />;
  const cal = status.calibration;
  return (
    <div className="stack" data-testid="judge-status" style={{ gap: 12 }}>
      <div className="frow">
        <span className="badge" data-tone={status.configured ? 'ok' : 'warn'}>{status.configured ? 'JUDGE CONFIGURED' : 'NO JUDGE'}</span>
        {status.configured && <span className="badge" data-tone={status.independent ? 'ok' : 'bad'} data-testid="judge-independence">{status.independent ? 'INDEPENDENT' : 'NOT INDEPENDENT'}</span>}
        {cal?.stale && <span className="badge" data-tone="warn" data-testid="judge-stale">CALIBRATION STALE</span>}
        {status.second_judge && <span className="badge">SECOND JUDGE</span>}
      </div>
      <p style={{ margin: 0 }}>{status.independence_reason}</p>
      {!compact && (
        <dl className="ffacts">
          <dt>Judge model</dt><dd>{status.judge_model ?? 'none configured'}</dd>
          <dt>Judge family</dt><dd>{status.judge_family ?? 'unknown'}</dd>
          <dt>Question-writer family</dt><dd>{status.generator_family ?? 'none or unknown'}</dd>
          <dt>Calibration</dt>
          <dd>{cal ? `${pct(cal.agreement, 1)} agreement with your labels (95% CI ${fmtInterval(cal.ci)}) on ${cal.n} items${cal.stale ? '. STALE: the judge model or prompt changed since' : ''}`
            : 'none yet for this judge. Until one exists the judge is advisory.'}</dd>
          <dt>Role</dt><dd>{status.gating}</dd>
        </dl>
      )}
      {status.missing.length > 0 && (
        <Banner tone="warn" role="status">
          <span data-testid="judge-missing"><strong>Missing server settings:</strong>{' '}
            {status.missing.map((n) => <code key={n} className="fchip" style={{ marginRight: 6 }}>{n}</code>)}
            Only names are shown, never values. Set them in the backend environment and restart it.</span>
        </Banner>
      )}
      {status.notes.length > 0 && <ul className="muted" style={{ margin: 0, paddingLeft: 18 }}>{status.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
    </div>
  );
};

const CalibrationForm: React.FC<{ judgeReady: boolean; onDone: () => void }> = ({ judgeReady, onDone }) => {
  const [text, setText] = useState('');
  const [fileName, setFileName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [record, setRecord] = useState<CalibrationRecord | null>(null);
  const parsed = text.trim() ? parseCalibrationText(text, fileName) : null;
  const items: CalibrationItem[] = parsed?.items ?? [];
  const canRun = judgeReady && items.length > 0 && !busy && (parsed?.errors.length ?? 0) === 0;

  const onFile = async (files: FileList | null) => {
    const f = files?.[0];
    if (!f) return;
    setFileName(f.name); setText(await f.text()); setRecord(null); setError(null);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canRun) return;
    setBusy(true); setError(null); setRecord(null);
    try { setRecord(await judgeApi.calibrate(items)); onDone(); }
    catch (err) { setError(describeError(err, 'judge calibration')); }
    finally { setBusy(false); }
  };

  return (
    <form className="panel stack" onSubmit={submit} aria-labelledby="cal-h" data-testid="calibration-form">
      <div>
        <h2 className="h2" id="cal-h" style={{ margin: 0 }}>Calibrate the judge <Tip text="Measures how often the judge agrees with your own labels. The agreement and its interval decide whether the judge may gate, never a number the tool invents." /></h2>
        <p className="muted" style={{ margin: '4px 0 0' }}>Label real answers yourself, then see how closely the judge agrees. Up to {MAX_CALIBRATION_ITEMS} items. Each judge call is a real model call.</p>
      </div>
      <Field label="Upload labelled items (.jsonl or .csv)" htmlFor="cal-file" hint={FORMAT_HELP}>
        <input id="cal-file" className="input" type="file" accept=".jsonl,.ndjson,.csv,.json,text/csv" onChange={(e) => void onFile(e.target.files)} />
      </Field>
      <Field label="Or paste them" htmlFor="cal-paste">
        <textarea id="cal-paste" className="textarea" value={text} onChange={(e) => { setText(e.target.value); setFileName(''); setRecord(null); }}
          placeholder={'{"question":"What is the refund window?","reference":"30 days","answer":"90 days","label":"incorrect"}'} />
      </Field>
      {parsed && (
        <div role="status" data-testid="calibration-parse">
          <p style={{ margin: 0 }}><strong>{items.length} valid item{items.length === 1 ? '' : 's'}</strong>{parsed.rows !== items.length ? ` of ${parsed.rows} rows` : ''}.</p>
          {parsed.errors.length > 0 && <ul className="field__error" style={{ margin: '4px 0 0', paddingLeft: 18 }}>{parsed.errors.map((m) => <li key={m}>{m}</li>)}</ul>}
        </div>
      )}
      {!judgeReady && <Banner tone="info" role="status">The judge is not configured on the server, so a calibration cannot run yet (see the status above).</Banner>}
      {error && <Banner tone="bad" role="alert"><span data-testid="calibration-error">{error}</span></Banner>}
      <div><button type="submit" className="fbtn" disabled={!canRun} data-testid="calibrate-run">{busy ? <><span className="spinner" aria-hidden="true" /> Calibrating…</> : 'Run calibration'}</button></div>
      {record && <section aria-label="Calibration result"><h3 className="h3">Result</h3><CalibrationRecordView record={record} /></section>}
    </form>
  );
};

/** Full 'Judge & calibration' area: status, calibration form, and past records. */
export const JudgePage: React.FC = () => {
  const [status, setStatus] = useState<JudgeStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<CalibrationHistory | null>(null);

  const load = useCallback(() => {
    setError(null);
    judgeApi.status().then(setStatus).catch((e: unknown) => setError(describeError(e, 'the judge status')));
    judgeApi.history().then(setHistory).catch(() => setHistory(null));
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="stack">
      <section className="panel stack" aria-labelledby="js-h">
        <div>
          <h2 className="h2" id="js-h" style={{ margin: 0 }}>Semantic judge <Tip text="A second model that reads answers for meaning. It never decides on its own: it is advisory unless your policy sets a minimum agreement and a fresh calibration meets it." /></h2>
          <p className="muted" style={{ margin: '4px 0 0' }}>
            Rules decide verdicts. The judge helps with answers that are worded differently from the reference. It must come from a different model family than the one that wrote the questions, otherwise it would grade its own homework.
          </p>
        </div>
        <JudgeStatusPanel status={status} error={error} onRetry={load} />
      </section>
      <CalibrationForm judgeReady={Boolean(status?.configured)} onDone={load} />
      <section className="panel stack" aria-labelledby="ch-h">
        <h2 className="h2" id="ch-h" style={{ margin: 0 }}>Calibration records</h2>
        {!history ? <p className="muted" style={{ margin: 0 }}>No records could be read.</p>
          : history.latest === null ? <div className="fempty">No calibration has been run yet.</div>
            : (
              <>
                <h3 className="h3" style={{ margin: 0 }}>Latest</h3>
                <CalibrationRecordView record={history.latest} />
                {history.records.length > 1 && (
                  <div className="tablewrap">
                    <table className="table">
                      <caption className="muted" style={{ textAlign: 'left', paddingBottom: 6 }}>All records, newest first</caption>
                      <thead><tr><th scope="col">Recorded</th><th scope="col">Items</th><th scope="col">Agreement</th><th scope="col">Record</th></tr></thead>
                      <tbody>{history.records.map((r) => <tr key={r.id}><td>{r.created_at}</td><td>{r.n}</td><td>{pct(r.agreement, 1)}</td><td><code className="fmono">{r.id.slice(0, 12)}</code></td></tr>)}</tbody>
                    </table>
                  </div>
                )}
              </>
            )}
      </section>
    </div>
  );
};
