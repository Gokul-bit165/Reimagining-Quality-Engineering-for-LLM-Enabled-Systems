import React, { useState } from 'react';
import { describeError } from '../api';
import { projectsApi } from '../lib/projects';
import { projectHref } from '../lib/route';
import { usePoll } from '../hooks/usePoll';
import { Banner, Field, Loading } from '../components/flow/ui';
import type { Project } from '../types/api';

const GITHUB_URL = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+(\.git)?\/?$/i;

export function validateRepoUrl(url: string): string | null {
  if (!url.trim()) return 'Enter the GitHub repository URL.';
  if (!GITHUB_URL.test(url.trim())) return 'Use a full URL such as https://github.com/your-org/your-rag-app';
  return null;
}

export function validateEndpoint(url: string): string | null {
  if (!url.trim()) return null;
  try {
    const u = new URL(url.trim());
    return u.protocol === 'http:' || u.protocol === 'https:' ? null : 'The endpoint must start with http:// or https://';
  } catch {
    return 'That does not look like a valid URL.';
  }
}

const STATE_TONE: Record<string, string> = { ready: 'ok', failed: 'bad', cloning: 'warn', analyzing: 'warn' };

export const ConnectPage: React.FC = () => {
  const [mode, setMode] = useState<'github' | 'zip'>('github');
  const [repo, setRepo] = useState('');
  const [branch, setBranch] = useState('');
  const [subdir, setSubdir] = useState('');
  const [endpoint, setEndpoint] = useState('');
  const [zip, setZip] = useState<File | null>(null);
  const [authorized, setAuthorized] = useState(false);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const projects = usePoll<Project[]>(() => projectsApi.list(), () => false, []);

  const repoError = mode === 'github' ? validateRepoUrl(repo) : zip ? null : 'Choose a .zip of your project.';
  const endpointError = validateEndpoint(endpoint);
  const authError = authorized ? null : 'You must confirm you are allowed to test this app.';
  const invalid = Boolean(repoError || endpointError || authError);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    setSubmitError(null);
    if (invalid) {
      const first = repoError ? (mode === 'github' ? 'repo' : 'zip') : endpointError ? 'endpoint' : null;
      (first ? document.getElementById(first) : document.querySelector<HTMLElement>('[data-testid="authorized"]'))?.focus();
      return;
    }
    setBusy(true);
    try {
      const res = mode === 'zip' && zip
        ? await projectsApi.upload(zip, authorized)
        : await projectsApi.create({
          repo_url: repo.trim(),
          authorized,
          ...(branch.trim() ? { branch: branch.trim() } : {}),
          ...(subdir.trim() ? { subdir: subdir.trim() } : {}),
          ...(endpoint.trim() ? { endpoint_url: endpoint.trim() } : {}),
        });
      window.location.hash = projectHref(res.id, 'understand');
    } catch (err) {
      setSubmitError(describeError(err, 'project analysis'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    if (!window.confirm('Delete this project and its evaluations?')) return;
    try { await projectsApi.remove(id); } catch (err) { setSubmitError(describeError(err, 'deleting projects')); }
    projects.reload();
  };

  return (
    <div className="page">
      <h1 className="page__title">Connect your RAG app</h1>
      <p className="page__lede">
        Point us at the code of a retrieval-augmented app. We read it, show you what risks it carries, run questions through it,
        and give a release recommendation with the evidence. Six short steps, about ten minutes for a first run.
      </p>

      <form className="panel stack" onSubmit={submit} noValidate aria-label="Connect a project">
        <div className="frow" role="group" aria-label="Source">
          <button type="button" className={`fbtn fbtn--sm ${mode === 'github' ? '' : 'fbtn--ghost'}`} aria-pressed={mode === 'github'} onClick={() => setMode('github')}>GitHub URL</button>
          <button type="button" className={`fbtn fbtn--sm ${mode === 'zip' ? '' : 'fbtn--ghost'}`} aria-pressed={mode === 'zip'} onClick={() => setMode('zip')}>Upload a .zip</button>
        </div>

        {mode === 'github' ? (
          <>
            <Field label="GitHub repository URL" htmlFor="repo" error={touched ? repoError : null}
              hint="Public repositories work out of the box. We only read the code; nothing is pushed."
              tip="The repository that contains your RAG application code.">
              <input id="repo" className="input" type="url" inputMode="url" autoComplete="off" placeholder="https://github.com/your-org/your-rag-app"
                value={repo} onChange={(e) => setRepo(e.target.value)} aria-invalid={touched && Boolean(repoError)} aria-describedby="repo-hint" />
            </Field>
            <div className="grid2">
              <Field label="Branch (optional)" htmlFor="branch" hint="Leave empty for the default branch.">
                <input id="branch" className="input" value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="main" autoComplete="off" />
              </Field>
              <Field label="Sub-folder (optional)" htmlFor="subdir" hint="Only needed for monorepos.">
                <input id="subdir" className="input" value={subdir} onChange={(e) => setSubdir(e.target.value)} placeholder="services/rag" autoComplete="off" />
              </Field>
            </div>
          </>
        ) : (
          <Field label="Project archive (.zip)" htmlFor="zip" error={touched ? repoError : null}
            hint="Zip the project folder. Do not include .env files or real secrets.">
            <input id="zip" className="input" type="file" accept=".zip,application/zip" onChange={(e) => setZip(e.target.files?.[0] ?? null)} />
          </Field>
        )}

        <Field label="Deployed endpoint URL (optional)" htmlFor="endpoint" error={touched ? endpointError : null}
          tip="If your app is already running somewhere, we send questions to it and score its real answers. Without it we can only analyse the code."
          hint="Adding one upgrades the run from 'code analysed only' to 'answers measured'.">
          <input id="endpoint" className="input" type="url" inputMode="url" autoComplete="off" placeholder="https://staging.example.com/ask"
            value={endpoint} onChange={(e) => setEndpoint(e.target.value)} aria-invalid={touched && Boolean(endpointError)} aria-describedby="endpoint-hint" />
        </Field>

        <div className="stack" style={{ gap: 8 }}>
          <label className="fcheck">
            <input type="checkbox" checked={authorized} onChange={(e) => setAuthorized(e.target.checked)} aria-describedby="auth-help" data-testid="authorized" />
            <span><strong>I own this app or am allowed to test it.</strong> I will use synthetic or non-sensitive data only.</span>
          </label>
          <span id="auth-help" className="field__hint">
            Only test applications you own or have written permission to test. Do not upload real customer data, credentials, or personal information.
          </span>
          {touched && authError && <span className="field__error" role="alert">{authError}</span>}
        </div>

        {submitError && <Banner tone="bad" role="alert">{submitError}</Banner>}
        <div className="frow">
          <button type="submit" className="fbtn" disabled={busy} data-testid="analyze">
            {busy ? <><span className="spinner" aria-hidden="true" /> Connecting…</> : <>Analyse project <span className="material-symbols-outlined" aria-hidden="true">arrow_forward</span></>}
          </button>
        </div>
      </form>

      <h2 className="h2" style={{ marginTop: 40 }}>Your projects</h2>
      {projects.loading && <Loading label="Loading projects…" />}
      {!projects.loading && Boolean(projects.error) && (
        <Banner tone="warn" role="status">Could not load existing projects: {describeError(projects.error, 'the project list')}</Banner>
      )}
      {!projects.loading && !projects.error && (projects.data?.length ?? 0) === 0 && (
        <div className="fempty">No projects yet. Connect your first RAG app above.</div>
      )}
      {(projects.data?.length ?? 0) > 0 && (
        <ul className="items" aria-label="Projects">
          {projects.data!.map((p) => (
            <li key={p.id} className="item">
              <div className="frow frow--between" style={{ padding: '10px 14px' }}>
                <a href={projectHref(p.id, p.analysis ? 'understand' : 'understand')} style={{ color: 'var(--c-accent-ink)', fontWeight: 600, overflowWrap: 'anywhere' }}>
                  {p.repo_url.replace(/^https:\/\/github\.com\//, '')}
                </a>
                <span className="frow">
                  <span className="badge" data-tone={STATE_TONE[p.state] ?? ''}>{p.state}</span>
                  <button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={() => void remove(p.id)} aria-label={`Delete ${p.repo_url}`}>Delete</button>
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
