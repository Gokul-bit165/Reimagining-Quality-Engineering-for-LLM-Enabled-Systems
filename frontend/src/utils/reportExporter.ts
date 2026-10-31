import type { Evaluation, EvalMetric } from '../types/api';

/* ── Evaluation (Connect-your-RAG-app flow) exports ─────────────── */

function escapeCsv(val: unknown): string {
  if (val === null || val === undefined) return '""';
  return `"${String(val).replace(/"/g, '""')}"`;
}

function pct(n?: number | null): string {
  if (n === null || n === undefined) return 'N/A';
  return `${(n * 100).toFixed(1)}%`;
}

function download(content: string, mime: string, filename: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function esc(v: unknown): string {
  return String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function ciText(m: EvalMetric): string {
  if (m.value === null || m.ci_low === null || m.ci_high === null) return `not measured (n=${m.n})`;
  return `${pct(m.value)} (95% CI ${pct(m.ci_low)} to ${pct(m.ci_high)}, n=${m.n})`;
}

/** Build the CSV text (pure, testable). */
export function evaluationCsv(ev: Evaluation): string {
  const lines: string[] = ['﻿Evaluation,' + escapeCsv(ev.id)];
  lines.push(`Verdict,${escapeCsv(ev.decision?.verdict ?? 'none')}`);
  (ev.decision?.reasons ?? []).forEach((r) => lines.push(`Reason,${escapeCsv(r)}`));
  lines.push('');
  lines.push('Metric,Value,CI low,CI high,n,Note');
  Object.entries({ ...ev.metrics, ...(ev.scorecard ?? {}) }).forEach(([name, m]) =>
    lines.push([name, m.value, m.ci_low, m.ci_high, m.n, m.note ?? ''].map(escapeCsv).join(',')));
  lines.push('');
  lines.push('Item,Source,Passed,Failure class,Failure reason,Question,Reference answer,Answer,Contexts');
  ev.items.forEach((i) =>
    lines.push([i.id, i.source, i.passed === null ? 'n/a' : i.passed, i.failure_class ?? '', i.failure_reason ?? '', i.question,
      i.reference_answer ?? '', i.answer ?? '', i.contexts.join(' | ')].map(escapeCsv).join(',')));
  return lines.join('\r\n');
}

export function exportEvaluationCsv(ev: Evaluation) {
  download(evaluationCsv(ev), 'text/csv;charset=utf-8', `${ev.id}_evaluation.csv`);
}

export function exportEvaluationJson(ev: Evaluation) {
  download(JSON.stringify(ev, null, 2), 'application/json', `${ev.id}_evaluation.json`);
}

export function exportEvaluationDoc(ev: Evaluation) {
  const rows = Object.entries({ ...ev.metrics, ...(ev.scorecard ?? {}) })
    .map(([k, m]) => `<tr><td>${esc(k)}</td><td>${esc(ciText(m))}</td><td>${esc(m.note ?? '')}</td></tr>`).join('');
  const failed = ev.items.filter((i) => i.passed === false);
  const html = `<html><head><meta charset="utf-8"><title>${esc(ev.id)}</title></head><body style="font-family:Calibri,Arial,sans-serif">
<h1>Evaluation ${esc(ev.id)}</h1>
<h2>Verdict: ${esc(ev.decision?.verdict ?? 'none')}</h2>
<ul>${(ev.decision?.reasons ?? []).map((r) => `<li>${esc(r)}</li>`).join('')}</ul>
<h2>Metrics</h2><table border="1" cellpadding="4"><tr><th>Metric</th><th>Value with 95% interval</th><th>Note</th></tr>${rows}</table>
<h2>Failures (${failed.length} of ${ev.items.length})</h2>
${failed.map((i) => `<h3>${esc(i.id)} (${esc(i.source)})</h3><p><b>Q:</b> ${esc(i.question)}</p><p><b>A:</b> ${esc(i.answer)}</p><p><b>Why failed:</b> ${esc(i.failure_reason)}</p>`).join('')}
</body></html>`;
  download(html, 'application/msword;charset=utf-8', `${ev.id}_evaluation.doc`);
}

export function downloadText(content: string, filename: string, mime = 'text/plain;charset=utf-8') {
  download(content, mime, filename);
}
