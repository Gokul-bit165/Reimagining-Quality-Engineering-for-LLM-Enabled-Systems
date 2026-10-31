import type { HttpMethod, ResponseFormat, TargetConfig } from '../types/api';

/* Client-side mirror of qe/ingest/target_config.py and qe/ingest/vault.py.
   The backend stays the authority; this only catches mistakes before a round trip. */

export const PLACEHOLDER = '{question}';
export const MAX_CONTEXT_PATHS = 10;
const MAX_PATH_LEN = 200;
const PATH_OK = /^[A-Za-z0-9_\-.[\]*$]+$/;
const SECRET_REF = /\$\{([A-Z][A-Z0-9_]{0,63})\}/g;
const HEADER_NAME = /^[A-Za-z0-9][A-Za-z0-9-]{0,63}$/;
const SECRET_NAME = /^[A-Z][A-Z0-9_]{0,63}$/;
const FORBIDDEN_HEADERS = new Set(['host', 'content-length', 'transfer-encoding', 'connection', 'upgrade', 'te', 'trailer', 'proxy-authorization', 'expect']);
const BENIGN_LITERAL = new Set(['accept', 'content-type', 'user-agent', 'accept-language', 'x-request-id']);
const DENY_PREFIXES = ['DOCKER_', 'QE_', 'LD_', 'DYLD_', 'PYTHON', 'BASH_', 'SSL', 'GIT_', 'NODE_', 'CURL_', 'REQUESTS_', 'NPM_', 'PIP_', 'SSH_'];
const DENY_EXACT = new Set(['PATH', 'HOME', 'ENV', 'IFS', 'SHELL', 'PS4', 'USERPROFILE', 'SYSTEMROOT', 'TEMP', 'TMP', 'APPDATA', 'LOCALAPPDATA', 'COMSPEC', 'PATHEXT', 'TZ', 'WINDIR', 'OPENSSL_CONF']);

export const RESPONSE_FORMATS: { id: ResponseFormat; label: string; text: string }[] = [
  { id: 'auto', label: 'Detect automatically', text: 'Uses the response content type, then tries JSON, then plain text.' },
  { id: 'json', label: 'JSON', text: 'The response body is one JSON document.' },
  { id: 'sse', label: 'Server-sent events (streaming)', text: 'Lines starting with "data:" are joined into one answer.' },
  { id: 'text', label: 'Plain text', text: 'The whole body is the answer. No context paths apply.' },
];

export interface TemplatePreset { id: string; label: string; template: string; answerPath: string | null; note: string }

export const TEMPLATE_PRESETS: TemplatePreset[] = [
  { id: 'simple', label: 'Simple: {question}', template: '{\n  "question": "{question}"\n}', answerPath: null,
    note: 'Sends {"question": ...}. Use when your app takes one field.' },
  { id: 'openai', label: 'OpenAI-style chat', template: '{\n  "messages": [\n    { "role": "user", "content": "{question}" }\n  ]\n}',
    answerPath: 'choices.0.message.content',
    note: 'Chat-completions body. Add a "model" field if your server requires one.' },
];

export interface HeaderRow { name: string; value: string }

export interface TargetForm {
  template: string;
  method: HttpMethod;
  answerPath: string;
  /** one path per line */
  contextPaths: string;
  headers: HeaderRow[];
  format: ResponseFormat;
}

export const emptyTargetForm = (): TargetForm => ({ template: '', method: 'POST', answerPath: '', contextPaths: '', headers: [], format: 'auto' });

export function formFromConfig(cfg: TargetConfig | null | undefined): TargetForm {
  if (!cfg) return emptyTargetForm();
  return {
    template: cfg.request_template === null || cfg.request_template === undefined ? '' : JSON.stringify(cfg.request_template, null, 2),
    method: cfg.method ?? 'POST',
    answerPath: cfg.answer_path ?? '',
    contextPaths: (cfg.context_paths ?? []).join('\n'),
    headers: Object.entries(cfg.headers ?? {}).map(([name, value]) => ({ name, value })),
    format: cfg.response_format ?? 'auto',
  };
}

export interface TargetErrors {
  template?: string;
  answerPath?: string;
  contextPaths?: string;
  /** index in `headers` -> message */
  headers: Record<number, string>;
}

export const hasTargetErrors = (e: TargetErrors): boolean =>
  Boolean(e.template || e.answerPath || e.contextPaths || Object.keys(e.headers).length);

function hasPlaceholder(node: unknown): boolean {
  if (typeof node === 'string') return node.includes(PLACEHOLDER);
  if (Array.isArray(node)) return node.some(hasPlaceholder);
  if (node && typeof node === 'object') return Object.values(node).some(hasPlaceholder);
  return false;
}

export function pathError(p: string): string | null {
  if (p.length > MAX_PATH_LEN || !PATH_OK.test(p)) return `"${p.slice(0, 40)}" is not a valid path. Use dotted keys, indexes and * (for example data.answer, choices.0.message.content, sources.*.text).`;
  return null;
}

export const splitPaths = (text: string): string[] => text.split(/[\n,]/).map((s) => s.trim()).filter(Boolean);

export function secretNamesIn(value: string): string[] {
  return [...value.matchAll(SECRET_REF)].map((m) => m[1]);
}

export function isAllowedSecretName(name: string): boolean {
  if (!SECRET_NAME.test(name) || DENY_EXACT.has(name) || name.endsWith('_PROXY')) return false;
  return !DENY_PREFIXES.some((p) => name.startsWith(p));
}

/** All secret names referenced by header values, in order, unique. */
export function headerSecretNames(headers: HeaderRow[]): string[] {
  return [...new Set(headers.flatMap((h) => secretNamesIn(h.value)))];
}

/** Parse the template box. `null` means "empty" (backend sends its own default body). */
export function parseTemplate(text: string): { ok: true; value: Record<string, unknown> | unknown[] | null } | { ok: false; error: string } {
  if (!text.trim()) return { ok: true, value: null };
  let parsed: unknown;
  try { parsed = JSON.parse(text); } catch (e) {
    return { ok: false, error: `Not valid JSON: ${e instanceof Error ? e.message : 'parse error'}.` };
  }
  if (parsed === null || typeof parsed !== 'object') return { ok: false, error: 'The request must be a JSON object or array.' };
  if (!hasPlaceholder(parsed)) return { ok: false, error: `Put ${PLACEHOLDER} inside a text value so each test question can be inserted.` };
  return { ok: true, value: parsed as Record<string, unknown> | unknown[] };
}

export function validateTargetForm(f: TargetForm): TargetErrors {
  const errors: TargetErrors = { headers: {} };
  const t = parseTemplate(f.template);
  if (!t.ok) errors.template = t.error;
  else if (f.method === 'GET' && Array.isArray(t.value)) errors.template = 'For GET the request must be a flat JSON object (it becomes query parameters).';
  if (f.answerPath.trim()) errors.answerPath = pathError(f.answerPath.trim()) ?? undefined;
  const ctx = splitPaths(f.contextPaths);
  if (ctx.length > MAX_CONTEXT_PATHS) errors.contextPaths = `At most ${MAX_CONTEXT_PATHS} context paths.`;
  else {
    const bad = ctx.map(pathError).find(Boolean);
    if (bad) errors.contextPaths = bad;
  }
  const seen = new Set<string>();
  f.headers.forEach((h, i) => {
    if (!h.name.trim() && !h.value.trim()) return;
    const low = h.name.trim().toLowerCase();
    if (!HEADER_NAME.test(h.name.trim()) || FORBIDDEN_HEADERS.has(low)) errors.headers[i] = `"${h.name.trim()}" is not an allowed header name.`;
    else if (seen.has(low)) errors.headers[i] = `Header "${h.name.trim()}" is listed twice.`;
    else if (/[\r\n\0]/.test(h.value) || h.value.length > 500) errors.headers[i] = 'The value is too long or contains a line break.';
    else {
      const refs = secretNamesIn(h.value);
      const reserved = refs.find((r) => !isAllowedSecretName(r));
      if (refs.length === 0 && !BENIGN_LITERAL.has(low)) errors.headers[i] = 'Use a secret reference such as Bearer ${API_TOKEN}. Literal values would be stored in plain text.';
      else if (reserved) errors.headers[i] = `Secret name ${reserved} is reserved. Choose another (capital letters, digits, underscores).`;
    }
    seen.add(low);
  });
  return errors;
}

/** Build the body for POST /target-config. Call only after validateTargetForm() came back clean. */
export function toTargetConfig(f: TargetForm): TargetConfig {
  const t = parseTemplate(f.template);
  return {
    request_template: t.ok ? t.value : null,
    method: f.method,
    answer_path: f.answerPath.trim() || null,
    context_paths: splitPaths(f.contextPaths),
    headers: Object.fromEntries(f.headers.filter((h) => h.name.trim()).map((h) => [h.name.trim(), h.value.trim()])),
    response_format: f.format,
  };
}

export const CONTEXTS_KIND_TEXT: Record<'text' | 'ids' | 'none', string> = {
  text: 'Passage text. Faithfulness and retrieval can be measured.',
  ids: 'Ids or file names only, not passage text. Faithfulness will not be measured.',
  none: 'No contexts returned. Faithfulness and retrieval cannot be measured.',
};
