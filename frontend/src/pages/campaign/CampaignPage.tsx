import React from 'react';
import { describeError } from '../../api';
import { campaignsApi, stateTone, badgeTone, STATE_TEXT } from '../../lib/campaign';
import { campaignHref } from '../../lib/route';
import { usePoll } from '../../hooks/usePoll';
import { Banner, Loading } from '../../components/flow/ui';
import { CampaignForm } from './CampaignForm';
import { CampaignDetail } from './CampaignDetail';
import type { Project } from '../../types/api';
import type { CampaignSummary } from '../../types/campaign';

const NEW_ID = 'new';
const isActive = (c: CampaignSummary) => c.state === 'queued' || c.state === 'running' || c.state === 'cancelling';

const CampaignList: React.FC<{ project: Project }> = ({ project }) => {
  const list = usePoll<CampaignSummary[]>(() => campaignsApi.forProject(project.id), (l) => l.some(isActive), [project.id], 2000);
  const rows = list.data ?? [];
  return (
    <div className="stack">
      <section className="panel stack" aria-labelledby="cl-h">
        <div className="frow frow--between">
          <div>
            <h2 className="h2" id="cl-h" style={{ margin: 0 }}>Test campaigns</h2>
            <p className="muted" style={{ margin: '4px 0 0' }}>Run the same planned tests against several versions of your app, or against a bare model, and compare them fairly.</p>
          </div>
          <a className="fbtn" href={campaignHref(project.id, NEW_ID)} data-testid="new-campaign">
            <span className="material-symbols-outlined" aria-hidden="true">add</span>New campaign
          </a>
        </div>
        {list.loading && !list.data && <Loading label="Loading campaigns…" />}
        {list.error != null && <Banner tone="bad" role="alert">Could not load campaigns. {describeError(list.error, 'campaigns')} <button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={list.reload}>Retry</button></Banner>}
        {list.data && rows.length === 0 && <div className="fempty" data-testid="campaigns-empty">No campaigns for this project yet. Start one to compare two or more targets.</div>}
        {rows.length > 0 && (
          <ul className="items" data-testid="campaign-list">
            {rows.map((c) => {
              const pctDone = c.progress.total > 0 ? Math.round((c.progress.done / c.progress.total) * 100) : 0;
              return (
                <li key={c.id} className="item">
                  <a className="item__head" href={campaignHref(project.id, c.id)} style={{ textDecoration: 'none' }} data-testid={`campaign-${c.id}`}>
                    <span className="badge" data-tone={badgeTone(stateTone(c.state))} title={STATE_TEXT[c.state]}>{c.state.toUpperCase()}</span>
                    <span className="item__q"><strong>{c.name}</strong> <span className="muted">· {c.targets.join(' vs ')}</span></span>
                    {isActive(c) && <span className="muted">{pctDone}%</span>}
                    {c.better_target && <span className="fchip" title="Recommended by the paired comparison">better: {c.better_target}</span>}
                    <span className="material-symbols-outlined" aria-hidden="true">chevron_right</span>
                  </a>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
};

/** The 'Test campaign' area of a project: list, create form, or one campaign. */
export const CampaignPage: React.FC<{ project: Project; campaignId: string | null }> = ({ project, campaignId }) => {
  if (project.state !== 'ready') return <Banner tone="info">Campaigns unlock when analysis finishes.</Banner>;
  if (campaignId === NEW_ID) return <CampaignForm key={project.id} project={project} />;
  if (campaignId) return <CampaignDetail projectId={project.id} campaignId={campaignId} />;
  return <CampaignList project={project} />;
};
