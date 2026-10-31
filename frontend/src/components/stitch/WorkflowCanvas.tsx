import React, { useMemo } from 'react';
import type { Report } from '../../types/api';
import { FlowCanvas, type StageSpec } from './FlowCanvas';

interface WorkflowCanvasProps {
  report: Report;
  /** Run id: layouts persist per report. */
  runId?: string;
  selectedStage: number;
  onSelectStage: (stage: number) => void;
}

/** Demo-report pipeline. Draggable/pannable/zoomable via the shared FlowCanvas. */
export const WorkflowCanvas: React.FC<WorkflowCanvasProps> = ({ report, runId, selectedStage, onSelectStage }) => {
  const stages = useMemo<StageSpec[]>(() => {
    const d = report.decision.decision;
    const tone = d === 'REJECT' ? 'bad' : d === 'RELEASE' ? 'ok' : 'warn';
    return [
      { id: '1', number: 'STAGE 01', title: 'Risk Register', icon: 'inventory_2', status: 'COMPLETED', tone: 'ok',
        desc: `${report.risks.length} risks mapped from OWASP ${report.scenario.taxonomy_id}`,
        meta: `${report.risks.reduce((a, r) => a + r.planned_tests, 0)} planned tests` },
      { id: '2', number: 'STAGE 02', title: 'Test Generation', icon: 'hub', status: 'COMPLETED', tone: 'ok',
        desc: `${report.generation.drafted} drafted; ${report.generation.rejected_drafts} rejected; ${report.generation.tests.length} validated`,
        meta: `${report.generation.tests.length} tests ready` },
      { id: '3', number: 'STAGE 03', title: 'Sandbox Execution', icon: 'terminal', status: 'COMPLETED', tone: 'ok',
        desc: `${report.scenario.app} (${report.scenario.variant}), ${report.execution.runs} runs`,
        meta: `${report.execution.consistency.identical_across_repeats}/${report.execution.consistency.cases} consistent` },
      { id: '4', number: 'STAGE 04', title: 'Grounding & Attacks', icon: 'security', status: d === 'REJECT' ? 'BREACHED' : 'EVALUATED',
        tone: d === 'REJECT' ? 'bad' : 'ok', desc: `${report.attacks.rows.length} attack pairs on ${report.scenario.app}`,
        meta: `${report.metrics.length} metrics evaluated` },
      { id: '5', number: 'STAGE 05', title: 'Decision & Sign-off', icon: 'rule', status: d, tone,
        desc: `Ledger ${report.ledger.verified ? 'verified' : 'unverified'}, ${report.decision.evidence_ids.length} evidence records`,
        meta: report.human_signoff.length ? `${report.human_signoff.length} signoff(s)` : 'Awaiting signoff' },
    ];
  }, [report]);

  return (
    <FlowCanvas
      storageKey={`report:${runId ?? report.id}`}
      stages={stages}
      selectedId={String(selectedStage)}
      onSelect={(id) => onSelectStage(Number(id))}
      caption="Linear verification pipeline"
    />
  );
};
