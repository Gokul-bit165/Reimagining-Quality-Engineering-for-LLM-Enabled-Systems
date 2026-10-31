// Model benchmark dashboard: choose models, run the same generated suite on each, compare.
import { api, el, pct, section, table, tag } from "./lib.js";

const SVG = "http://www.w3.org/2000/svg";
const METRIC_LABEL = {
  faithfulness: "Faithfulness", answer_accuracy: "Answer accuracy", abstention: "Abstention",
  injection_resistance: "Injection resistance", consistency: "Consistency",
};
let pollTimer = null;

function miniBar(rate) {
  const W = 220, pad = 4, x = (v) => pad + v * (W - 2 * pad);
  const s = document.createElementNS(SVG, "svg");
  s.setAttribute("viewBox", `0 0 ${W} 20`); s.setAttribute("class", "mini"); s.setAttribute("role", "img");
  const mk = (tag, attrs) => { const n = document.createElementNS(SVG, tag); Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v)); return n; };
  const title = mk("title", {});
  title.textContent = `Failure rate ${pct(rate.point)}, 95% interval ${pct(rate.lower)} to ${pct(rate.upper)}`;
  s.append(title, mk("line", { class: "axis", x1: pad, x2: W - pad, y1: 10, y2: 10 }),
    mk("rect", { class: "range", x: x(rate.lower), y: 5, width: Math.max(2, x(rate.upper) - x(rate.lower)), height: 10 }),
    mk("circle", { class: "point", cx: x(rate.point), cy: 10, r: 3.5 }));
  return s;
}

export async function showBenchForm(main) {
  const info = await api("/api/benchmarks/models");
  const boxes = info.simulated.map((m) => el("label", { class: "check" },
    el("input", { type: "checkbox", value: m.id, name: "sim", checked: "" }),
    el("span", {}, el("strong", {}, `${m.id} `), tag("simulated reference", "t-sim"), ` ${m.description}`)));
  const real = el("input", { id: "b-real", placeholder: info.suggested_real.join(", ") || "vendor/model:free",
    autocomplete: "off", ...(info.real_available ? {} : { disabled: "" }) });
  const focus = el("input", { id: "b-focus", maxlength: "300", placeholder: "optional, e.g. returns and refunds" });
  const n = el("select", { id: "b-n" }, ...[5, 10, 15, 20].map((v) => el("option", { value: v, ...(v === 10 ? { selected: "" } : {}) }, `${v} tests`)));
  const rep = el("select", { id: "b-rep" }, ...[1, 2, 3].map((v) => el("option", { value: v, ...(v === 2 ? { selected: "" } : {}) }, `${v} repeat${v > 1 ? "s" : ""}`)));
  const status = el("p", { role: "status", class: "metric-read" });
  const form = el("form", { class: "form" },
    el("fieldset", {}, el("legend", {}, "Simulated reference models (always available, offline)"), ...boxes),
    el("label", { for: "b-real" }, info.real_available ? "Real models on OpenRouter (comma separated ids)"
      : `Real models unavailable: ${info.reason ?? "not configured"}`), real,
    el("label", { for: "b-focus" }, "Focus (steers which documents the questions come from)"), focus,
    el("label", { for: "b-n" }, "Suite size"), n, el("label", { for: "b-rep" }, "Repeats per test (for consistency)"), rep,
    el("button", { class: "btn", type: "submit" }, "Run benchmark"), status);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const models = [...form.querySelectorAll("input[name=sim]:checked")].map((i) => i.value)
      .concat(real.value.split(",").map((s) => s.trim()).filter(Boolean));
    const btn = form.querySelector("button[type=submit]"); btn.disabled = true;
    status.textContent = "Starting…";
    try {
      const res = await api("/api/benchmarks", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ models, focus: focus.value, n_tests: Number(n.value), repeats: Number(rep.value) }) });
      location.hash = res.id;
    } catch (e) { status.textContent = `Could not start: ${e.message}`; btn.disabled = false; }
  });
  main.replaceChildren(el("p", { class: "eyebrow" }, "Model benchmark"), el("h1", { class: "decision" }, "Compare models"),
    el("p", { class: "lede" }, "Every model answers the same generated suite: grounded questions, false premises, unanswerable questions and hidden prompt injections. Results are shown per metric with exact intervals, side by side."),
    el("p", { class: "notice" }, el("strong", {}, "Free tiers are rate limited. "),
      "Real calls are paced about 3 seconds apart; each model makes tests × repeats calls. A call that fails is shown as missing evidence, never as a failed test."),
    form);
  document.title = "Model benchmark · qe";
}

function comparisonTable(rep) {
  const names = Object.keys(rep.models);
  const head = ["Metric", ...names];
  const rows = rep.comparison.map((c) => [
    el("span", {}, el("strong", {}, METRIC_LABEL[c.metric] ?? c.metric), el("br"), el("span", { class: "metric-read" }, c.meaning)),
    ...names.map((m) => {
      const r = c.cells[m], cell = rep.models[m].metrics[c.metric];
      if (!r) return el("span", { class: "empty" }, cell.not_evaluable ? "not evaluable" : "no evidence");
      return el("div", {}, el("strong", {}, `${cell.failed} / ${cell.failed + cell.passed} failed`), el("br"),
        el("span", { class: "metric-read" }, `${pct(r.lower)} to ${pct(r.upper)}`), miniBar(r));
    })]);
  return table(head, rows);
}

function modelSection(name, m) {
  const sec = el("section", { class: "model" });
  sec.append(el("h3", {}, name, " ", tag(m.simulated ? "simulated reference" : "real model", m.simulated ? "t-sim" : "t-warn")));
  const r = m.runs;
  sec.append(el("p", { class: "metric-read" }, `${r.total} calls, ${r.errors} errored` +
    (r.errors ? ` (no evidence, not counted as failures): ${r.error_kinds.join("; ")}` : "")));
  Object.entries(m.metrics).forEach(([metric, x]) => {
    if (!x.examples.length) return;
    const d = el("details", { class: "examples" }, el("summary", {}, `${METRIC_LABEL[metric] ?? metric}: ${x.failed} failing test(s)`));
    x.examples.forEach((ex) => d.append(el("div", { class: "example" },
      el("p", {}, el("strong", {}, `Test (${ex.style}): `), ex.question), el("p", {}, el("strong", {}, "Model said: "), ex.output || "(empty)"),
      el("p", { class: "metric-read" }, ex.detail ?? ""))));
    sec.append(d);
  });
  return sec;
}

function render(main, id, body) {
  const rep = body.report, st = body.status;
  const frag = document.createDocumentFragment();
  frag.append(el("p", { class: "eyebrow" }, `${id} · focus: ${rep?.benchmark.focus || "none"}`),
    el("h1", { class: "decision" }, "Model benchmark"));
  if (st.state === "running") {
    frag.append(el("p", { class: "lede" }, `Running… ${st.done} of ${st.total} calls`),
      el("progress", { max: st.total, value: st.done, "aria-label": "Benchmark progress" }),
      el("p", { class: "metric-read", role: "status" }, st.note));
  }
  if (st.state === "error") frag.append(el("p", { class: "error" }, `The benchmark failed: ${st.error}`));
  if (rep && st.state !== "error") {
    frag.append(el("div", { class: "labels" }, ...Object.entries(rep.models).map(([m, v]) =>
      tag(`${m}: ${v.simulated ? "simulated" : "real"}`, v.simulated ? "t-sim" : "t-warn"))));
    frag.append(section("compare", "Side-by-side comparison", comparisonTable(rep)));
    const sep = rep.comparison.flatMap((c) => c.separable.map((s) => `${METRIC_LABEL[c.metric]}: ${s}`));
    frag.append(section("separation", "What can be concluded",
      sep.length ? el("ul", { class: "plain" }, ...sep.map((s) => el("li", {}, s)))
        : el("p", {}, "No pair of models is separable on any metric at this sample size: every interval overlaps. This is not a tie claim, it is a limit of the evidence."),
      el("p", { class: "metric-read" }, rep.benchmark.suite_generator ? `Suite: ${rep.benchmark.suite.n} tests (${Object.entries(rep.benchmark.suite.styles).map(([k, v]) => `${v} ${k}`).join(", ")}); generated by a ${rep.benchmark.suite_generator}.` : "")));
    frag.append(section("models", "Per-model evidence", ...Object.entries(rep.models).map(([n, m]) => modelSection(n, m))));
    frag.append(section("notes", "Read this before quoting a result",
      el("ul", { class: "plain" }, ...rep.notes.map((t) => el("li", {}, t))),
      el("p", { class: "metric-read" }, `Ledger: ${rep.ledger.entries} entries, hash chain ${rep.ledger.verified ? "verified" : "FAILED"}, head ${rep.ledger.head.slice(0, 16)}…`)));
  }
  main.replaceChildren(frag);
}

export async function showBench(main, id) {
  clearTimeout(pollTimer);
  const tick = async () => {
    try {
      const body = await api(`/api/benchmarks/${encodeURIComponent(id)}`);
      render(main, id, body);
      document.title = `Model benchmark · ${id} · qe`;
      if (body.status.state === "running") pollTimer = setTimeout(tick, 2000);
    } catch (e) { main.replaceChildren(el("p", { class: "error" }, `Could not load ${id}: ${e.message}`)); }
  };
  await tick();
}

export function stopPolling() { clearTimeout(pollTimer); }
