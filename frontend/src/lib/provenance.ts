import type { EvalItem } from '../types/api';

/** Host (with port) of an endpoint URL, or null when it is missing or not a valid URL. */
export function endpointHost(url: string | null | undefined): string | null {
  if (!url) return null;
  try { return new URL(url).host; } catch { return null; }
}

/** True for localhost, 127.x.x.x, ::1 and 0.0.0.0: results then describe whatever runs on this machine. */
export function isLoopbackEndpoint(url: string | null | undefined): boolean {
  if (!url) return false;
  try {
    const h = new URL(url).hostname.replace(/^\[|\]$/g, '').toLowerCase();
    return h === 'localhost' || h.endsWith('.localhost') || h === '::1' || h === '0.0.0.0' || /^127(\.\d{1,3}){3}$/.test(h);
  } catch { return false; }
}

export const SOURCE_INFO: Record<EvalItem['source'], { label: string; text: string }> = {
  user: { label: 'Yours', text: 'A question you supplied.' },
  generated: { label: 'Generated from your docs', text: 'Written by a model from the documents you provided.' },
  security: { label: 'Security probe', text: 'An attack-style input that tests prompt injection or data leakage.' },
  regression: { label: 'Regression', text: 'A past failure added to the regression suite and re-asked.' },
};

export function sourceLabel(source: string): string {
  return (SOURCE_INFO as Record<string, { label: string }>)[source]?.label ?? source;
}
