# 05 — Deep Testing Methods for LLM Applications

Evidence tags as in README. "Adaptation" lines are **our proposals** (hypotheses) unless a citation is given.

## A. Testing levels
| Level | LLM-app interpretation | Evidence |
|---|---|---|
| Unit | Single prompt template/parser/tool with mocked LLM — deterministic | Kohl et al. arXiv:2601.18827 (mocking to force reproducible behavior) ✔S |
| Component | Retriever alone (recall@k vs labelled evidence), reranker, guardrail, memory module | RAG-X decouples retrieval/generation (arXiv:2603.03541) ✔S |
| Integration/API | Contract tests: schemas, error codes, tool arguments | engineering practice (no specific cite) |
| E2E / system | Task completion with simulated users | τ-bench ✔S |
| Architecture-level | Trace-structure invariants (which components ran, in what order) | arXiv:2601.18827 ✔S |
| Multi-agent workflow | Handoff/transition correctness | Gap — little verified |
| Security | Adaptive adversarial with outcome assertions | `10` |
| Performance/load | Latency, token cost, rate-limit behavior | standard; LLM-specific literature not reviewed |
| Reliability | pass^k, perturbation, fault injection | τ-bench; ReliabilityBench arXiv:2601.06112 ✔S |
| Production regression | Replay/shadow traffic; canaries | practitioner sources only (◐2) |

## B. Technique-by-technique

| Technique | Adaptation to LLM apps | Finds *new* failures? | Status |
|---|---|---|---|
| **Property-based** | State invariants as predicates over output+trace ("every cited ID exists in corpus"; "no PII pattern in output"); generator = LLM or grammar | Yes, if generators explore input space | Proposal; no LLM-app paper verified |
| **Metamorphic** | Relations among runs: paraphrase invariance, irrelevant-context invariance, synonym/antonym entailment (MetaRAG), corpus update/OCR-noise relations | Yes — no oracle needed | Established-ish: survey arXiv:2605.13898 ✔S; MetaRAG arXiv:2509.09360 ✔S |
| **Differential** | Same input across model versions / prompts / retrievers; disagreement = suspect | Yes (drift, regressions) | Proposal; supports model-replacement testing |
| **Mutation** | Mutate prompt template, retrieval corpus, tool descriptions to see whether *the test suite* detects it (suite adequacy) | Measures suite quality | **Not searched**; hypothesis |
| **Stateful / model-based** | Model the app as a state machine from traces; walk it | Yes | Needs extracted model (see `06`) |
| **Combinatorial** | Cover pairwise combos of (intent × document type × user role × tool availability) | Systematic | Proposal; classic technique |
| **Coverage-guided fuzzing** | Feedback = new trace paths / retrieved-chunk coverage / tool sequences, not code coverage | Yes | LeCov (neuron-level, white-box) arXiv:2408.10474 ✔S; "Chunk Coverage" for RAG appeared only as a seminar abstract (USI, 30 Apr 2026; speaker J. Kim) ✔S — paper not verified |
| **Grammar-based fuzzing** | Grammars over tool-call argument schemas, structured inputs, document formats | Yes for parsers/tools | Proposal |
| **Fault injection / chaos** | Tool timeouts, malformed tool outputs, retrieval empty/stale, provider 429/5xx | Yes | ReliabilityBench λ-axis ✔S |
| **Boundary-value** | Context-window limits, empty/very long inputs, top-k edges | Yes | Proposal |
| **Temporal consistency** | Same query across time/versions; stale-knowledge probes | Yes | Proposal |
| **Multi-turn** | Persona-driven simulated users; long-horizon | Yes | τ-bench; AJAR for adversarial multi-turn ✔S |
| **Workflow-invariant** | Assertions on traces (order, presence, forbidden calls) | Detects known invariant breaks | arXiv:2601.18827 ✔S |
| **Dependency-failure / model replacement** | Swap/disable components; observe degradation | Yes | Proposal; ties to drift attribution |

## C. Honest limits
- Techniques that need **internals** (neuron coverage, logits, attention) are unavailable for API-hosted models; coverage must be defined over *observable* artifacts (retrieved chunks, tool events, spans).
- Metamorphic relations must be **valid**; a wrong relation produces false failures. Each relation needs its own validity check (e.g., human-verified sample) — otherwise it is another unvalidated oracle.
- "Discovers previously unknown failures" is the central unproven claim; the only method-agnostic evidence is that adaptive attack search finds failures static suites miss (`10`). For quality (non-security) failures, direct evidence is thin in what I read.
