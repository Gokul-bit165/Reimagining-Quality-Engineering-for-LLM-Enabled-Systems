import type { ProjectQaPair } from '../types/api';

export interface ParseResult<T> {
  rows: T[];
  errors: string[];
}

/** Minimal RFC 4180 CSV parser (quoted fields, escaped quotes, CRLF, newlines in quotes). */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let inQuotes = false;
  const src = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
  for (let i = 0; i < src.length; i++) {
    const ch = src[i];
    if (inQuotes) {
      if (ch === '"' && src[i + 1] === '"') { field += '"'; i++; }
      else if (ch === '"') inQuotes = false;
      else field += ch;
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ',') {
      row.push(field); field = '';
    } else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && src[i + 1] === '\n') i++;
      row.push(field); field = '';
      if (row.some((c) => c.trim() !== '')) rows.push(row);
      row = [];
    } else {
      field += ch;
    }
  }
  row.push(field);
  if (row.some((c) => c.trim() !== '')) rows.push(row);
  return rows;
}

const QUESTION_KEYS = ['question', 'query', 'prompt', 'q'];
const ANSWER_KEYS = ['reference_answer', 'reference', 'expected', 'answer', 'ground_truth', 'a'];
const ANSWERABLE_KEYS = ['answerable'];
const YES = new Set(['true', 'yes', 'y', '1', 'answerable']);
const NO = new Set(['false', 'no', 'n', '0', 'not answerable', 'unanswerable']);

/** true / false / null (unknown). Anything unrecognised reads as unknown, never as a guess. */
export function parseAnswerable(v: unknown): boolean | null {
  if (typeof v === 'boolean') return v;
  if (typeof v === 'number') return v === 1 ? true : v === 0 ? false : null;
  const t = String(v ?? '').trim().toLowerCase();
  if (YES.has(t)) return true;
  if (NO.has(t)) return false;
  return null;
}

/** Build a pair. A "not answerable" item cannot carry a reference answer (backend rule): it is dropped with a note. */
function makePair(question: string, ref: string, answerableRaw: unknown, where: string, errors: string[]): ProjectQaPair {
  const answerable = parseAnswerable(answerableRaw);
  const pair: ProjectQaPair = { question };
  if (answerable === false && ref) {
    errors.push(`${where}: marked not answerable but has a reference answer. The reference answer was dropped.`);
  } else if (ref) pair.reference_answer = ref;
  if (answerable !== null) pair.answerable = answerable;
  return pair;
}

function pickKey(keys: string[], candidates: string[]): number {
  return keys.findIndex((k) => candidates.includes(k.trim().toLowerCase()));
}

export function parseQaCsv(text: string): ParseResult<ProjectQaPair> {
  const table = parseCsv(text);
  if (table.length === 0) return { rows: [], errors: ['The CSV is empty.'] };
  const header = table[0];
  const qi = pickKey(header, QUESTION_KEYS);
  const hasHeader = qi >= 0;
  const questionCol = hasHeader ? qi : 0;
  const answerCol = hasHeader ? pickKey(header, ANSWER_KEYS) : header.length > 1 ? 1 : -1;
  const answerableCol = hasHeader ? pickKey(header, ANSWERABLE_KEYS) : -1;
  const body = hasHeader ? table.slice(1) : table;
  const rows: ProjectQaPair[] = [];
  const errors: string[] = [];
  body.forEach((cells, idx) => {
    const question = (cells[questionCol] ?? '').trim();
    if (!question) { errors.push(`Row ${idx + (hasHeader ? 2 : 1)}: missing question, skipped.`); return; }
    const ref = answerCol >= 0 ? (cells[answerCol] ?? '').trim() : '';
    rows.push(makePair(question, ref, answerableCol >= 0 ? cells[answerableCol] : null, `Row ${idx + (hasHeader ? 2 : 1)}`, errors));
  });
  return { rows, errors };
}

export function parseQaJsonl(text: string): ParseResult<ProjectQaPair> {
  const rows: ProjectQaPair[] = [];
  const errors: string[] = [];
  text.split(/\r?\n/).forEach((line, idx) => {
    if (!line.trim()) return;
    try {
      const obj = JSON.parse(line) as Record<string, unknown>;
      const qKey = Object.keys(obj).find((k) => QUESTION_KEYS.includes(k.toLowerCase()));
      const aKey = Object.keys(obj).find((k) => ANSWER_KEYS.includes(k.toLowerCase()));
      const bKey = Object.keys(obj).find((k) => ANSWERABLE_KEYS.includes(k.toLowerCase()));
      const question = qKey ? String(obj[qKey] ?? '').trim() : '';
      if (!question) { errors.push(`Line ${idx + 1}: no "question" field, skipped.`); return; }
      const ref = aKey ? String(obj[aKey] ?? '').trim() : '';
      rows.push(makePair(question, ref, bKey ? obj[bKey] : null, `Line ${idx + 1}`, errors));
    } catch {
      errors.push(`Line ${idx + 1}: not valid JSON, skipped.`);
    }
  });
  return { rows, errors };
}

/** Pick the parser by file name or by sniffing content. */
export function parseQaText(text: string, fileName = ''): ParseResult<ProjectQaPair> {
  const lower = fileName.toLowerCase();
  const trimmed = text.trimStart();
  if (lower.endsWith('.jsonl') || lower.endsWith('.ndjson') || trimmed.startsWith('{')) {
    return parseQaJsonl(text);
  }
  return parseQaCsv(text);
}

/** True if text decoded from a binary file (e.g. a real PDF) rather than plain text. */
export function looksBinary(text: string): boolean {
  if (text.startsWith('%PDF')) return true;
  const sample = text.slice(0, 2000);
  if (!sample) return false;
  // eslint-disable-next-line no-control-regex
  const control = sample.match(/[\u0000-\u0008\u000E-\u001F�]/g)?.length ?? 0;
  return control / sample.length > 0.05;
}
