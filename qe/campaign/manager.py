"""Campaign orchestration: a persisted, resumable, cancellable, budgeted state machine.

Stages (each records start/end, inputs hash, status, error; every transition is audited in the
campaign ledger): risk_definition -> test_plan -> execution -> verification -> classification ->
scoring -> comparison -> recommendation -> review (human).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

from qe.campaign import analysis, execute, plan, risks, store
from qe.campaign.models import STAGES, CampaignParams, TargetSpec
from qe.campaign.targets import ModelTarget, build_target
from qe.core.events import EventType, ProducerKind
from qe.core.ids import content_id
from qe.core.schemas import Policy, Signoff
from qe.ingest.target_config import TargetConfig
from qe.realeval.dataset import EvalItem, QuestionGenerator
from qe.realeval.generators import generator_from_env
from qe.realeval.resolver import ResolvedProject
from qe.realeval.target import RagTarget

_LOCK = threading.RLock()
_RUNNING: dict[str, threading.Event] = {}
RESUMABLE = ("interrupted", "cancelled", "failed")
PRIVATE = ("inputs_digest",)


class CampaignError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


def inputs_digest(project: ResolvedProject) -> str:
    return content_id([project.documents, project.qa_pairs, project.risk_flags,
                       project.canaries])


def _stage_template() -> dict[str, dict[str, Any]]:
    return {s: {"status": "pending", "started": None, "ended": None, "inputs_hash": None,
                "error": None, "detail": {}} for s in STAGES}


def create_record(cid: str, project: ResolvedProject, params: CampaignParams,
                  specs: list[TargetSpec]) -> dict[str, Any]:
    return {
        "id": cid, "name": params.name, "project_id": project.project_id, "state": "queued",
        "created": time.time(), "error": None, "incomplete": None,
        "params": params.public(), "targets": [s.model_dump(mode="json") for s in specs],
        "stages": _stage_template(), "progress": {"done": 0, "total": 0},
        "risks": [], "unmapped": [], "plan": None, "coverage": None, "results": {},
        "comparisons": None, "recommendation": None, "decisions": {}, "notes": [],
        "inputs_digest": inputs_digest(project)}


def load(cid: str) -> dict[str, Any] | None:
    with _LOCK:  # liveness first: a thread saves its final state BEFORE it deregisters
        live = cid in _RUNNING
    rec = store.load_raw(cid)
    if rec is None:
        return None
    if rec["state"] in ("queued", "running") and not live:
        rec = {**rec, "state": "interrupted",
               "error": "interrupted (process stopped); resumable"}
    return rec


def public(rec: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in rec.items() if k not in PRIVATE}
    out["resumable"] = rec["state"] in RESUMABLE
    return out


def list_all() -> list[dict[str, Any]]:
    out = []
    for cid in store.list_ids():
        rec = load(cid)
        if rec:
            out.append({"id": rec["id"], "name": rec["name"], "project_id": rec["project_id"],
                        "state": rec["state"], "progress": rec["progress"],
                        "targets": [t["label"] for t in rec["targets"]],
                        "created": rec["created"],
                        "better_target": (rec.get("recommendation") or {}).get("better_target")})
    return out


class _Run:
    """One execution of the pipeline for a campaign (initial run or a resume)."""

    def __init__(self, cid: str, project: ResolvedProject | None, params: CampaignParams,
                 specs: list[TargetSpec], cancel: threading.Event,
                 generator: QuestionGenerator | None, regression_items: list[EvalItem],
                 project_cfg: TargetConfig | None) -> None:
        self.cid, self._project, self.params, self.specs = cid, project, params, specs
        self._assembled: dict[str, dict[str, Any]] = {}
        self._cases: list[Mapping[str, Any]] = []
        self._runs: dict[str, dict[str, list[dict[str, Any]]]] = {}
        self.cancel, self.generator = cancel, generator
        self.regression_items, self.project_cfg = regression_items, project_cfg
        loaded = store.load_raw(cid)
        assert loaded is not None
        self.rec: dict[str, Any] = loaded

    @property
    def project(self) -> ResolvedProject:
        if self._project is None:
            raise RuntimeError("this run has no project (analysis-only recompute)")
        return self._project

    def note(self, text: str) -> None:
        if text not in self.rec["notes"]:
            self.rec["notes"].append(text)

    # -- persistence helpers -------------------------------------------------
    def save(self) -> None:
        with _LOCK:
            store.save(self.rec)

    def stage(self, name: str, fn: Callable[[], dict[str, Any]], inputs: Any) -> bool:
        """Run a stage unless already done. Returns False when the pipeline must stop."""
        st = self.rec["stages"][name]
        if st["status"] == "done":
            return True
        st.update(status="running", started=time.time(), ended=None, error=None,
                  inputs_hash=content_id(inputs))
        self.rec["state"] = "running"
        self.save()
        store.audit(self.cid, "stage_started", stage=name, inputs_hash=st["inputs_hash"])
        try:
            detail = fn()
        except Exception as exc:  # noqa: BLE001 - reported through the record
            st.update(status="failed", ended=time.time(), error=f"{type(exc).__name__}: {exc}")
            self.rec.update(state="failed", error=f"stage {name} failed: {exc}")
            self.save()
            store.audit(self.cid, "stage_failed", stage=name, error=type(exc).__name__)
            return False
        status = detail.pop("_status", "done")
        st.update(status=status, ended=time.time(), detail=detail)
        self.save()
        store.audit(self.cid, "stage_finished", stage=name, status=status)
        return bool(status == "done")

    # -- stages ----------------------------------------------------------------
    def risk_definition(self) -> dict[str, Any]:
        p, imported = self.project, self.params.imported_plan
        scenarios = [str(c.get("risk")) for c in (imported or {}).get("cases", [])
                     if isinstance(c, dict) and c.get("risk") in plan.SCENARIO_SET]
        reg = risks.build_register(
            risk_focus=self.params.risk_focus, risk_flags=p.risk_flags,
            has_qa=bool(p.qa_pairs), has_documents=bool(p.documents),
            include_security=self.params.include_security, imported_scenarios=scenarios)
        self.rec.update(risks=reg["risks"], unmapped=reg["unmapped"])
        return {"n_risks": len(reg["risks"]), "n_unmapped": len(reg["unmapped"]),
                "sources": sorted({s for r in reg["risks"] for s in r["sources"]})}

    def test_plan(self) -> dict[str, Any]:
        reg = {"risks": self.rec["risks"], "unmapped": self.rec["unmapped"]}
        n = len(self.specs)
        if self.params.imported_plan is not None:
            built = plan.adopt_import(self.project, self.params, reg, n)
        else:
            gen = self.generator if self.params.generate_with_llm else None
            built = plan.build_plan(self.project, self.params, reg, gen,
                                    self.regression_items, n)
        store.save_plan(self.cid, built)
        store.audit(self.cid, "plan_created", plan_id=built["plan_id"], source=built["source"],
                    cases=len(built["cases"]), authoring=built["authoring"]["mode"])
        self.rec.update(plan=plan_summary(built), coverage=built["coverage"],
                        notes=list(built["notes"]))
        if not built["cases"]:
            raise ValueError("the plan has no cases: supply Q&A pairs, documents or a plan")
        return {"plan_id": built["plan_id"], "n_cases": len(built["cases"])}

    def build_targets(self) -> dict[str, RagTarget]:
        out: dict[str, RagTarget] = {}
        for s in self.specs:
            t = build_target(s, self.project, self.project_cfg)
            if isinstance(t, ModelTarget) and t.truncated:
                self.note(f"target {s.label}: documents truncated for context stuffing "
                          "(bare-model baseline sees only the first part of the corpus)")
            out[s.label] = t
        return out

    def execution(self) -> dict[str, Any]:
        built = store.load_plan(self.cid)
        assert built is not None
        targets = self.build_targets()
        st = self.rec["stages"]["execution"]
        with store.ledger(self.cid) as lg:
            def progress(done: int, total: int) -> None:
                self.rec["progress"] = {"done": done, "total": total}
                self.save()

            outcome = execute.run_execution(
                items=built["cases"], repeats=built["repeats"], targets=targets, lg=lg,
                cancel=self.cancel, max_calls=self.params.max_calls,
                timeout_s=self.params.timeout_s, on_progress=progress)
        total = len(built["cases"]) * built["repeats"] * len(self.specs)
        self.rec["progress"] = {"done": outcome.calls_total, "total": total}
        detail: dict[str, Any] = {"calls": outcome.calls_total, "new_calls": outcome.calls_new,
                                  "total_calls": total, "state": outcome.state}
        st["detail"] = detail
        if outcome.state != "complete":
            self.rec["incomplete"] = outcome.reason
            detail["_status"] = "cancelled" if outcome.state == "cancelled" else "incomplete"
            detail["reason"] = outcome.reason
            store.audit(self.cid, "execution_stopped", reason=outcome.reason,
                        state=outcome.state)
        else:
            self.rec["incomplete"] = None
        return detail

    def _analysis_inputs(self) -> tuple[dict[str, Any], list[Mapping[str, Any]],
                                        dict[str, dict[str, list[dict[str, Any]]]], list[str]]:
        built = store.load_plan(self.cid)
        assert built is not None
        labels = [s.label for s in self.specs]
        with store.ledger(self.cid) as lg:
            runs, confirmed = execute.read_runs(lg)
        cases = analysis.common_items(built["cases"], labels, runs, built["repeats"])
        return built, cases, runs, confirmed

    def verification(self) -> dict[str, Any]:
        built, cases, runs, confirmed = self._analysis_inputs()
        excluded = len(built["cases"]) - len(cases)
        policy = self.params.policy
        assembled = {
            s.label: analysis.verify(built, cases, s.label, runs, policy,
                                     self.rec.get("incomplete"), confirmed)
            for s in self.specs}
        self._assembled = assembled
        self._cases, self._runs = cases, runs
        if excluded:
            self.note(f"{excluded} plan case(s) not answered by every target on every repeat "
                      "were excluded from all targets (paired, identical item set)")
        with store.ledger(self.cid) as lg:
            for label, res in assembled.items():
                store.append(lg, f"verify:{label}:{len(cases)}:{len(confirmed)}",
                             EventType.VERDICT_ISSUED,
                             {"kind": "campaign_verdicts", "target": label,
                              "n_items": len(res["items"]),
                              "passed": sum(1 for r in res["items"] if r["passed"] is True),
                              "failed": sum(1 for r in res["items"] if r["passed"] is False)})
        return {"n_cases_compared": len(cases), "excluded_cases": excluded}

    def _ensure_assembled(self) -> None:
        if not self._assembled:  # verification stage was skipped as done in an earlier run
            self.verification()

    def classification(self) -> dict[str, Any]:
        self._ensure_assembled()
        built = store.load_plan(self.cid)
        assert built is not None
        scen = {c["id"]: c["scenario"] for c in built["cases"]}
        for s in self.specs:
            res = self._assembled[s.label]
            self.rec["results"][s.label] = {
                "label": s.label, "kind": s.kind, "metadata": s.metadata,
                "failure_taxonomy": res["failure_taxonomy"],
                "per_risk": analysis.per_risk(res["items"], scen),
                "items": analysis.trim_items(res["items"], scen)}
        return {"classes": {s.label: sorted(self._assembled[s.label]["failure_taxonomy"])
                            for s in self.specs}}

    def scoring(self) -> dict[str, Any]:
        self._ensure_assembled()
        for s in self.specs:
            res = self._assembled[s.label]
            out = self.rec["results"][s.label]
            out.update(metrics=res["metrics"], scorecard=res["scorecard"],
                       decision=res["decision"], advisory=res["advisory"],
                       unchecked=res["unchecked"], sample=res["sample"],
                       performance=analysis.performance(self._runs.get(s.label, {}),
                                                        self._cases))
            self.rec["decisions"][s.label] = res["decision"]
        return {"targets_scored": len(self.specs)}

    def comparison(self) -> dict[str, Any]:
        self._ensure_assembled()
        if len(self.specs) < 2:
            self.rec["comparisons"] = {"alpha": self.params.alpha, "pairs": [],
                                       "family_size": 0, "multiplicity": "single target",
                                       "note": "a comparison needs at least two targets"}
            return {"pairs": 0}
        rows = {s.label: self._assembled[s.label]["items"] for s in self.specs}
        self.rec["comparisons"] = analysis.compare(rows, self.params.alpha)
        return {"pairs": len(self.rec["comparisons"]["pairs"])}

    def recommendation(self) -> dict[str, Any]:
        self.rec["recommendation"] = analysis.recommend(
            self.rec["results"], self.rec["comparisons"], self.rec.get("incomplete"))
        return {"better_target": self.rec["recommendation"]["better_target"]}

    def review(self) -> dict[str, Any]:
        signed = [lbl for lbl, r in self.rec["results"].items()
                  if (r["decision"] or {}).get("status") != "pending_review"]
        everything = len(signed) == len(self.rec["results"])
        return {"_status": "done" if everything else "awaiting_review",
                "awaiting": [s.label for s in self.specs if s.label not in signed]}

    # -- driver -------------------------------------------------------------
    def drive(self) -> None:
        pipeline: list[tuple[str, Callable[[], dict[str, Any]], Any]] = [
            ("risk_definition", self.risk_definition,
             [self.params.risk_focus, self.project.risk_flags, self.params.include_security]),
            ("test_plan", self.test_plan,
             [self.rec["inputs_digest"], self.params.seed, self.params.max_cases,
              self.params.repeats, self.params.generate_with_llm]),
            ("execution", self.execution, [self.params.max_calls, self.params.timeout_s]),
            ("verification", self.verification, [self.rec["progress"]]),
            ("classification", self.classification, []),
            ("scoring", self.scoring, []),
            ("comparison", self.comparison, [self.params.alpha]),
            ("recommendation", self.recommendation, []),
        ]
        for name, fn, inputs in pipeline:
            ok = self.stage(name, fn, inputs)
            if name == "execution" and not ok:
                if self.rec["stages"][name]["status"] == "failed":
                    return
                continue  # cancelled / incomplete: still score what exists, marked incomplete
            if not ok:
                return
        self.stage("review", self.review, [])
        self.finish()

    def analyze_only(self) -> None:
        """Recompute verification..review from the ledger (after a human confirmation)."""
        for name, fn in (("verification", self.verification), ("classification",
                         self.classification), ("scoring", self.scoring),
                         ("comparison", self.comparison),
                         ("recommendation", self.recommendation), ("review", self.review)):
            if not self.stage(name, fn, [time.time()]) and name != "review":
                return
        self.finish()

    def finish(self) -> None:
        stop = self.rec["stages"]["execution"]["status"]
        self.rec["state"] = ("cancelled" if stop == "cancelled" else
                             "failed" if stop == "incomplete" else "done")
        if self.rec["state"] == "failed":
            self.rec["error"] = self.rec["incomplete"]
        self.save()


def plan_summary(built: dict[str, Any]) -> dict[str, Any]:
    by_scenario: dict[str, int] = {}
    for c in built["cases"]:
        by_scenario[c["scenario"]] = by_scenario.get(c["scenario"], 0) + 1
    return {"plan_id": built["plan_id"], "source": built["source"], "seed": built["seed"],
            "repeats": built["repeats"], "n_cases": len(built["cases"]),
            "authoring": built["authoring"], "by_scenario": by_scenario,
            "n_risks": len(built["risks"]), "n_gaps": len(built["coverage"]["gaps"]),
            "require_citations": built["require_citations"]}


def _launch(run: _Run) -> None:
    cid = run.cid

    def work() -> None:
        try:
            run.drive()
        except Exception as exc:  # noqa: BLE001
            run.rec.update(state="failed", error=f"{type(exc).__name__}: {exc}")
            run.save()
            store.audit(cid, "campaign_failed", error=type(exc).__name__)
        except BaseException:  # process-level kill: leave the persisted state for resume
            return
        finally:
            with _LOCK:
                _RUNNING.pop(cid, None)

    threading.Thread(target=work, daemon=True, name=cid).start()


def start(project: ResolvedProject, params: CampaignParams, specs: list[TargetSpec],
          project_cfg: TargetConfig | None = None,
          regression_items: list[EvalItem] | None = None) -> dict[str, Any]:
    cid = store.new_id()
    store.campaign_dir(cid).mkdir(parents=True, exist_ok=True)
    rec = create_record(cid, project, params, specs)
    cancel = threading.Event()
    with _LOCK:
        _RUNNING[cid] = cancel
    store.save(rec)
    if params.imported_plan is not None:
        store.save_imported(cid, params.imported_plan)
    store.audit(cid, "campaign_created", project_id=project.project_id,
                targets=[s.label for s in specs], params=params.public())
    _launch(_Run(cid, project, params, specs, cancel,
                 generator_from_env() if params.generate_with_llm else None,
                 regression_items or [], project_cfg))
    return {"id": cid, "state": "queued"}


def resume(cid: str, project: ResolvedProject, project_cfg: TargetConfig | None = None,
           ) -> dict[str, Any]:
    rec = load(cid)
    if rec is None:
        raise CampaignError(404, "campaign not found")
    if rec["state"] not in RESUMABLE:
        raise CampaignError(409, f"campaign is {rec['state']}; only interrupted, cancelled or "
                                 "failed campaigns can be resumed")
    if inputs_digest(project) != rec["inputs_digest"]:
        raise CampaignError(409, "the project's documents/Q&A changed since this campaign "
                                 "started: resuming would mix evidence; start a new campaign")
    params = params_from_record(rec)
    imported = store.load_imported(cid)
    params.imported_plan = imported
    specs = [TargetSpec.model_validate(t) for t in rec["targets"]]
    for name in STAGES[2:]:  # execution onwards is recomputed from the ledger
        rec["stages"][name].update(status="pending", error=None)
    rec.update(state="queued", error=None, incomplete=None, results={}, decisions={},
               comparisons=None, recommendation=None)
    cancel = threading.Event()
    with _LOCK:
        if cid in _RUNNING:
            raise CampaignError(409, "campaign is already running")
        _RUNNING[cid] = cancel  # registered before the state is rewritten (see load())
    try:
        store.save(rec)
        store.audit(cid, "campaign_resumed")
        run = _Run(cid, project, params, specs, cancel, None, [], project_cfg)
    except Exception:
        with _LOCK:
            _RUNNING.pop(cid, None)
        raise
    _launch(run)
    return {"id": cid, "state": "queued"}


def params_from_record(rec: dict[str, Any]) -> CampaignParams:
    p = rec["params"]
    return CampaignParams(
        name=rec["name"], project_id=rec["project_id"], risk_focus=list(p["risk_focus"]),
        repeats=p["repeats"], max_cases=p["max_cases"], max_calls=p["max_calls"],
        timeout_s=p["timeout_s"], include_security=p["include_security"],
        generate_with_llm=p["generate_with_llm"], seed=p["seed"], alpha=p["alpha"],
        policy=Policy.model_validate(p["policy"]) if p.get("policy") else None,
        use_example_policy=p["use_example_policy"])


def cancel(cid: str) -> dict[str, Any] | None:
    rec = load(cid)
    if rec is None:
        return None
    with _LOCK:
        ev = _RUNNING.get(cid)
    if ev is not None:
        ev.set()
        store.audit(cid, "cancel_requested")
    return {"id": cid, "state": rec["state"] if ev is None else "cancelling"}


def wait(cid: str, timeout: float = 60.0) -> dict[str, Any]:
    """Test helper: block until the campaign leaves queued/running."""
    end = time.time() + timeout
    while time.time() < end:
        rec = load(cid)
        with _LOCK:
            live = cid in _RUNNING
        if rec and rec["state"] not in ("queued", "running") and not live:
            return rec
        time.sleep(0.02)
    raise TimeoutError(cid)


class SignoffError(Exception):
    pass


def signoff(cid: str, label: str, reviewer: str, decision: str, rationale: str,
            ) -> dict[str, Any]:
    with _LOCK:
        rec = load(cid)
        if rec is None or rec["state"] != "done":
            raise SignoffError("campaign is not finished (state must be done)")
        res = rec["results"].get(label)
        if res is None:
            raise KeyError(label)
        dec = res["decision"]
        if dec["status"] != "pending_review":
            raise SignoffError(f"decision for {label!r} already reviewed")
        approved = decision.lower() in ("approve", "approved")
        so = Signoff(decision_id=dec["decision_id"], approver=reviewer.strip(),
                     approved=approved, note=rationale)
        with store.ledger(cid) as lg:
            store.append(lg, f"signoff:{label}", EventType.SIGNOFF_RECORDED,
                         {**so.model_dump(mode="json"), "kind": "campaign_signoff",
                          "target": label}, ProducerKind.HUMAN, "human-reviewer")
        dec = {**dec, "status": "approved" if approved else "rejected",
               "signoff": {"reviewer": reviewer.strip(), "decision": decision.lower(),
                           "rationale": rationale}}
        res["decision"] = dec
        rec["decisions"][label] = dec
        pending = [lbl for lbl, r in rec["results"].items()
                   if r["decision"]["status"] == "pending_review"]
        rec["stages"]["review"].update(
            status="done" if not pending else "awaiting_review", ended=time.time(),
            detail={"awaiting": pending})
        store.save(rec)
        store.audit(cid, "signoff", target=label, reviewer=reviewer.strip(),
                    decision=decision.lower())
        return dec


def confirm_item(cid: str, item_id: str, reviewer: str) -> dict[str, Any]:
    """Human confirms an advisory (LLM-drafted) case; verdicts are recomputed from the ledger."""
    with _LOCK:
        rec = load(cid)
        built = store.load_plan(cid)
        if rec is None or built is None or rec["state"] != "done":
            raise SignoffError("campaign is not finished (state must be done)")
        case = next((c for c in built["cases"] if c["id"] == item_id), None)
        if case is None:
            raise KeyError(item_id)
        if not (case.get("lineage") or {}).get("advisory"):
            raise SignoffError("case is not advisory")
        if any(r["decision"]["status"] != "pending_review" for r in rec["results"].values()):
            raise SignoffError("a decision was already reviewed; start a new campaign")
        with store.ledger(cid) as lg:
            store.append(lg, f"confirm:{item_id}", EventType.SIGNOFF_RECORDED,
                         {"kind": "item_confirmation", "item_id": item_id,
                          "reviewer": reviewer.strip()}, ProducerKind.HUMAN, "human-reviewer")
        store.audit(cid, "item_confirmed", item_id=item_id, reviewer=reviewer.strip())
        for name in STAGES[3:]:
            rec["stages"][name].update(status="pending", error=None)
        rec.update(results={}, decisions={}, comparisons=None, recommendation=None)
        store.save(rec)
        specs = [TargetSpec.model_validate(t) for t in rec["targets"]]
        run = _Run(cid, None, params_from_record(rec), specs, threading.Event(), None, [], None)
        run.analyze_only()
        return {"id": cid, "item_id": item_id}
