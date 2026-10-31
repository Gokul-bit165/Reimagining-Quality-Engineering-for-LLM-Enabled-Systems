import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  applyNodeChanges,
  type Edge,
  type Node,
  type NodeChange,
  type NodeProps,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { clearLayout, loadLayout, saveLayout, type NodePositions } from '../../lib/layoutStorage';

export type StageTone = 'ok' | 'bad' | 'warn' | 'idle' | 'run';

export interface StageSpec {
  id: string;
  number: string;
  title: string;
  icon: string;
  status: string;
  tone: StageTone;
  desc: string;
  meta: string;
}

interface StageData extends Record<string, unknown> {
  stage: StageSpec;
  isSelected: boolean;
}

type StageNode = Node<StageData, 'stage'>;

const NODE_GAP_X = 290;
const NODE_GAP_Y = 190;
const NODES_PER_ROW = 3;

const StageCard: React.FC<NodeProps<StageNode>> = ({ data }) => {
  const { stage, isSelected } = data;
  return (
    <div
      className={`flow-stage${isSelected ? ' is-selected' : ''}`}
      data-tone={stage.tone}
      aria-label={`${stage.number} ${stage.title}, ${stage.status}. ${stage.desc}`}
    >
      <Handle type="target" position={Position.Left} className="flow-handle" isConnectable={false} />
      <div className="flow-stage__head">
        <span className="flow-stage__num">{stage.number}</span>
        <span className="flow-stage__status">{stage.status}</span>
      </div>
      <div className="flow-stage__title">
        <span className="material-symbols-outlined" aria-hidden="true">{stage.icon}</span>
        <span>{stage.title}</span>
      </div>
      <p className="flow-stage__desc">{stage.desc}</p>
      <div className="flow-stage__foot">
        <span className="flow-stage__meta">{stage.meta}</span>
        <span className="flow-stage__cta">{isSelected ? 'Inspecting' : 'Inspect'}</span>
      </div>
      <Handle type="source" position={Position.Right} className="flow-handle" isConnectable={false} />
    </div>
  );
};

const nodeTypes = { stage: StageCard };

export function defaultPositions(stages: StageSpec[]): NodePositions {
  const out: NodePositions = {};
  stages.forEach((s, i) => {
    out[s.id] = { x: (i % NODES_PER_ROW) * NODE_GAP_X, y: Math.floor(i / NODES_PER_ROW) * NODE_GAP_Y };
  });
  return out;
}

function buildNodes(stages: StageSpec[], positions: NodePositions, selectedId: string): StageNode[] {
  const defaults = defaultPositions(stages);
  return stages.map((stage) => ({
    id: stage.id,
    type: 'stage' as const,
    position: positions[stage.id] ?? defaults[stage.id],
    data: { stage, isSelected: stage.id === selectedId },
    ariaLabel: `${stage.title}. Use arrow keys to move this node.`,
    selected: stage.id === selectedId,
  }));
}

interface FlowCanvasProps {
  /** localStorage key: one saved layout per project or report. */
  storageKey: string;
  stages: StageSpec[];
  selectedId: string;
  onSelect: (id: string) => void;
  caption?: string;
}

export const FlowCanvas: React.FC<FlowCanvasProps> = ({ storageKey, stages, selectedId, onSelect, caption }) => {
  const [nodes, setNodes] = useState<StageNode[]>(() => buildNodes(stages, loadLayout(storageKey), selectedId));
  const dirty = useRef(false);
  const rf = useRef<ReactFlowInstance<StageNode> | null>(null);

  // Re-derive node content/selection when stage data changes; keep the user's positions.
  useEffect(() => {
    setNodes((prev) => {
      const pos: NodePositions = {};
      prev.forEach((n) => { pos[n.id] = n.position; });
      return buildNodes(stages, { ...loadLayout(storageKey), ...pos }, selectedId);
    });
  }, [stages, selectedId, storageKey]);

  // A different project/report loads its own saved layout.
  useEffect(() => {
    setNodes(buildNodes(stages, loadLayout(storageKey), selectedId));
    dirty.current = false;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  const edges = useMemo<Edge[]>(() => stages.slice(1).map((s, i) => {
    const source = stages[i].id;
    const active = selectedId === source || selectedId === s.id;
    return {
      id: `e-${source}-${s.id}`,
      source,
      target: s.id,
      type: 'smoothstep',
      animated: active,
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18, color: active ? '#4f46e5' : '#64748b' },
      style: { stroke: active ? '#4f46e5' : '#64748b', strokeWidth: 2 },
    };
  }), [stages, selectedId]);

  const onNodesChange = useCallback((changes: NodeChange<StageNode>[]) => {
    if (changes.some((c) => c.type === 'position' && c.dragging !== true)) dirty.current = true;
    setNodes((prev) => applyNodeChanges(changes, prev));
  }, []);

  useEffect(() => {
    if (!dirty.current) return;
    dirty.current = false;
    const pos: NodePositions = {};
    nodes.forEach((n) => { pos[n.id] = { x: Math.round(n.position.x), y: Math.round(n.position.y) }; });
    saveLayout(storageKey, pos);
  }, [nodes, storageKey]);

  const resetLayout = useCallback(() => {
    clearLayout(storageKey);
    dirty.current = false;
    setNodes(buildNodes(stages, {}, selectedId));
    window.requestAnimationFrame(() => { void rf.current?.fitView({ padding: 0.15, duration: 0 }); });
  }, [stages, selectedId, storageKey]);

  return (
    <section className="flow-wrap" aria-label="Pipeline workflow canvas">
      <div className="flow-toolbar">
        <span className="flow-toolbar__caption">
          {caption ?? `${stages.length} stages, ${Math.max(stages.length - 1, 0)} links`}
        </span>
        <span className="flow-toolbar__hint">
          Drag cards to rearrange. Scroll or pinch to zoom. Drag the background to pan.
          Focus a card, then use arrow keys to move it.
        </span>
        <button type="button" className="fbtn fbtn--ghost fbtn--sm" onClick={resetLayout} data-testid="reset-layout">
          <span className="material-symbols-outlined" aria-hidden="true">restart_alt</span>
          Reset layout
        </button>
      </div>
      <div className="flow-surface" data-testid="flow-surface">
        <ReactFlow<StageNode, Edge>
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onInit={(inst) => { rf.current = inst; }}
          onNodeClick={(_, node) => onSelect(node.id)}
          onSelectionChange={({ nodes: sel }) => { if (sel.length === 1 && sel[0].id !== selectedId) onSelect(sel[0].id); }}
          nodesDraggable
          nodesConnectable={false}
          nodesFocusable
          edgesFocusable={false}
          elementsSelectable
          panOnDrag
          zoomOnScroll
          zoomOnPinch
          minZoom={0.3}
          maxZoom={1.8}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          disableKeyboardA11y={false}
          ariaLabelConfig={{ 'node.a11yDescription.default': 'Press Enter or Space to select this stage. Use arrow keys to move it.' }}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} color="#cbd5e1" />
          <Controls showInteractive={false} position="bottom-left" />
        </ReactFlow>
      </div>
    </section>
  );
};
