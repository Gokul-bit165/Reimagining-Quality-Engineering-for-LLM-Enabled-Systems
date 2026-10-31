// Scenario report: one section per stage of the brief. Everything shown comes from the ledger.
import { ACCESS, STATE, api, el, facts, failureExamples, intervalBar, metricRow, pct, section, table, tag } from "./lib.js";

const SURFACE = {
  direct_injection: "direct injection", indirect_injection: "indirect injection",
  rag_poisoning: "RAG poisoning", tool_misuse: "tool misuse", memory_poisoning: "memory poisoning",
};

function labels(r) {
  const row = el("div", { class: "labels" });
  row.append(tag("SIMULATED generation", "t-sim"), tag("FakeLLM sandbox target", "t-sim"),
    tag(r.labels.policy, "t-warn"));
  return row;
}

function decisionBlock(r) {
  const d = r.decision;
  const [cls, label] = STATE[d.decision] ?? ["s-insufficient", d.decision];
  const frag = document.createDocumentFragment();
  frag.append(el("p", { class: "eyebrow" }, `${r.id} · policy ${d.policy_version}`));
  frag.append(el("h1", { class: `decision ${cls}` }, label));
  const lede = {
    RELEASE: "Every required metric's interval is inside the policy appetite. A human must still sign off.",
    REJECT: "At least one required metric is entirely above the policy appetite.",
    CONDITIONAL: "Release is allowed only if the listed conditions hold, and a human signs off.",
    INSUFFICIENT_EVIDENCE: "The evidence cannot support a release or a rejection under this policy. This is a valid outcome, not an error.",
  }[d.decision];
  frag.append(el("p", { class: "lede" }, lede));
  frag.append(labels(r));
  return frag;
}

function scenarioSection(r) {
  const s = r.scenario;
  return section("application", "Application and scenario", facts([
    ["Application", `${s.app} (${s.variant} variant)`],
    ["Risk scenario", s.text],
    ["Taxonomy id", s.taxonomy_id],
    ["Prior failures fed in", s.previous_failures?.length ? s.previous_failures.join(", ") : "none"],
    ["Access level", `${r.access.visibility_levels.join(", ")} (${r.access.visibility_levels.map((l) => ACCESS[l] ?? l).join(", ")})`],
    ["Target", r.labels.target],
  ]), el("p", { class: "metric-read" }, r.access.note));
}

function riskSection(r) {
  const rows = r.risks.map((x) => [
    el("code", {}, x.risk_id), `${x.taxonomy_id} ${x.title}`, x.component,
    x.source === "user" ? tag("your scenario", "t-user") : tag("simulated analyst", "t-sim"),
    String(x.planned_tests),
  ]);
  const unplanned = r.plan.unplanned?.length
    ? el("p", { class: "notice" }, el("strong", {}, "Uncovered risks: "),
        `${r.plan.unplanned.length} risk(s) received no tests within the budget and are reported as uncovered.`)
    : null;
  return section("risks", "Risk register",
    el("p", {}, "Risks are validated against the OWASP LLM taxonomy and ranked by policy code; the simulated analyst only proposes."),
    table(["Risk", "Taxonomy", "Component", "Origin", "Planned tests"], rows), unplanned);
}

function generationSection(r) {
  const g = r.generation;
  const rows = g.tests.slice(0, 40).map((t) => [t.question, t.expected, el("code", {}, t.source_id), t.family]);
  const more = g.tests.length > 40 ? ` (first 40 of ${g.tests.length} shown)` : "";
  return section("generation", "Dynamic test generation",
    el("p", {}, `${g.drafted} tests drafted from the risk scenario and the application's own sources; ` +
      `${g.rejected_drafts} rejected by the verbatim-evidence gate; ${Object.keys(g.redundant).length} removed as redundant; ` +
      `${g.tests.length} executed. Drafts are proposals; only validated tests run.`),
    el("p", { class: "notice" }, "Generation is simulated (a deterministic stand-in that varies questions per risk, source and prior failure). It is not a real model."),
    el("details", {}, el("summary", {}, `Generated tests${more}`),
      table(["Question sent to the app", "Expected (source sentence)", "Source", "Author family"], rows)));
}

function executionSection(r) {
  const e = r.execution, c = e.consistency;
  return section("execution", "Test execution", facts([
    ["Test cases", String(e.cases)], ["Repeats per case", String(e.repeats)],
    ["Runs recorded", String(e.runs)], ["Runs with errors", String(e.errors)],
    ["Runs not executed", String(e.unrun)],
    ["Consistency", `${c.identical_across_repeats} of ${c.cases} cases gave identical output on every repeat`],
  ]), el("p", { class: "metric-read" },
    "The sandbox app is deterministic, so full consistency is expected here; this says nothing about a real model's variability."));
}

function metricsBlock(r, dims) {
  const out = document.createDocumentFragment();
  const ms = r.metrics.filter((m) => dims.includes(m.dimension));
  if (!ms.length) out.append(el("p", { class: "empty" }, "No checks of this kind ran for this application."));
  ms.forEach((m) => { out.append(metricRow(m)); const f = failureExamples(m); if (f) out.append(f); });
  return out;
}

function groundingSection(r) {
  const ran = el("p", { class: "metric-read" }, `Checks that ran: ${r.checks.ran.join(", ")}. `,
    "Only citation ids and numeric claims are verified; free-text hallucinations are not detected by this demo.");
  return section("grounding", "Grounding and hallucination results",
    metricsBlock(r, ["grounding", "accuracy & completeness"]), ran);
}

function attackSection(r) {
  const a = r.attacks;
  const cell = (x) => (x.breached ? tag(`breached @${x.first_success}`, "t-bad") : tag("held", "t-ok"));
  const rows = a.rows.map((x) => [el("code", {}, x.pair_id), SURFACE[x.surface] ?? x.surface, x.goal,
    cell(x.static_template), cell(x.adaptive_mutation)]);
  const asr = Object.entries(a.asr).map(([cls, v]) =>
    `${cls}: ${v.successes} of ${v.n_pairs} pairs breached within ${a.budget} attempts (95% interval ${pct(v.lower)} to ${pct(v.upper)})`);
  return section("security", "Adversarial security results",
    el("p", {}, "Outcomes are decided by deterministic oracles in the sandbox (canary at a sink, state change, forbidden tool call), never by a model saying \"blocked\"."),
    rows.length ? table(["Pair", "Surface", "Attacker goal", "Static template", "Adaptive mutation"], rows)
      : el("p", { class: "empty" }, "No attack pairs apply to this application."),
    ...asr.map((t) => el("p", { class: "metric-read" }, t)),
    el("p", { class: "metric-read" }, `Decision input: ${a.verdict_attacker}, budget ${a.budget}. Intervals ignore correlation between pairs.`),
    metricsBlock(r, ["security", "safety"]));
}

function taxonomySection(r) {
  const chips = Object.entries(r.failure_taxonomy).map(([k, n]) => tag(`${k}: ${n}`, "t-bad"));
  const rows = r.failures.map((f) => [f.question ?? f.case_id, el("code", {}, f.metric), f.location,
    f.rule ?? "unknown", (f.evidence ?? []).join(", ") || "-", f.substitution.replace("_", " ")]);
  return section("taxonomy", "Failure taxonomy with evidence",
    chips.length ? el("div", { class: "labels" }, ...chips) : el("p", { class: "empty" }, "No failures to classify."),
    rows.length ? table(["Test", "Metric", "Location", "Rule", "Evidence", "Context substitution"], rows) : null,
    el("p", { class: "metric-read" }, "Locations come from trace rules; \"unknown\" is a valid answer. Controlled substitution was not run."));
}

function scorecardSection(r) {
  const byDim = {};
  r.metrics.forEach((m) => { (byDim[m.dimension] ??= []).push(m); });
  const rows = Object.entries(byDim).flatMap(([dim, ms]) => ms.map((m) => [
    dim, el("code", {}, m.metric), m.failure_rate ? `${m.failure_rate.k} / ${m.failure_rate.n}` : "n/a",
    m.failure_rate ? `${pct(m.failure_rate.lower)} to ${pct(m.failure_rate.upper)}` : "n/a",
    m.appetite != null ? pct(m.appetite) : "none",
    tag(({ within: "within", above: "above", straddles: "straddles", no_appetite: "no appetite" })[m.status] ?? "n/a",
      m.status === "above" ? "t-bad" : m.status === "within" ? "t-ok" : "t-warn")]));
  return section("scorecard", "Quality and safety scorecard",
    el("p", {}, "One row per dimension and metric, with failure rates as exact intervals. There is deliberately no single composite score: a weighting would be an invented number."),
    table(["Dimension", "Metric", "Failed / evaluable", "95% interval", "Appetite", "Verdict"], rows));
}

function regressionSection(r) {
  const adm = r.regression.admitted;
  const rows = adm.map((c) => [c.original_question ?? c.minimized_from, c.minimized_input.input ?? JSON.stringify(c.minimized_input),
    el("code", {}, c.metric ?? "-"), `${c.reproduced[0]} / ${c.reproduced[1]}`, c.lineage.length > 1 ? `${c.lineage.length - 1} step(s)` : "none"]);
  const rej = r.regression.rejected.map((c) => el("li", {}, `${c.metric}: ${c.reason}`));
  const body = r.scenario.variant === "clean"
    ? el("p", { class: "empty" }, "Regression cases are built from the defective (seeded) version; this is the clean control.")
    : rows.length ? table(["Failing test", "Minimized test", "Metric", "Reproduced on defect", "Minimized"], rows)
    : el("p", { class: "empty" }, "No failures reproduced reliably enough to admit.");
  return section("regression", "Regression suite",
    el("p", {}, "Each failing test is minimized, then admitted only if it reproduces on the defective version and passes on the clean one. Admission parameters are demo values (flake rate 0 for the deterministic sandbox, alpha 0.05)."),
    body, rej.length ? el("ul", { class: "plain" }, ...rej) : null);
}

function whyList(r) {
  const ul = el("ul", { class: "plain" });
  r.metrics.filter((m) => m.failure_rate && r.pack.decision && m.appetite != null).forEach((m) => {
    const x = m.failure_rate;
    const verb = { within: "inside", above: "above", straddles: "straddling" }[m.status];
    ul.append(el("li", {}, `${m.metric}: ${x.k} of ${x.n} failed, interval ${pct(x.lower)} to ${pct(x.upper)}, ${verb} the appetite ${pct(m.appetite)}.`));
  });
  const names = r.metrics.map((m) => m.metric);
  (r.decision.conditions ?? [])
    .filter((c) => !c.startsWith("EXAMPLE policy") && !names.some((n) => c.startsWith(`${n}:`)))
    .forEach((c) => ul.append(el("li", {}, c)));
  return ul;
}

function recommendationSection(r) {
  const [cls, label] = STATE[r.decision.decision] ?? ["s-insufficient", r.decision.decision];
  return section("recommendation", "Release recommendation",
    el("p", { class: `lede ${cls}` }, label),
    el("p", {}, "Why (from the ledger, by the policy engine; the narrative adds nothing):"), whyList(r),
    el("p", { class: "metric-read" }, `${r.decision.evidence_ids.length} evidence record(s) support this decision. Small samples give wide intervals; this demonstration makes no claim of statistical validity.`));
}

function packSection(r) {
  const base = `/api/runs/${encodeURIComponent(r.id)}/pack`;
  return section("pack", "Evidence pack", facts([
    ["Ledger hash chain", r.ledger.verified ? "verified" : "FAILED"], ["Entries", String(r.ledger.entries)],
    ["Head", el("code", {}, r.ledger.head)],
    ["Download", el("span", {}, el("a", { href: `${base}?fmt=json`, download: `${r.id}-pack.json` }, "JSON"), " · ",
      el("a", { href: `${base}?fmt=md`, download: `${r.id}-pack.md` }, "Markdown"))],
  ]), el("p", { class: "metric-read" }, "The pack is regenerated from the ledger on every request and is byte-identical for the same ledger."));
}

function approvalSection(r, reload) {
  const rows = r.human_signoff.map((s) => el("li", {}, `${s.approved ? "Approved" : "Rejected"} by ${s.approver}${s.note ? `: ${s.note}` : ""}`));
  const status = el("p", { role: "status", class: "metric-read" });
  const form = el("form", { class: "form" });
  const name = el("input", { id: "approver", required: "", maxlength: "80", autocomplete: "name" });
  const note = el("input", { id: "so-note", maxlength: "500" });
  const send = (approved) => async () => {
    if (!name.value.trim()) { status.textContent = "Enter the reviewer's name."; name.focus(); return; }
    try {
      await api(`/api/runs/${encodeURIComponent(r.id)}/signoff`, { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ approver: name.value, approved, note: note.value }) });
      reload();
    } catch (e) { status.textContent = `Could not record: ${e.message}`; }
  };
  form.append(el("label", { for: "approver" }, "Reviewer name"), name, el("label", { for: "so-note" }, "Note (optional)"), note,
    el("div", { class: "row" }, el("button", { class: "btn", type: "button", onclick: send(true) }, "Record approval"),
      el("button", { class: "btn btn-quiet", type: "button", onclick: send(false) }, "Record rejection")), status);
  return section("approval", "Human approval",
    el("p", {}, "A human must approve any critical release decision. The sign-off is written to the ledger as a human-only event."),
    rows.length ? el("ul", { class: "plain" }, ...rows) : el("p", { class: "empty" }, "No sign-off recorded yet."), form);
}

async function monitoringSection() {
  const sec = section("monitoring", "Monitoring plan");
  try {
    const { markdown } = await api("/api/monitoring-plan");
    const pre = el("pre", { class: "plan" });
    pre.textContent = markdown;
    sec.append(el("p", { class: "metric-read" }, "A plan, not a running system. Nothing here has been measured."),
      el("details", {}, el("summary", {}, "Read the plan"), pre));
  } catch (e) { sec.append(el("p", { class: "error" }, `Could not load plan: ${e.message}`)); }
  return sec;
}

export async function renderReport(main, r, ctx) {
  main.replaceChildren(decisionBlock(r));
  const nav = el("nav", { class: "jump", "aria-label": "Sections" });
  [["application", "Application"], ["risks", "Risks"], ["generation", "Generation"], ["execution", "Execution"],
    ["grounding", "Grounding"], ["security", "Security"], ["taxonomy", "Failures"], ["scorecard", "Scorecard"],
    ["regression", "Regression"], ["recommendation", "Recommendation"], ["pack", "Evidence"],
    ["approval", "Approval"], ["monitoring", "Monitoring"]]
    .forEach(([id, t]) => nav.append(el("a", { href: `#${ctx.hashFor(id)}` , onclick: (e) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: "smooth" }); } }, t)));
  main.append(nav, scenarioSection(r), riskSection(r), generationSection(r), executionSection(r),
    groundingSection(r), attackSection(r), taxonomySection(r), scorecardSection(r), regressionSection(r),
    recommendationSection(r), packSection(r), approvalSection(r, ctx.reload), await monitoringSection());
  main.append(el("p", { class: "metric-read" }, "Not done in this demo: free-text hallucination judging, bias/toxicity checks, real-model runs, live monitoring."));
}
