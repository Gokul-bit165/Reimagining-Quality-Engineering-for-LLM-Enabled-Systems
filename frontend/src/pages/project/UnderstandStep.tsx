import React from 'react';
import type { DetectedItem, Project } from '../../types/api';
import { EXECUTION_MODE_INFO, labelOf } from '../../lib/explain';
import { projectHref } from '../../lib/route';
import { Banner, Loading, Tip } from '../../components/flow/ui';
import { ExecutionPanel } from './ExecutionPanel';

const Chips: React.FC<{ items: DetectedItem[] }> = ({ items }) =>
  items.length === 0 ? <span className="muted">Not detected</span> : (
    <span className="chips">{items.map((it, i) => <span key={i} className="fchip">{labelOf(it)}</span>)}</span>
  );

export const UnderstandStep: React.FC<{ project: Project }> = ({ project }) => {
  if (project.state === 'cloning' || project.state === 'analyzing') {
    return (
      <div className="panel stack" aria-live="polite">
        <Loading label={project.state === 'cloning' ? 'Fetching your code from GitHub…' : 'Reading the code to find the retriever, prompts and risks…'} />
        <p className="muted">This usually takes under a minute. You can leave this page; analysis continues on the server.</p>
      </div>
    );
  }
  if (project.state === 'failed' || !project.analysis) {
    return (
      <div className="stack">
        <Banner tone="bad" role="alert">
          <span>
            <strong>Analysis failed.</strong> {project.error ?? 'The backend did not return an analysis for this project.'}
            {' '}Check the URL is public (or upload a zip) and try again.
          </span>
        </Banner>
        <div><a className="fbtn fbtn--ghost" href="#connect">Back to connect</a></div>
      </div>
    );
  }
  const a = project.analysis;
  const mode = EXECUTION_MODE_INFO[a.execution_mode];
  return (
    <div className="stack">
      <Banner tone={mode.tone === 'warn' ? 'warn' : 'ok'}>
        <span className="material-symbols-outlined" aria-hidden="true">{mode.tone === 'warn' ? 'visibility' : 'play_circle'}</span>
        <span data-testid="execution-mode">
          <strong>Execution mode: {mode.label} ({a.execution_mode}).</strong> {mode.text}
        </span>
      </Banner>

      {(a.summary || (a.next_steps?.length ?? 0) > 0) && (
        <section className="panel panel--flat" aria-labelledby="plain">
          <h2 className="h2" id="plain">In plain words</h2>
          {a.summary && <p style={{ margin: '0 0 8px', fontSize: 14, lineHeight: 1.55 }} data-testid="analysis-summary">{a.summary}</p>}
          {(a.next_steps?.length ?? 0) > 0 && (
            <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13, lineHeight: 1.6 }}>{a.next_steps!.map((n, i) => <li key={i}>{n}</li>)}</ol>
          )}
        </section>
      )}

      <div className="grid2" style={{ alignItems: 'start' }}>
        <section className="panel" aria-labelledby="what">
          <h2 className="h2" id="what">What we found</h2>
          <dl className="ffacts">
            <dt>Framework</dt><dd>{a.framework ?? 'Not detected'}</dd>
            <dt>Language</dt><dd>{a.language ?? 'Not detected'}</dd>
            <dt>Retriever <Tip text="The component that looks up passages to feed the model." /></dt><dd>{a.retriever ? labelOf(a.retriever) : 'Not detected'}</dd>
            <dt>Vector store</dt><dd>{a.vector_store ? labelOf(a.vector_store) : 'Not detected'}</dd>
            <dt>Chunking <Tip text="How documents are split into passages before indexing." /></dt><dd>{a.chunking ? labelOf(a.chunking) : 'Not detected'}</dd>
            <dt>Model providers</dt><dd><Chips items={a.llm_providers} /></dd>
            <dt>Entry points</dt><dd><Chips items={a.entrypoints} /></dd>
            <dt>Document sources</dt><dd><Chips items={a.doc_sources} /></dd>
            <dt>Env variables</dt><dd><Chips items={a.env_vars} /></dd>
          </dl>
        </section>

        <div className="stack">
          <section className="panel" aria-labelledby="risks">
            <h2 className="h2" id="risks">Risk flags ({a.risk_flags.length})</h2>
            {a.risk_flags.length === 0 ? (
              <p className="muted">No risk patterns were flagged by static analysis. That is not proof the app is safe; the evaluation will test it.</p>
            ) : a.risk_flags.map((r) => (
              <div className="flag" key={`${r.id}-${r.evidence_file}-${r.line}`}>
                <span className="material-symbols-outlined flag__ico" aria-hidden="true">warning</span>
                <div>
                  <div className="flag__title">{r.title}</div>
                  <div className="flag__ev">{r.evidence_file ? `${r.evidence_file}${r.line ? `:${r.line}` : ''}` : 'No file evidence recorded'}</div>
                </div>
              </div>
            ))}
          </section>
          <section className="panel" aria-labelledby="prompts">
            <h2 className="h2" id="prompts">Prompts found ({a.prompts.length})</h2>
            {a.prompts.length === 0 ? <span className="muted">Not detected</span> : a.prompts.map((p, i) => (
              <div key={i} style={{ marginBottom: 8 }}>
                <div className="flag__ev">{labelOf(p)}</div>
                {typeof p === 'object' && typeof p.snippet === 'string' && <pre className="quote fquote" style={{ margin: '4px 0 0', overflowX: 'auto' }}>{p.snippet}</pre>}
              </div>
            ))}
          </section>
        </div>
      </div>

      <ExecutionPanel project={project} />

      <div className="frow">
        <a className="fbtn" href={projectHref(project.id, 'inputs')} data-testid="to-inputs">
          Continue: provide inputs <span className="material-symbols-outlined" aria-hidden="true">arrow_forward</span>
        </a>
      </div>
    </div>
  );
};
