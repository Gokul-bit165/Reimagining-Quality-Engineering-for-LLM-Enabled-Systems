// Shared UI helpers. All ledger-derived text is set with textContent (it is untrusted).
export const $ = (id) => document.getElementById(id);
const SVG = "http://www.w3.org/2000/svg";
export const STATE = {
  RELEASE: ["s-release", "Release"],
  REJECT: ["s-reject", "Reject"],
  CONDITIONAL: ["s-conditional", "Conditional release"],
  INSUFFICIENT_EVIDENCE: ["s-insufficient", "Insufficient evidence"],
};
export const ACCESS = {
  A: "black-box", B: "SDK / trace in response", C: "OpenTelemetry traces",
  D: "repository", E: "gateway",
};

export function el(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const kid of kids) if (kid != null) node.append(kid);
  return node;
}
export const pct = (x) => `${(x * 100).toFixed(1)}%`;
const svg = (tag, attrs) => {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
};

export async function api(path, init) {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* keep status text */ }
    throw new Error(`${res.status} ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
  }
  return res.json();
}

export function section(id, title, ...kids) {
  const wrap = el("section", { id, "aria-labelledby": `${id}-h` });
  wrap.append(el("h2", { id: `${id}-h` }, title), ...kids.filter((k) => k != null));
  return wrap;
}

export function facts(rows) {
  const dl = el("dl", { class: "facts" });
  rows.forEach(([k, v]) => dl.append(el("dt", {}, k), el("dd", {}, v)));
  return dl;
}

export function table(headers, rows) {
  const t = el("table", { class: "tbl" });
  t.append(el("thead", {}, el("tr", {}, ...headers.map((h) => el("th", { scope: "col" }, h)))));
  const body = el("tbody");
  rows.forEach((r) => body.append(el("tr", {}, ...r.map((c) => el("td", {}, c)))));
  t.append(body);
  return el("div", { class: "tbl-wrap", tabindex: "0", role: "region", "aria-label": "table" }, t);
}

export function tag(text, cls = "") { return el("span", { class: `tag ${cls}` }, text); }

// Failure-rate interval drawn against the policy appetite line (R11: no bare point estimates).
export function intervalBar(rate, appetite) {
  const max = Math.min(1, Math.max(rate.upper, appetite ?? 0) * 1.25 + 0.02);
  const W = 600, pad = 8, x = (v) => pad + (v / max) * (W - 2 * pad);
  const s = svg("svg", { viewBox: `0 0 ${W} 48`, class: "interval", role: "img" });
  const title = svg("title", {});
  title.textContent = `Failure rate ${pct(rate.point)}, ${rate.confidence * 100}% interval ` +
    `${pct(rate.lower)} to ${pct(rate.upper)}` + (appetite != null ? `; policy appetite ${pct(appetite)}` : "");
  s.append(title, svg("line", { class: "axis", x1: pad, x2: W - pad, y1: 30, y2: 30 }));
  s.append(svg("rect", { class: "range", x: x(rate.lower), y: 22, width: Math.max(2, x(rate.upper) - x(rate.lower)), height: 16 }));
  s.append(svg("circle", { class: "point", cx: x(rate.point), cy: 30, r: 5 }));
  if (appetite != null) {
    s.append(svg("line", { class: "appetite", x1: x(appetite), x2: x(appetite), y1: 12, y2: 44 }));
    const t = svg("text", { class: "appetite-label", x: x(appetite) + 4, y: 12 });
    t.textContent = `appetite ${pct(appetite)}`;
    s.append(t);
  }
  for (const v of [0, max]) {
    const t = svg("text", { class: "tick", x: x(v), y: 47, "text-anchor": v === 0 ? "start" : "end" });
    t.textContent = pct(v);
    s.append(t);
  }
  return s;
}

const STATUS_TEXT = {
  within: "Whole interval is within the appetite.",
  above: "Whole interval is above the appetite.",
  straddles: "Interval straddles the appetite: the evidence cannot settle it.",
  no_appetite: "The policy sets no appetite for this metric.",
};

export function metricRow(m) {
  const rate = m.failure_rate;
  const row = el("div", { class: "metric" });
  row.append(el("div", { class: "metric-head" },
    el("span", { class: "metric-name mono" }, m.metric),
    el("span", { class: "metric-counts" },
      `${m.failed_cases} failed · ${m.passed_cases} passed · ${m.not_evaluable_cases} not evaluable`)));
  if (!rate) {
    row.append(el("p", { class: "empty" }, "No evaluable cases: interval unavailable."));
    return row;
  }
  row.append(intervalBar(rate, m.appetite));
  row.append(el("p", { class: "metric-read" },
    `${rate.k} of ${rate.n} evaluable cases failed; ${rate.confidence * 100}% interval ` +
    `${pct(rate.lower)} to ${pct(rate.upper)} (${rate.method.replace("_", "-")}). ${STATUS_TEXT[m.status] ?? ""}`));
  return row;
}

export function failureExamples(m) {
  if (!m.failures?.length) return null;
  const d = el("details", { class: "examples" }, el("summary", {}, `${m.failures.length} failing case(s) with evidence`));
  m.failures.forEach((f) => d.append(el("div", { class: "example" },
    el("p", {}, el("strong", {}, "Test: "), f.question ?? "(unknown)"),
    el("p", {}, el("strong", {}, "Expected: "), f.expected ?? "(none)"),
    el("p", {}, el("strong", {}, "Observed: "), f.output || "(empty)"),
    el("p", { class: "metric-read" }, `${f.state}${f.detail ? ` · ${f.detail}` : ""} · evidence `,
      el("code", {}, f.evidence_key.slice(0, 40) + "…")))));
  return d;
}
