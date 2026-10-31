export interface XY { x: number; y: number }
export type NodePositions = Record<string, XY>;

const PREFIX = 'qe.canvas.layout.v1:';

function isXY(v: unknown): v is XY {
  return typeof v === 'object' && v !== null
    && Number.isFinite((v as XY).x) && Number.isFinite((v as XY).y);
}

/** Positions are stored per project/report key. Corrupt data is ignored. */
export function loadLayout(key: string): NodePositions {
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const out: NodePositions = {};
    for (const [id, pos] of Object.entries(parsed)) if (isXY(pos)) out[id] = { x: pos.x, y: pos.y };
    return out;
  } catch {
    return {};
  }
}

export function saveLayout(key: string, positions: NodePositions): void {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(positions));
  } catch { /* storage full or blocked: layout simply won't persist */ }
}

export function clearLayout(key: string): void {
  try { window.localStorage.removeItem(PREFIX + key); } catch { /* ignore */ }
}
