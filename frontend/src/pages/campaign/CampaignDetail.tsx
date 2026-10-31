import React, { useState } from 'react';
import { describeError } from '../../api';
import { campaignsApi, isCampaignActive } from '../../lib/campaign';
import { campaignHref } from '../../lib/route';
import { usePoll } from '../../hooks/usePoll';
import { Banner, Loading } from '../../components/flow/ui';
import { ReportActions } from '../../components/flow/ReportActions';
import { StageTracker } from './StageTracker';
import { PlanView } from './PlanView';
import { TargetResults } from './TargetResults';
import { Comparison } from './Comparison';
import { ReviewPanel } from './ReviewPanel';
import { AuditTrail } from './AuditTrail';
import type { Campaign } from '../../types/campaign';

type TabKey = 'progress' | 'plan' | 'results' | 'compare' | 'review' | 'audit';
const TABS: { key: TabKey; label: string }[] = [
  { key: 'progress', label: 'Progress' }, { key: 'plan', label: 'Test plan' }, { key: 'results', label: 'Results' },
  { key: 'compare', label: 'Comparison' }, { key: 'review', label: 'Review' }, { key: 'audit', label: 'Audit trail' },
];

function firstTab(c: Campaign): TabKey {
  if (c.state === 'done') return c.targets.length > 1 ? 'compare' : 'results';
  return 'progress';
}

const Header: React.FC<{ c: Campaign }> = ({ c }) => (
  <div className="stack" style={{ gap: 4 }}>
    <h2 className="h2" style={{ margin: 0 }} data-testid="campaign-title">{c.name}</h2>
    <p className="muted" style={{ margin: 0 }}>
      {c.targets.length} target{c.targets.length === 1 ? '' : 's'} ({c.targets.map((t) => t.label).join(', ')}) · {c.params.repeats} repeat{c.params.repeats === 1 ? '' : 's'} · up to {c.params.max_cases} cases · call budget {c.params.max_calls.toLocaleString()}
      {c.params.use_example_policy ? ' · EXAMPLE policy' : ''}{c.params.plan_imported ? ' · imported plan' : ''}
    </p>
  </div>
);

export const CampaignDetail: React.FC<{ projectId: string; campaignId: string }> = ({ projectId, campaignId }) => {
  const live = usePoll<Campaign>(() => campaignsApi.get(campaignId), (c) => isCampaignActive(c.state), [campaignId], 1500);
  const [tab, setTab] = useState<TabKey | null>(null);
  const c = live.data;

  if (live.loading && !c) return <Loading label="Loading the campaign…" />;
  if (!c) {
    return (
      <div className="stack">
        <Banner tone="bad" role="alert">Could not load this campaign. {describeError(live.error, 'this campaign')}</Banner>
        <div className="frow"><button type="button" className="fbtn fbtn--ghost" onClick={live.reload}>Retry</button><a className="fbtn fbtn--ghost" href={campaignHref(projectId)}>Back to campaigns</a></div>
      </div>
    );
  }
  if (c.project_id !== projectId) {
    return <Banner tone="warn" role="alert">This campaign belongs to another project. <a href={campaignHref(c.project_id, c.id)}>Open it there</a>.</Banner>;
  }
  const active = tab ?? firstTab(c);
  const finished = c.state === 'done';

  return (
    <div className="stack" data-testid="campaign-detail">
      <div className="frow"><a className="fbtn fbtn--ghost fbtn--sm" href={campaignHref(projectId)}><span className="material-symbols-outlined" aria-hidden="true">arrow_back</span>All campaigns</a></div>
      <Header c={c} />
      {live.error != null && <Banner tone="warn" role="status">Could not refresh: {describeError(live.error, 'this campaign')}. Showing the last data received.</Banner>}
      <div className="tabs" role="tablist" aria-label="Campaign sections">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" id={`ctab-${t.key}`} aria-selected={active === t.key} aria-controls="ctab-panel" onClick={() => setTab(t.key)} data-testid={`ctab-${t.key}`}>{t.label}</button>
        ))}
      </div>
      <div id="ctab-panel" role="tabpanel" aria-labelledby={`ctab-${active}`} className="stack">
        {active === 'progress' && <StageTracker campaign={c} onChanged={live.reload} />}
        {active === 'plan' && <PlanView campaign={c} />}
        {active === 'results' && <TargetResults campaign={c} />}
        {active === 'compare' && <Comparison campaign={c} />}
        {active === 'review' && <ReviewPanel campaign={c} onChanged={live.reload} />}
        {active === 'audit' && <AuditTrail campaign={c} />}
        <ReportActions owner={{ kind: 'campaign', id: c.id }}
          disabledReason={finished ? null : 'The report needs a finished campaign. Until then the server will refuse it.'} />
      </div>
    </div>
  );
};
