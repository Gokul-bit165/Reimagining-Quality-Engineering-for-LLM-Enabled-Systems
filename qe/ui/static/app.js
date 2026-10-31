// qe evidence UI. No build step. All ledger-derived text is set with textContent (untrusted).
const $ = (id) => document.getElementById(id);
const SVG = "http://www.w3.org/2000/svg";
const STATE = {
  RELEASE: ["s-release", "Release"],
  REJECT: ["s-reject", "Reject"],
  CONDITIONAL: ["s-conditional", "Conditional"],
  INSUFFICIENT_EVIDENCE: ["s-insufficient", "Insufficient evidence"],
};
const ACCESS = {
  A: "black-box", B: "SDK / trace in response", C: "OpenTelemetry traces",
  D: "repository", E: "gateway",
};

function el(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const kid of kids) node.append(kid);
  return node;
}
const pct = (x) => `${(x * 100).toFixed(1)}%`;
const svg = (tag, attrs) => {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
};

async function api(path, init) {
  const res = await fetch(path, init);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// ---- interval bar: failure-rate interval against the policy appetite line -------------
function intervalBar(rate, appetite) {
  const max = Math.min(1, Math.max(rate.upper, appetite ?? 0) * 1.25 + 0.02);
  const W = 600, pad = 8, x = (v) => pad + (v / max) * (W - 2 * pad);
  const s = svg("svg", { viewBox: `0 0 ${W} 48`, class: "interval", role: "img" });
  const desc = `Failure rate ${pct(rate.point)}, ${rate.confidence * 100}% interval ` +
    `${pct(rate.lower)} to ${pct(rate.upper)}` +
    (appetite != null ? `; policy appetite ${pct(appetite)}` : "");
  s.append(svg("title", {}), svg("line", { class: "axis", x1: pad, x2: W - pad, y1: 30, y2: 30 }));
  s.firstChild.textContent = desc;
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

function metricRow(m, appetite) {
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
  row.append(intervalBar(rate, appetite));
  let read = `${rate.k} of ${rate.n} evaluable cases failed; ${rate.confidence * 100}% interval ` +
    `${pct(rate.lower)} to ${pct(rate.upper)} (${rate.method.replace("_", "-")}).`;
  if (appetite != null) {
    read += rate.upper <= appetite ? " Whole interval is within the appetite."
      : rate.lower > appetite ? " Whole interval is above the appetite."
      : " Interval straddles the appetite: the evidence cannot settle it.";
  }
  row.append(el("p", { class: "metric-read" }, read));
  return row;
}

// ---- sections ------------------------------------------------------------------------
function decisionSection(run) {
  const d = run.pack.decision;
  const [cls, label] = STATE[d.decision] ?? ["s-insufficient", d.decision];
  const frag = document.createDocumentFragment();
  frag.append(el("p", { class: "eyebrow" }, `${run.id} · policy ${d.policy_version}`));
  frag.append(el("h1", { class: `decision ${cls}` }, label));
  const lede = {
    RELEASE: "Every required metric's interval sits inside the policy appetite. Human sign-off is still required.",
    REJECT: "At least one required metric is entirely above the policy appetite.",
    CONDITIONAL: "Release is allowed only if the listed conditions hold.",
    INSUFFICIENT_EVIDENCE: "The evidence cannot support a release or a rejection under this policy. This is a valid outcome, not an error.",
  }[d.decision];
  frag.append(el("p", { class: "lede" }, lede));
  if (run.pack.policy.example_only) {
    frag.append(el("p", { class: "notice" }, el("strong", {}, "Example policy. "),
      "Its appetites are illustrative and are not a recommendation."));
  }
  const conditions = (d.conditions ?? []).filter((c) => !c.startsWith("EXAMPLE policy"));
  if (conditions.length) {
    const ul = el("ul", { class: "plain" });
    conditions.forEach((c) => ul.append(el("li", {}, c)));
    frag.append(ul);
  }
  return frag;
}

function section(title, ...kids) {
  const wrap = document.createDocumentFragment();
  wrap.append(el("h2", {}, title), ...kids);
  return wrap;
}

function facts(rows) {
  const dl = el("dl", { class: "facts" });
  rows.forEach(([k, v]) => dl.append(el("dt", {}, k), el("dd", {}, v)));
  return dl;
}

function renderRun(run) {
  const main = $("main");
  main.replaceChildren(decisionSection(run));
  const pack = run.pack;
  const levels = pack.access.visibility_levels;
  main.append(section("Access level",
    el("p", {}, levels.length
      ? `Runs were observed at level ${levels.join(", ")} (${levels.map((l) => ACCESS[l] ?? l).join(", ")}). ${pack.access.note}`
      : "No runs recorded, so no access level was observed.")));
  const metrics = pack.metrics.length
    ? pack.metrics.map((m) => metricRow(m, run.appetite[m.metric]))
    : [el("p", { class: "empty" }, "No verdicts recorded yet.")];
  main.append(section("Evidence", ...metrics));
  main.append(section("Runs", facts([
    ["Recorded", String(pack.runs.recorded)],
    ["With errors", String(pack.runs.with_errors.length)],
    ["Not run (budget or kill switch)", String(pack.runs.unrun_budget_or_kill.length)],
  ])));
  main.append(section("Ledger integrity", facts([
    ["Hash chain", pack.ledger.verified ? "verified" : "FAILED"],
    ["Entries", String(pack.ledger.entries)],
    ["Head", el("code", {}, pack.ledger.head)],
    ["Human sign-off", pack.human_signoff],
  ])));
  const claims = el("ul", { class: "plain" });
  pack.claims_not_made.forEach((c) => claims.append(el("li", {}, c)));
  main.append(section("Claims not made", claims));
  document.title = `${label(run)} · ${run.id} · qe`;
  main.focus({ preventScroll: true });
}
const label = (run) => (STATE[run.pack.decision.decision] ?? [0, run.pack.decision.decision])[1];

// ---- run list + routing --------------------------------------------------------------
let runs = [];
function renderList(activeId) {
  const list = $("run-list"), select = $("run-select");
  list.replaceChildren(); select.replaceChildren();
  for (const r of runs) {
    const [cls, text] = STATE[r.decision] ?? ["s-insufficient", r.decision];
    const btn = el("button", { type: "button", "aria-current": String(r.id === activeId) },
      el("span", { class: "run-name" }, `${r.app} · ${r.variant}`),
      el("span", { class: "run-meta" }, el("span", { class: `chip ${cls}` }, text)));
    btn.addEventListener("click", () => { location.hash = r.id; });
    list.append(el("li", {}, btn));
    const opt = el("option", { value: r.id }, `${r.app} · ${r.variant} — ${text}`);
    if (r.id === activeId) opt.selected = true;
    select.append(opt);
  }
}
async function show(id) {
  renderList(id);
  try { renderRun(await api(`/api/runs/${encodeURIComponent(id)}`)); }
  catch (e) { $("main").replaceChildren(el("p", { class: "error" }, `Could not load ${id}: ${e.message}`)); }
}
async function load() {
  try { runs = await api("/api/runs"); }
  catch (e) { $("main").replaceChildren(el("p", { class: "error" }, `Could not load runs: ${e.message}`)); return; }
  if (!runs.length) {
    renderList(null);
    $("main").replaceChildren(el("h1", { class: "decision" }, "No runs yet"),
      el("p", { class: "lede" }, "Use “Regenerate demo runs” to create four offline demo ledgers."));
    return;
  }
  const wanted = decodeURIComponent(location.hash.slice(1));
  show(runs.some((r) => r.id === wanted) ? wanted : runs[runs.length - 1].id);
}
$("run-select").addEventListener("change", (e) => { location.hash = e.target.value; });
window.addEventListener("hashchange", load);
$("demo-btn").addEventListener("click", async (ev) => {
  const btn = ev.currentTarget, status = $("demo-status");
  btn.disabled = true; status.textContent = "Running the sandbox apps…";
  try { runs = await api("/api/demo", { method: "POST" }); status.textContent = "Done."; await load(); }
  catch (e) { status.textContent = `Failed: ${e.message}`; }
  finally { btn.disabled = false; }
});
load();
