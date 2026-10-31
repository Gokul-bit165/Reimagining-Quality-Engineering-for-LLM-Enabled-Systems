import React, { useState } from 'react';
import { describeError } from '../../api';
import { projectsApi } from '../../lib/projects';
import {
  MAX_EGRESS_HOSTS, RUNTIME_ACTIVE, RUNTIME_TEXT, parseEgressHosts, tailLog, validateAppPath, validateAppPort, validateEgressHosts,
} from '../../lib/campaign';
import { EXECUTION_MODE_INFO } from '../../lib/explain';
import { usePoll } from '../../hooks/usePoll';
import { Banner, Field, Loading, Tip } from '../../components/flow/ui';
import type { Project } from '../../types/api';

const LogViewer: React.FC<{ title: string; log: string; testId: string }> = ({ title, log, testId }) => {
  if (!log.trim()) return <p className="muted" style={{ margin: 0 }}>{title}: nothing logged yet.</p>;
  const { text, hidden } = tailLog(log);
  return (
    <details data-testid={testId}>
      <summary className="h3" style={{ cursor: 'pointer', margin: 0 }}>{title}</summary>
      {hidden > 0 && <p className="field__hint" style={{ margin: '6px 0 0' }}>Showing the last {text.split('\n').length} lines; {hidden} earlier line{hidden === 1 ? '' : 's'} hidden. The backend also truncates long logs.</p>}
      <pre className="logbox" tabIndex={0} aria-label={`${title}, scrollable`}>{text}</pre>
    </details>
  );
};

const RuntimeState: React.FC<{ project: Project }> = ({ project }) => {
  const rt = project.runtime;
  if (!rt || rt.state === 'idle') {
    return <p className="muted" style={{ margin: 0 }}>Nothing has been built or started yet. The container is built when you run an evaluation.</p>;
  }
  const info = RUNTIME_TEXT[rt.state] ?? { label: rt.state, tone: 'info' as const };
  const active = RUNTIME_ACTIVE.includes(rt.state);
  return (
    <div className="stack" style={{ gap: 12 }} aria-live="polite">
      <div className="frow">
        {active && <span className="spinner" aria-hidden="true" />}
        <span className="badge" data-tone={info.tone === 'info' ? undefined : info.tone} data-testid="runtime-state">{info.label.toUpperCase()}</span>
        {rt.kind && <span className="fchip">{rt.kind}</span>}
        <span className="muted">Egress: {rt.egress === 'none' ? 'none (the app cannot reach the internet)' : rt.egress}</span>
      </div>
      {rt.detail && <p style={{ margin: 0 }} data-testid="runtime-detail">{rt.detail}</p>}
      {rt.state === 'failed' && <Banner tone="bad" role="alert">The app did not start. The logs below show why. Fix the cause (often a missing environment variable or the wrong port) and run again.</Banner>}
      <LogViewer title="Build log" log={rt.build_log} testId="build-log" />
      <LogViewer title="Run log" log={rt.run_log} testId="run-log" />
      {rt.egress_log.length > 0 && (
        <details data-testid="egress-log">
          <summary className="h3" style={{ cursor: 'pointer', margin: 0 }}>Network attempts ({rt.egress_log.length})</summary>
          <p className="field__hint" style={{ margin: '6px 0 0' }}>Evidence of what the app tried to reach and whether the allowlist permitted it.</p>
          <pre className="logbox" tabIndex={0} aria-label="Network attempts, scrollable">{rt.egress_log.join('\n')}</pre>
        </details>
      )}
      <p className="field__hint" style={{ margin: 0 }}>Logs are scrubbed of secret values and truncated by the server.</p>
    </div>
  );
};

const Settings: React.FC<{ project: Project; onSaved: () => void }> = ({ project, onSaved }) => {
  const inputs = project.inputs ?? {};
  const [hosts, setHosts] = useState((inputs.egress_allowlist ?? []).join('\n'));
  const [path, setPath] = useState(inputs.app_path ?? '');
  const [port, setPort] = useState(inputs.app_port ? String(inputs.app_port) : '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const list = parseEgressHosts(hosts);
  const hostErrors = validateEgressHosts(list);
  const pathError = validateAppPath(path);
  const portError = validateAppPort(port);
  const invalid = hostErrors.length > 0 || Boolean(pathError) || Boolean(portError);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (invalid) return;
    setBusy(true); setError(null); setSaved(false);
    try {
      await projectsApi.saveInputs(project.id, {
        egress_allowlist: [...new Set(list)],
        app_path: path.trim() || null,
        app_port: port.trim() ? Number(port) : null,
      });
      setSaved(true); onSaved();
    } catch (err) { setError(describeError(err, 'saving execution settings')); }
    finally { setBusy(false); }
  };

  return (
    <form className="stack" onSubmit={save} noValidate data-testid="execution-settings">
      <Field label="Allowed outbound hosts" htmlFor="egress" tip="By default the sandboxed app has no internet. Listing a host lets it reach only that host."
        hint={`One per line: a DNS name such as api.openai.com, or *.example.com. No scheme, port, path or IP. Up to ${MAX_EGRESS_HOSTS}.`}
        error={hostErrors.length ? hostErrors[0] : null}>
        <textarea id="egress" className="textarea" value={hosts} onChange={(e) => { setHosts(e.target.value); setSaved(false); }} aria-invalid={hostErrors.length > 0}
          aria-describedby="egress-hint egress-warn" placeholder="api.openai.com" spellCheck={false} />
      </Field>
      <div id="egress-warn">
        <Banner tone="warn" role="status">
          <span data-testid="egress-warning"><strong>Allow only your model provider&apos;s own hosts.</strong> Anything you list can receive whatever the app sends, including your documents and test questions. Never list a host you do not control or trust, and prefer an exact name over a wildcard.</span>
        </Banner>
      </div>
      <div className="grid2">
        <Field label="Question path override" htmlFor="app-path" hint="HTTP path the questions are POSTed to. Leave blank to use the detected one." error={pathError}>
          <input id="app-path" className="input" value={path} onChange={(e) => { setPath(e.target.value); setSaved(false); }} placeholder="/ask" aria-invalid={Boolean(pathError)} autoComplete="off" spellCheck={false} />
        </Field>
        <Field label="App port override" htmlFor="app-port" hint="Container port the app listens on. Leave blank to use the detected one." error={portError}>
          <input id="app-port" className="input" inputMode="numeric" value={port} onChange={(e) => { setPort(e.target.value); setSaved(false); }} placeholder="8000" aria-invalid={Boolean(portError)} autoComplete="off" />
        </Field>
      </div>
      {error && <Banner tone="bad" role="alert">{error}</Banner>}
      {saved && <Banner tone="ok" role="status">Saved. These take effect the next time the app is built and started.</Banner>}
      <div><button type="submit" className="fbtn" disabled={busy || invalid} data-testid="save-execution">{busy ? 'Saving…' : 'Save execution settings'}</button></div>
    </form>
  );
};

/** Docker only: run state (polled while building/starting) and the sandbox settings. */
const DockerSection: React.FC<{ project: Project }> = ({ project: initial }) => {
  const live = usePoll<Project>(() => projectsApi.get(initial.id), (p) => RUNTIME_ACTIVE.includes(p.runtime?.state ?? ''), [initial.id], 2000);
  const project = live.data ?? initial;
  return (
    <>
      <RuntimeState project={project} />
      {live.error != null && <Banner tone="warn" role="status">Could not refresh the run state. {describeError(live.error, 'the project')}</Banner>}
      {live.loading && !live.data && <Loading label="Reading run state…" />}
      <Settings project={project} onSaved={live.reload} />
    </>
  );
};

/** Execution mode and why, the sandbox run state, and the settings that shape the sandbox. */
export const ExecutionPanel: React.FC<{ project: Project }> = ({ project }) => {
  const analysis = project.analysis;
  const mode = analysis?.execution_mode ?? 'static_only';
  const info = EXECUTION_MODE_INFO[mode];

  return (
    <section className="panel stack" aria-labelledby="exec-h" data-testid="execution-panel">
      <h2 className="h2" id="exec-h" style={{ margin: 0 }}>Execution <Tip text="How your app is run to get real answers, and what it is allowed to reach." /></h2>
      <dl className="ffacts">
        <dt>Mode</dt><dd data-testid="exec-mode"><strong>{info.label}</strong> ({mode}){analysis?.run_kind ? <> · run kind <code className="fmono">{analysis.run_kind}</code></> : null}</dd>
        <dt>Why</dt><dd data-testid="exec-reason">{analysis?.mode_reason || 'The analyser gave no reason.'}</dd>
      </dl>
      {mode === 'static_only' && (
        <Banner tone="warn" role="status">
          <span data-testid="static-only-note"><strong>Analysed, not run.</strong> {analysis?.mode_reason ? `Because: ${analysis.mode_reason}` : 'No way to run it was found.'} No real answers exist for this project, so nothing here is measured. Add a deployed endpoint URL in Inputs to get measured results.</span>
        </Banner>
      )}
      {mode === 'docker' && <DockerSection project={project} />}
      {mode === 'endpoint' && <p className="muted" style={{ margin: 0 }}>Your own endpoint is called directly, so nothing is built or sandboxed here. Network allowlists apply only to containers this tool builds.</p>}
    </section>
  );
};
