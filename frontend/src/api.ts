export type ApiErrorKind = 'network' | 'forbidden' | 'not_found' | 'conflict' | 'too_large' | 'invalid' | 'server' | 'http';

/** Map an HTTP status (0 = network failure) to a kind the UI can branch on. */
export function errorKind(status: number): ApiErrorKind {
  if (status === 0) return 'network';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status === 409) return 'conflict';
  if (status === 413) return 'too_large';
  if (status === 400 || status === 422) return 'invalid';
  if (status >= 500) return 'server';
  return 'http';
}

/** Error carrying the HTTP status so the UI can tell 404/409/413/network apart. `detail` is the backend's reason only. */
export class ApiError extends Error {
  readonly status: number;
  readonly kind: ApiErrorKind;
  readonly detail: string;
  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.kind = errorKind(status);
    this.detail = detail ?? message.replace(/^\d+\s*/, '');
  }
}

/** FastAPI returns a string, or a list of {loc,msg} validation errors. */
export function formatDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail) && typeof (detail as { error?: unknown }).error === 'string') {
    const d = detail as { error: string; missing?: unknown; notes?: unknown };
    const list = (v: unknown) => (Array.isArray(v) ? v.map(String).filter(Boolean) : []);
    const parts = [d.error];
    if (list(d.missing).length) parts.push(`missing settings: ${list(d.missing).join(', ')}`);
    if (list(d.notes).length) parts.push(list(d.notes).join(' '));
    return parts.join('. ');
  }
  if (Array.isArray(detail)) {
    return detail.map((d) => {
      const msg = typeof d?.msg === 'string' ? d.msg.replace(/^Value error,\s*/, '') : JSON.stringify(d);
      const field = Array.isArray(d?.loc) ? d.loc.filter((x: unknown) => x !== 'body').join('.') : '';
      return field ? `${field}: ${msg}` : msg;
    }).join('; ');
  }
  return JSON.stringify(detail);
}

/** Thin typed fetch wrapper. Throws ApiError (status 0 = network failure). */
export async function api<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, 'Cannot reach the backend. Check that the API server is running.');
  }
  if (!res.ok) {
    let detail: string = res.statusText;
    try {
      const body = await res.json();
      if (body && body.detail !== undefined) {
        detail = formatDetail(body.detail);
      }
    } catch { /* keep status text */ }
    throw new ApiError(res.status, `${res.status} ${detail}`, detail);
  }
  return res.json() as Promise<T>;
}

export function jsonInit(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

/** Plain-language message for an error from the API layer. */
export function describeError(err: unknown, what = 'this request'): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return err.message;
    if (err.status === 404) return `Not found (404). The backend may not support ${what} yet, or it was deleted.`;
    if (err.status === 409) return `Conflict (409): ${err.detail}`;
    if (err.status === 413) return `Too large (413): ${err.detail}`;
    if (err.status === 403) return `Not allowed (403): ${err.detail}`;
    if (err.status >= 500) return `Backend error (${err.status}): ${err.message.replace(/^\d+\s*/, '')}`;
    return err.message;
  }
  return err instanceof Error ? err.message : String(err);
}

/** Fetch a non-JSON body (JSONL dataset, report). Same error handling as api(). */
export async function apiText(path: string): Promise<string> {
  let res: Response;
  try {
    res = await fetch(path);
  } catch {
    throw new ApiError(0, 'Cannot reach the backend. Check that the API server is running.');
  }
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText}`);
  return res.text();
}

/** Read an error response body into a readable reason (JSON `detail`, else status text). */
async function failureOf(res: Response): Promise<ApiError> {
  let detail: string = res.statusText;
  try {
    const body = await res.json();
    if (body && body.detail !== undefined) detail = formatDetail(body.detail);
  } catch { /* keep status text */ }
  return new ApiError(res.status, `${res.status} ${detail}`, detail);
}

export interface Download { blob: Blob; filename: string; type: string }

/** Fetch a binary or text document. Errors (409 conflict, 413 too large, ...) keep the backend's reason. */
export async function apiDownload(path: string, fallbackName: string): Promise<Download> {
  let res: Response;
  try {
    res = await fetch(path);
  } catch {
    throw new ApiError(0, 'Cannot reach the backend. Check that the API server is running.');
  }
  if (!res.ok) throw await failureOf(res);
  const disposition = res.headers.get('content-disposition') ?? '';
  const filename = /filename="?([^";]+)"?/i.exec(disposition)?.[1] ?? fallbackName;
  const blob = await res.blob();
  return { blob, filename, type: res.headers.get('content-type') ?? blob.type };
}
