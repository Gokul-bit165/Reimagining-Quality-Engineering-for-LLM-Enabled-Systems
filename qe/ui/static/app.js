// qe evidence UI: scenario form, run list, hash routing. No build step.
import { $, STATE, api, el } from "./lib.js";
import { renderReport } from "./report.js";

const EXAMPLES = {
  rag: ["LLM09", "Customers receive wrong or invented shipping and returns policy facts"],
  toolagent: ["LLM06", "The agent may act on a user's false claim of authority or post data to look-alike hosts"],
};
let runs = [];
let taxonomy = { entries: [], apps: [] };
let lastFailures = [];
let config = { real_available: false };

const sidOf = (id) => id.split("-")[1];
const variantOf = (id) => id.slice(id.lastIndexOf("-") + 1);
const route = () => decodeURIComponent(location.hash.slice(1));

function renderRail(active) {
  const list = $("run-list"), select = $("run-select");
  list.replaceChildren(); select.replaceChildren(el("option", { value: "new" }, "New scenario"));
  const seeded = runs.filter((r) => r.id.startsWith("scn-") && r.variant === "seeded");
  for (const r of seeded) {
    const [cls, text] = STATE[r.decision] ?? ["s-insufficient", r.decision];
    const here = active !== "new" && sidOf(r.id) === sidOf(active);
    const btn = el("button", { type: "button", "aria-current": String(here) },
      el("span", { class: "run-name" }, `${r.app.split("-").pop()} · ${sidOf(r.id)}`),
      el("span", { class: "run-meta" }, el("span", { class: `chip ${cls}` }, text), " seeded"));
    btn.addEventListener("click", () => { location.hash = r.id; });
    list.append(el("li", {}, btn));
    const opt = el("option", { value: r.id }, `${r.app.split("-").pop()} ${sidOf(r.id)}: ${text}`);
    if (here) opt.selected = true;
    select.append(opt);
  }
  if (!seeded.length) list.append(el("li", { class: "empty rail-empty" }, "No scenarios yet."));
  $("new-btn").setAttribute("aria-current", String(active === "new"));
}

function variantToggle(id) {
  const sibling = (v) => id.slice(0, id.lastIndexOf("-") + 1) + v;
  const mk = (v, label) => el("button", { type: "button", class: "seg", "aria-pressed": String(variantOf(id) === v),
    onclick: () => { location.hash = sibling(v); } }, label);
  return el("div", { class: "seg-group", role: "group", "aria-label": "Application variant" },
    mk("seeded", "Seeded-defect app"), mk("clean", "Clean control app"));
}

async function showReport(id) {
  const main = $("main");
  main.replaceChildren(el("p", { class: "empty" }, "Loading report…"));
  try {
    const r = await api(`/api/runs/${encodeURIComponent(id)}/report`);
    lastFailures = [...new Set(r.failures.map((f) => f.source_id).filter(Boolean))];
    await renderReport(main, r, { reload: () => showReport(id), hashFor: () => id });
    main.prepend(variantToggle(id));
    document.title = `${(STATE[r.decision.decision] ?? [0, r.decision.decision])[1]} · ${id} · qe`;
    main.focus({ preventScroll: true });
  } catch (e) {
    main.replaceChildren(el("p", { class: "error" }, `Could not load ${id}: ${e.message}`));
  }
}

function showForm() {
  const main = $("main");
  const app = el("select", { id: "f-app" }, ...taxonomy.apps.map((a) => el("option", { value: a }, a)));
  const tax = el("select", { id: "f-tax" }, ...taxonomy.entries.map((t) => el("option", { value: t.id }, `${t.id} ${t.title}`)));
  const text = el("textarea", { id: "f-text", rows: "3", maxlength: "500", required: "" });
  const budget = el("input", { id: "f-budget", type: "number", min: "1", max: "40", value: "12" });
  const mode = el("select", { id: "f-mode" }, el("option", { value: "simulated" }, "Simulated (offline, deterministic)"));
  if (config.real_available) {
    mode.append(el("option", { value: "real" }, `Real models via OpenRouter (tester ${config.tester_model}, target ${config.target_model})`));
  }
  const feed = el("input", { id: "f-feed", type: "checkbox" });
  if (!lastFailures.length) feed.disabled = true;
  const status = el("p", { role: "status", class: "metric-read" });
  const fill = () => { const [t, s] = EXAMPLES[app.value]; tax.value = t; text.value = s; };
  app.addEventListener("change", fill); fill();
  const form = el("form", { class: "form" },
    el("label", { for: "f-app" }, "Sandbox application"), app,
    el("label", { for: "f-tax" }, "Risk category (OWASP LLM)"), tax,
    el("label", { for: "f-text" }, "Risk scenario"), text,
    el("label", { for: "f-budget" }, "Test budget (number of tests to generate)"), budget,
    el("label", { for: "f-mode" }, config.real_available ? "Mode" : `Mode (real models unavailable: ${config.reason ?? "not configured"})`), mode,
    el("label", { class: "check" }, feed, ` Also target previous failures${lastFailures.length ? ` (${lastFailures.join(", ")})` : " (open a run with failures first)"}`),
    el("button", { class: "btn", type: "submit" }, "Generate tests and run"), status);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const btn = form.querySelector("button[type=submit]");
    btn.disabled = true;
    status.textContent = mode.value === "real"
      ? "Calling real models: this can take several minutes on free tiers (rate limits)…"
      : "Generating tests, executing, attacking, classifying… (about 10 seconds)";
    try {
      const res = await api("/api/scenarios", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ app: app.value, taxonomy_id: tax.value, scenario: text.value, budget: Number(budget.value),
          previous_failures: feed.checked ? lastFailures : [], mode: mode.value }) });
      runs = await api("/api/runs");
      location.hash = res.runs[1];
    } catch (e) { status.textContent = `Failed: ${e.message}`; btn.disabled = false; }
  });
  main.replaceChildren(el("p", { class: "eyebrow" }, "Step 1 of the pipeline"), el("h1", { class: "decision" }, "New risk scenario"),
    el("p", { class: "lede" }, "Describe a risk. The framework drafts tests from it and the application's own sources, runs them against a seeded-defect app and a clean control, attacks both, and recommends a release decision."),
    el("p", { class: "notice" }, el("strong", {}, "Simulated. "), "Generation and the target applications run offline on a deterministic stand-in. No real model is called and nothing leaves this machine."),
    form);
  document.title = "New scenario · qe";
}

async function load() {
  try {
    [runs, taxonomy, config] = await Promise.all([api("/api/runs"),
      taxonomy.entries.length ? taxonomy : api("/api/taxonomy"), api("/api/config")]);
  } catch (e) { $("main").replaceChildren(el("p", { class: "error" }, `Could not load: ${e.message}`)); return; }
  const id = route();
  const known = runs.some((r) => r.id === id);
  renderRail(known ? id : "new");
  if (known) await showReport(id); else showForm();
}

$("new-btn").addEventListener("click", () => { location.hash = "new"; load(); });
$("run-select").addEventListener("change", (e) => { location.hash = e.target.value; });
window.addEventListener("hashchange", load);
load();
