# 16 — Architecture Candidates (three genuinely different options; **no selection made**)

Written after `02`–`15`. Each component is tagged for feasibility (`21` legend): **EP** existing proven · **OS** open-source available · **EI** engineering integration · **OR** original research · **SP** speculative.

The candidates differ in their *center of gravity*: A = observed evidence, B = adversarial search, C = an evidence ledger with independent adjudication.

---
## Candidate A — Instrumented Evaluation & Verification Platform (trace-centric)

**Thesis:** quality evidence comes from instrumentation; deterministic assertions and a verifier portfolio do most work; LLMs are used sparingly.

```mermaid
flowchart LR
  subgraph Target["Target app (sandbox)"]
    APP[LLM application]
    SDK[SDK / OTel exporter]
    TOOLS[Mock tool backends]
  end
  subgraph Integration
    GW[Optional gateway]
    COL[Trace collector]
  end
  subgraph Core["Evaluation core"]
    ORCH[Workflow orchestrator]
    AM[App-model builder]
    GEN[Test generator + validators]
    EXE[Executor]
    EVR[(Evidence store - append-only)]
    VER[Verification engine: deterministic -> NLI -> judge]
    DIA[Failure classifier / localizer]
    MET[Metrics + intervals]
    REG[Regression manager]
    POL[Policy engine]
  end
  HUM[Human review queue]
  REL[Release report]
  OBS[Platform observability]
  EXE --> APP
  APP --> SDK --> COL --> EVR
  GW -.-> COL
  TOOLS --- APP
  ORCH --> AM --> GEN --> EXE
  EVR --> VER --> DIA --> MET --> POL --> HUM --> REL
  DIA --> REG --> GEN
  ORCH --> OBS
  EVR --> REG
```
- **Strength:** reproducible, auditable, strong localization where instrumented. Evidence: structural testing (arXiv:2601.18827).
- **Weakness:** needs instrumentation (B/C); weak on unknown-unknown discovery; coverage bounded by what tests are written/generated.
- **Components:** collector (EP/OS: OTel), evidence store (EI), verifier portfolio (EI + OR for independence), localizer (EI for rules, OR for black-box).

---
## Candidate B — Autonomous Risk-Driven Adversarial Testing Platform (search-centric)

**Thesis:** discovery comes from agents that model the app, hypothesize failure modes, and search adaptively; verdicts come from outcome oracles in sandbox.

```mermaid
flowchart TB
  subgraph Sandbox["Isolated sandbox (egress-controlled, canary sinks)"]
    TARGET[Target app]
    ENV[Synthetic environment: data, tenants, tools]
  end
  PROBE[Capability prober]
  TM[Threat modeler - LLM, taxonomy-constrained]
  PL[Budgeted planner - bandit over risk cells]
  subgraph Attackers["Attacker agents (adaptive)"]
    ATK1[Injection / poisoning]
    ATK2[Tool-misuse / escalation]
    ATK3[Quality-stress: perturbation, multi-turn]
  end
  OUT[Outcome oracles: canary, state diff, forbidden-call]
  VAL[Finding validator: reproduce k times]
  LED[(Findings + lineage store)]
  REGS[Regression suite - minimized reproducible cases]
  HUM[Human triage]
  REPORT[Risk report + release recommendation]
  PROBE --> TM --> PL --> Attackers
  Attackers --> TARGET
  TARGET --- ENV
  TARGET --> OUT --> VAL --> LED --> HUM --> REPORT
  VAL --> REGS
  LED -->|feedback| PL
```
- **Strength:** best evidence for finding failures static suites miss (adaptive attack results, `10`).
- **Weakness:** cost and nondeterminism; metrics hard to compare run to run; quality (non-security) oracles weaker; needs environment synthesis for arbitrary apps (OR/SP).
- **Components:** attacker orchestration (OS: AJAR/PyRIT/Petri patterns), outcome oracles (EI), environment synthesis (**OR/SP**), minimizer (**OR**).

---
## Candidate C — Hybrid Quality-Engineering System with an Independent Evidence Ledger

**Thesis:** combine A's structure and B's discovery, but make *adjudication independence* an explicit subsystem: findings are not accepted until verified by a method-diverse portfolio under information isolation, with calibrated abstention to humans.

```mermaid
flowchart TB
  subgraph Access["Access negotiation"]
    NEG[Capability negotiation A..E]
  end
  subgraph Understand
    COLL[Deterministic collectors]
    APPM[App model + uncertainty]
    RISK[Risk register - policy-ranked]
  end
  subgraph Produce["Test production (two tiers)"]
    FROZEN[Frozen regression tier]
    DISC[Discovery tier - generators + attackers]
    TV[Test validity gate: source-of-truth oracle, sampled human audit]
  end
  EXE[Durable executor]
  LEDGER[(Evidence ledger: immutable, hashed, per-claim records)]
  subgraph Adjudicate["Independent adjudication (information-isolated)"]
    V1[Deterministic checks]
    V2[Entailment / small detectors]
    V3[Decision-model or LLM judges]
    V4[Outcome oracles]
    AGG[Aggregator: n_eff-aware, conformal abstention]
  end
  LOC[Localizer: substitution + trace rules]
  STAT[Estimators: judge-corrected, clustered CIs]
  POL[Policy engine: declared loss/risk appetite]
  HUM[Human adjudication + release sign-off]
  MON[Monitor: drift attribution, canaries]
  NEG --> COLL --> APPM --> RISK --> DISC
  FROZEN --> TV
  DISC --> TV --> EXE --> LEDGER
  LEDGER --> V1 & V2 & V3 & V4 --> AGG --> LEDGER
  LEDGER --> LOC --> STAT --> POL --> HUM
  AGG -->|disagree or low confidence| HUM
  HUM -->|validated failures| FROZEN
  MON --> RISK
  MON --> EXE
```
- **Strength:** addresses the two weakest links found in the literature: oracle independence and test validity. Natural place to record "unknown/insufficient evidence."
- **Weakness:** largest scope; several parts are OR (app model, independence measurement, localization); easiest to over-claim.
- **Components:** ledger (EI), diverse verifier portfolio (EI/OR), conformal abstention (OS techniques, EI), validity gate (OR), policy engine (EI).

---
## Cross-cutting design sections (apply to all three)

### B. Internal architecture notes
Orchestration as a **durable workflow** (resume after failure; idempotent steps; Temporal-style — engineering judgment). Sync: connect/discover/human review. Async: generation, execution, verification (queue-based, rate-limit-aware). Events: `TestExecuted`, `EvidenceRecorded`, `VerdictIssued`, `FindingConfirmed`, `DecisionProposed`. Retries: transport-level automatic; **verdict-level retries only with logged reason** (retry-until-pass is a bias).

### C. Multi-agent structure
Typed events via orchestrator; no free-form inter-agent chat; verifiers see claims+evidence pointers, never producer rationale; deterministic services for execution, estimation, policy, ledger (see `08`).

### D. Data architecture
Entities: `AppModel`, `Risk`, `TestCase{lineage, oracle_source, validity_status}`, `Run`, `Trace/Span`, `EvidenceRecord`, `Verdict{method, version, calibration_id}`, `Failure{type, location, localization_confidence}`, `RegressionCase{minimized, pass^k admission}`, `Decision{policy_version, evidence_ids, approver}`. Lineage: content-addressed IDs, append-only, signed timestamps; every report number traces to evidence IDs.

### E. Security architecture
Trust boundaries: platform ↔ sandbox ↔ target ↔ third parties. Secrets in vault, short-lived test credentials, synthetic data only, egress allowlist with canary sinks, per-run budgets and kill switch, repo content treated as untrusted input, judges isolated from attacker-controlled text where possible, full audit log.

### F. Scalability
Parallelism limited by provider rate limits and by *stateful* tests (isolated sandboxes per run); storage dominated by traces; cost control via cascade and deterministic-first funnels. No throughput numbers are claimed (not measured).

### G. Deployment
| Mode | Pros | Cons |
|---|---|---|
| Local | Data stays put; easy dev | Limited scale; reproducibility depends on user env |
| Containerized self-host | Reproducible; fits enterprise | Ops burden |
| Cloud SaaS | Easy scale, shared judge infra | Data exposure; many enterprises disallow |
| Hybrid (control plane cloud, data plane in customer VPC) | Balances | Complexity |

### H. Feasibility summary
| Component | A | B | C |
|---|---|---|---|
| Trace ingestion (OTel) | EP/OS | EI | EP/OS |
| Deterministic checks/assertions | EP | EP | EP |
| Verifier portfolio (NLI+judge) | OS/EI | EI | EI + **OR** (independence) |
| App-model extraction | EI/**OR** | **OR** | **OR** |
| Adaptive attackers | — | OS/EI | OS/EI |
| Env synthesis for arbitrary apps | — | **OR/SP** | **OR/SP** |
| Test validity gate | EI | EI | **OR** |
| Localization | EI (grey-box) | partial | EI + **OR** (black-box) |
| Conformal abstention/gates | EI | EI | EI |
| Drift attribution | EI/**OR** | — | **OR** |

No candidate is endorsed here; `19` and `22` list what must be learned to choose.
