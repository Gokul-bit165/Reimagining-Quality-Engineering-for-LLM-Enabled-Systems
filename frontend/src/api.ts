/** Error carrying the HTTP status so the UI can tell 404/409/network apart. */
export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** FastAPI returns a string, or a list of {loc,msg} validation errors. */
export function formatDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail;
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
    throw new ApiError(res.status, `${res.status} ${detail}`);
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
    if (err.status === 409) return `Conflict (409): ${err.message.replace(/^409\s*/, '')}`;
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
