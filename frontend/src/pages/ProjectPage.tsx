import React from 'react';
import { describeError } from '../api';
import { evaluationsApi, projectsApi } from '../lib/projects';
import { projectHref, routeTitle, STEP_KEYS, TOOL_KEYS, type AreaKey, type StepKey, type ToolKey } from '../lib/route';
import { endpointHost, isLoopbackEndpoint } from '../lib/provenance';
import { usePoll } from '../hooks/usePoll';
import { Banner, Loading } from '../components/flow/ui';
import { UnderstandStep } from './project/UnderstandStep';
import { InputsStep } from './project/InputsStep';
import { RunStep } from './project/RunStep';
import { ResultsStep } from './project/ResultsStep';
import { OperateStep } from './project/OperateStep';
import { CampaignPage } from './campaign/CampaignPage';
import { JudgePage } from './project/JudgePanel';
import type { Evaluation, EvaluationSummary, Project } from '../types/api';

const isActive = (e: { state: string }) => e.state === 'queued' || e.state === 'running';

function describeEval(e: EvaluationSummary): string {
  const when = e.created ? new Date(e.created * 1000).toLocaleString() : e.id;
  return `${when} · ${e.state}${e.verdict ? ` · ${e.verdict.replace('_', ' ')}` : ''}`;
}

const STEP_LABEL: Record<StepKey, string> = {
  understand: 'Understand', inputs: 'Provide inputs', run: 'Run', results: 'Results', operate: 'Operate',
};
const TOOL_LABEL: Record<ToolKey, string> = { campaign: 'Test campaign', judge: 'Judge & calibration' };
const TOOL_ICON: Record<ToolKey, string> = { campaign: 'compare_arrows', judge: 'balance' };
const STEP_BLURB: Record<AreaKey, string> = {
  understand: 'What your code does and where the risks are.',
  inputs: 'Give us documents, questions and an endpoint. All optional.',
  run: 'Ask the questions and score the answers.',
  results: 'Scores with confidence intervals, failures, and a release recommendation.',
  operate: 'Keep failures from returning and plan monitoring.',
  campaign: 'Plan tests from your risks, run them against several targets, and compare the results fairly.',
  judge: 'Check the semantic judge is independent and how closely it agrees with your own labels.',
};

const Provenance: React.FC<{ endpoint: string | null | undefined }> = ({ endpoint }) => {
  const host = endpointHost(endpoint);
  return (
    <p className="frow" style={{ margin: '0 0 8px' }} data-testid="provenance">
      {host ? (
        <>
          <span className="muted">Tested endpoint:</span> <code className="fmono">{host}</code>
          {isLoopbackEndpoint(endpoint) && (
            <span className="badge" data-tone="warn" tabIndex={0} data-testid="local-badge" title="Results describe whatever is listening there"
              aria-label="Local endpoint. Results describe whatever is listening there">Local endpoint</span>
          )}
        </>
      ) : <span className="muted">No endpoint set: only the code is analysed, no answers are measured.</span>}
    </p>
  );
};

interface Props { projectId: string; step: AreaKey; evalId: string | null; campaignId?: string | null }

export const ProjectPage: React.FC<Props> = ({ projectId, step, evalId, campaignId = null }) => {
  const proj = usePoll<Project>(
    () => projectsApi.get(projectId),
    (p) => p.state === 'cloning' || p.state === 'analyzing',
    [projectId],
  );
  // Every evaluation of this project, newest first. Lets results/run resume after a reload.
  const list = usePoll<EvaluationSummary[]>(
    () => evaluationsApi.forProject(projectId),
    (l) => l.some(isActive),
    [projectId, evalId],
    2000,
  );
  const evals = list.data ?? [];
  const inFlight = evals.find(isActive);
  const effectiveId = evalId ?? (step === 'run' ? inFlight?.id ?? null : evals[0]?.id ?? null);
  const ev = usePoll<Evaluation | null>(
    () => (effectiveId ? evaluationsApi.get(effectiveId) : Promise.resolve(null)),
    (e) => e !== null && isActive(e),
    [effectiveId],
    1200,
  );

  const repoUrl = proj.data?.repo_url ?? null;
  React.useEffect(() => { document.title = routeTitle({ name: 'project', projectId, step, evalId, campaignId }, repoUrl); }, [projectId, step, evalId, campaignId, repoUrl]);

  if (proj.loading && !proj.data) return <div className="page"><Loading label="Loading project…" /></div>;
  if (!proj.data) {
    return (
      <div className="page stack">
        <Banner tone="bad" role="alert">Could not load this project. {describeError(proj.error, 'this project')}</Banner>
        <div className="frow"><button type="button" className="fbtn fbtn--ghost" onClick={proj.reload}>Retry</button><a className="fbtn fbtn--ghost" href="#connect">Back to connect</a></div>
      </div>
    );
  }
  const project = proj.data;
  const ready = project.state === 'ready';
  const evaluation = ev.data;
  const done = evaluation?.state === 'done';
  const resolving = list.loading || (Boolean(effectiveId) && ev.loading && !ev.data);

  const enabled: Record<StepKey, boolean> = {
    understand: true, inputs: ready, run: ready, results: evals.length > 0, operate: evals.some((e) => e.state === 'done'),
  };
  const completed: Record<StepKey, boolean> = {
    understand: ready, inputs: Boolean(project.inputs && Object.keys(project.inputs).length), run: evals.length > 0,
    results: Boolean(done), operate: false,
  };

  return (
    <div className="page">
      <div className="frow frow--between" style={{ marginBottom: 8 }}>
        <h1 className="page__title" style={{ overflowWrap: 'anywhere' }}>{project.repo_url.replace(/^https:\/\/github\.com\//, '')}</h1>
        <span className="badge" data-tone={project.state === 'ready' ? 'ok' : project.state === 'failed' ? 'bad' : 'warn'}>{project.state}</span>
      </div>
      <Provenance endpoint={project.inputs.endpoint_url || project.endpoint_url} />
      <p className="page__lede">{STEP_BLURB[step]}</p>

      <nav aria-label="Progress">
        <ol className="stepper">
          <li className="stepper__item">
            <a className="stepper__btn" href="#connect" data-done="true" style={{ textDecoration: 'none' }}>
              <span className="stepper__n" aria-hidden="true">1</span>Connect
            </a>
          </li>
          {STEP_KEYS.map((k, i) => (
            <li className="stepper__item" key={k}>
              <button type="button" className="stepper__btn" disabled={!enabled[k]} data-done={completed[k]}
                aria-current={step === k ? 'step' : undefined} data-testid={`step-${k}`}
                onClick={() => { window.location.hash = projectHref(projectId, k, k === 'run' ? evalId : effectiveId); }}>
                <span className="stepper__n" aria-hidden="true">{completed[k] && step !== k ? '✓' : i + 2}</span>{STEP_LABEL[k]}
              </button>
            </li>
          ))}
        </ol>
      </nav>

      <nav aria-label="Work areas" className="toolbar">
        <span className="toolbar__label">Also</span>
        {TOOL_KEYS.map((k) => (
          <a key={k} className="toolbar__link" href={projectHref(projectId, k)} aria-current={step === k ? 'page' : undefined} data-testid={`tool-${k}`}>
            <span className="material-symbols-outlined" aria-hidden="true">{TOOL_ICON[k]}</span>{TOOL_LABEL[k]}
          </a>
        ))}
      </nav>

      {Boolean(ev.error) && effectiveId && step !== 'run' && <div style={{ marginBottom: 16 }}><Banner tone="warn" role="status">Could not load evaluation {effectiveId}: {describeError(ev.error, 'this evaluation')}</Banner></div>}

      {(step === 'results' || step === 'operate') && evals.length > 1 && (
        <div className="field" style={{ marginBottom: 16, maxWidth: 420 }}>
          <label className="field__label" htmlFor="eval-pick">Evaluation</label>
          <select id="eval-pick" className="select" value={effectiveId ?? ''} data-testid="eval-picker"
            onChange={(e) => { window.location.hash = projectHref(projectId, step, e.target.value); }}>
            {evals.map((e, i) => <option key={e.id} value={e.id}>{i === 0 ? 'Latest: ' : ''}{describeEval(e)}</option>)}
          </select>
        </div>
      )}

      {step === 'campaign' && <CampaignPage project={project} campaignId={campaignId} />}
      {step === 'judge' && <JudgePage />}
      {step === 'understand' && <UnderstandStep project={project} />}
      {step === 'inputs' && (ready ? <InputsStep key={project.id} project={project} /> : <Banner tone="info">Inputs unlock when analysis finishes.</Banner>)}
      {step === 'run' && !effectiveId && evals.length > 0 && (
        <div style={{ marginBottom: 16 }}><Banner tone="info" role="status">
          <span>This project already has {evals.length} evaluation{evals.length === 1 ? '' : 's'}. <a href={projectHref(projectId, 'results')}>View the latest results</a>, or start a new run below.</span>
        </Banner></div>
      )}
      {step === 'run' && (ready ? <RunStep project={project} evaluation={evaluation} evalError={ev.error} onChanged={ev.reload} /> : <Banner tone="info">Runs unlock when analysis finishes.</Banner>)}
      {step === 'results' && (evaluation ? <ResultsStep key={evaluation.id} project={project} evaluation={evaluation} onReload={ev.reload} />
        : resolving ? <Loading label="Loading results…" /> : <div className="fempty">This project has no evaluations yet. <a href={projectHref(projectId, 'run')}>Start one</a>.</div>)}
      {step === 'operate' && (evaluation && done ? <OperateStep key={evaluation.id} project={project} evaluation={evaluation} />
        : resolving ? <Loading label="Loading…" /> : <div className="fempty">Operate unlocks once an evaluation has finished.</div>)}
    </div>
  );
};
