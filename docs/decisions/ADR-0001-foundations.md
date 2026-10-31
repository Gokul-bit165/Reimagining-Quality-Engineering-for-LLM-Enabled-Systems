# ADR-0001: Foundations (stack, ledger, write permissions)

Status: accepted (M0). Date: 2026-10-31.

- **Stack:** Python 3.12 (provisioned via uv; system has 3.13), Pydantic v2, SQLite WAL ledger behind a `Ledger` protocol, pytest + hypothesis, ruff, mypy --strict.
- **Ledger:** append-only, hash-chained (`SHA-256(seq|prev|canonical_event_json)`), idempotent by event `key`, same key with different content raises `ConflictError`. The chain detects edits, deletions and reordering. **Tail truncation is only detectable with an external anchor** (head hash + length) passed to `verify()`; this is a documented limit.
- **R3 reconciliation:** research/24 lets crew agents "write typed events". Resolved by splitting event types: evidence/decision types are `DETERMINISTIC_ONLY`; proposal/draft types (risk, test draft, attack attempt, validity verdict, narrative) may come from `LLM_AGENT`; sign-off is `HUMAN` only. Enforced in `Ledger.append`. LLM judge verdicts are recorded by the deterministic verifier service that wraps the model call, with model/version in the payload.
- **Verifier isolation (R4):** `VerifierInput` has `extra="forbid"` and no field for producer rationale or other verdicts.
- **Egress guard:** `EgressGuard` patches Python sockets in-process only. It does not contain subprocesses or native code. Container-level egress control is deferred to M4.
- **Providers:** Groq and OpenRouter (user choice). Keys only from env vars (`GROQ_API_KEY`, `OPENROUTER_API_KEY`) or a gitignored `.env`. Spend budget not yet set; real-model calls are blocked until it is.
- **Open item:** "NCM = nonconformity measure" is assumed but not confirmed by the user.
- **Process note:** the sandbox apps (T0.3) are authored by a separate subagent with no access to `qe/` internals so the defect manifests stay independent of the verifiers.

## Addendum: M0 adversarial review (docs/reviews/M0-core-review.md)
Fixed, each with a regression test in `tests/adversarial/test_review_fixes.py`: C2 (key column now verified against the hashed event), H1 (stored rows re-checked against write permissions in `verify()`), H2 (optional `producer_kinds` registry pins producer name to kind), H3 (events re-validated on append), H4 (`VerifierInput` accepts only the exact `Claim`/`EvidenceRef` types), C1/H5 (egress guard now covers asyncio incl. Proactor `sock_connect`, UDP `sendto`, resolver functions; patches are reference-counted so overlapping guards are safe), negative budget charges and limits, schema bounds (NaN/inf, confidence range, `pass_k_admission`, `DecisionRecord` consistency).

**Known limits that remain (not fixed, stated plainly):**
- No MAC/signature on the ledger. Someone with write access to the SQLite file can forge a *consistent* chain from some point on. Mitigation is an external anchor (head hash + length) pinned outside the DB; nothing pins it automatically yet.
- Without a `producer_kinds` registry, `producer_kind` is self-declared. Orchestrator code must construct the ledger with a registry.
- `EgressGuard` is in-process only: subprocesses, native code and pre-captured `_socket` references are not covered. Hostname allowlists are not supported (use IPs).
- Frozen models hold mutable dicts; `model_copy(update=...)` skips validators. Ledger writes re-validate, so this cannot reach the ledger, but in-memory objects can be mutated.
- R4 family independence (judge family != author family) has no enforcement code yet; planned for M3 aggregator.
