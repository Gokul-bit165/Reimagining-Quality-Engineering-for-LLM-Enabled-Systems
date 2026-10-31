/** Thin fetch wrapper matching the vanilla lib.js `api()` function. */
export async function api<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail: string = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch { /* keep status text */ }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json();
}

