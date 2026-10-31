# sandbox_apps

Four small applications that act as the **system under test** for the verification platform. They are
authored independently of `qe/` (nothing here imports it). Each app has a `clean` (defect-free
control) and a `seeded` (injected defects) variant. `sandbox_apps/<app>/defects.yaml` is the ground
truth; `probes.yaml` maps each defect id to a request sequence that triggers it.

Apps: `chatbot` (Acme Cloud support bot), `rag` (Orbital Logistics KB assistant, BM25 over 20
synthetic docs), `multiagent` (planner / researcher / writer with shared memory), `toolagent`
(office assistant with notes, records, email and HTTP tools over a fake datastore).

## Contract (identical for all apps)

```python
from sandbox_apps.rag import build_app

app = build_app(variant="seeded", llm=None, seed=0, drift=False)  # ValueError unless clean|seeded
resp = app.invoke({"input": "...", "session_id": "s1", "user": "alice", "want_trace": True})
```

Response: `{"output", "citations": [ids], "citation_details"? (rag), "trace"? , "meta"}`.

* `meta` = `app, variant, model, prompt_version, trace_visibility ("full"|"none"), seed`.
* `want_trace: false` omits `trace` (black-box mode); default is grey-box.
* Trace events: `retrieval` (doc ids, chunk ids, scores, doc version/hash, corpus version),
  `tool_call` (tool, args, status ok|denied|error, actor), `llm_call` (role, model, prompt_version,
  prompt hash), `handoff` (from, to, reason), `memory_read`, `memory_write`.
* `invoke` is in-process and deterministic given `(variant, seed, llm responses, request, call history)`.
  Apps keep session/memory state between calls on one instance; build a fresh app per scenario.
* `app.snapshot_state()` returns a JSON-able dict; `app.sinks()` returns recorded sink events (toolagent:
  `{"sink": "email"|"http", ...}`; others `[]`). Toolagent state holds `CANARY-<hex>` tokens (seed-derived)
  in a private note and in an admin-only vault record.
* `rag` also has `corpus_manifest()` (source of truth: ids, versions, hashes, text) and
  `ingest_document()`; `multiagent` publishes `ALLOWED_TRANSITIONS`.
* `drift=True`: model `*-1 -> *-2` and `prompt_version v1 -> v2`. Only `chatbot/seeded` changes behaviour (CHAT-005);
  on every `clean` app the flag changes labels only.
* Optional HTTP: `python -m sandbox_apps.<app> --variant seeded --port 8765` (binds `127.0.0.1` only;
  `POST /invoke`, `GET /health`; `make_server` rejects any other host).

## LLM clients (`_common/llm.py`)

* `LLMClient` Protocol: `complete(messages, **kw) -> str`.
* `FakeLLM`: rule/template engine, role chosen by a `ROLE: x` system line, `pick()` keyed by a prompt hash,
  optional `script` (keyword -> reply) and `misbehave` flags (`fabricate`, `follow_injection`,
  `fabricate_success`). Seeded defects mostly arise because the seeded prompt omits a guard sentence, so
  the naive FakeLLM misbehaves; the flags can force the same on a clean app.
* `OpenAICompatibleLLM(base_url, model, api_key_env="GROQ_API_KEY")`: stdlib `urllib` only, key read from
  the env var at call time, never logged or put in errors, never instantiated by apps or tests. Opt-in only.

## Defect manifest schema

`app, version, author_note ("authored independently of qe/"), defects[]` with per defect:
`id, class, app, variant: seeded, location, trigger, trigger_rate_note (always|common|rare),
severity (low|medium|high|critical), expected_observable, required_visibility (blackbox|trace|state),
held_out_family (bool), description`. Held-out: CHAT-005, RAG-006, RAG-008, MA-002, TOOL-002 (keep hidden
from platform development). Low-trigger-rate (`rare`): CHAT-002, CHAT-007, RAG-002, RAG-007, MA-002, MA-003,
TOOL-005, TOOL-006.

## Coverage (generated)

Regenerate with `python -m uv run python -m sandbox_apps._common.coverage_table`. Output at time of writing:

| defect class | chatbot | rag | multiagent | toolagent |
|---|---|---|---|---|
| fabricated_claims | CHAT-001 | RAG-001 | MA-001 | TOOL-005 |
| invalid_citations | - | RAG-002, RAG-003 | - | - |
| contradictions | CHAT-002 | - | - | - |
| retrieval_failures | - | RAG-004, RAG-005, RAG-006, RAG-007 | - | - |
| prompt_injection_susceptibility | CHAT-003 | RAG-008 | - | TOOL-002 |
| unauthorized_tool_attempts | - | - | - | TOOL-001, TOOL-006 |
| memory_contamination | CHAT-004 | - | MA-004 | TOOL-003 |
| wrong_agent_transitions | - | - | MA-002 | - |
| incomplete_task_execution | CHAT-006, CHAT-007 | - | MA-003 | TOOL-004 |
| model_prompt_drift | CHAT-005 | - | - | - |
| **total defects** | 7 | 8 | 4 | 6 |

## Tests

`python -m uv run pytest tests/integration -q` runs, per app: determinism, clean-variant-has-no-defect,
seeded-defect-triggerable (check functions live in the test files, separate from any `qe` verifier),
plus manifest schema, class coverage, no-network (`socket.connect` patched to raise), loopback HTTP.

## Known limits

FakeLLM is a template engine: defects are far more regular and easier to detect than real-model failures
(use the natural-defect track and real LLMs, opt-in, for realism). Probes are known-good triggers, so
detection rates measured on them are optimistic for the common-rate defects.
