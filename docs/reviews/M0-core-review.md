# M0 core adversarial review

Reviewer: independent subagent (no implementer context). Scope: qe/core/{ids,events,ledger,schemas,telemetry}.py,
qe/ports/__init__.py, qe/exec/{egress,sandbox}.py, qe/testing/fakes.py, tests/{unit,property,adversarial}.
Baseline: `python -m uv run pytest -q` -> `37 passed in 1.83s`. Windows 11, CPython 3.12 (default asyncio loop = ProactorEventLoop).
Method: throwaway attack scripts plus 75 mutations, all run on a COPY of the repo in the scratchpad (real repo untouched).
Scripts (outside the repo): scratchpad/a1.py, a1p.py, a2.py, a3.py, a4.py, mut.py.

Verdict: REQUEST CHANGES. 2 CRITICAL, 5 HIGH, 7 MEDIUM, 4 LOW. 35 of 75 mutants survived.

## What held up (ran and could not break)
- Concurrency: 8 threads x 50 appends -> 400 rows, 0 errors, verify ok. 6 processes x 40 appends on one file -> 240 rows, 0 errors, verify ok (BEGIN IMMEDIATE + WAL works).
- Payload edits, row deletion and recomputed-row-hash edits are detected by verify().
- Non-finite floats are rejected in canonical_json; 1 vs 1.0 and 0.0 vs -0.0 get distinct IDs.
- Fail-safe on a bad producer_kind: model_construct with a plain str kind is rejected (`is not` check).
- Egress: socket.socket subclass, connect_ex, IPv6 connect, UDP connect, urllib, fromfd were all blocked (synchronous paths).
- The `seq|prev|event_json` delimiter is not ambiguous in practice (prev is chain-checked, event_json starts with `{`); no collision found.

## CRITICAL

### C1. Egress guard is bypassed by asyncio on Windows (the default loop) - R6/R7
Repro (scratchpad/a4.py): loop created before the guard, then `with EgressGuard()` inside a coroutine:
```
sock_connect NOT BLOCKED
create_connection NOT BLOCKED
loop ProactorEventLoop server hits 2 attempts []
```
Proactor connects via ConnectEx in `_overlapped`, never `socket.socket.connect`. A connection to a non-allowlisted loopback sink was really made and `attempts` stayed empty (the guard also fails to report it). LocalSandbox is async-only, so its main use path is the bypassed one. The tests pass only because they use synchronous `socket.create_connection`.
Other gaps in the same file (a3.py): `_socket.socket().connect` bypasses (server hit); subprocess unguarded (documented; server hit); `socket.getnameinfo` and UDP `sendto` unguarded; `gethostbyname/_ex` reach the real resolver without a recorded attempt (DNS exfil channel).
Fix: do not make a security claim from monkeypatching. Either enforce at OS/container level (M4) and label LocalSandbox "best effort, tests only" with a fail-closed default, or add `sys.addaudithook` coverage (socket.connect/sendto/getaddrinfo/gethostbyname; verify it fires for ConnectEx) plus tests under both Selector and Proactor loops.

### C2. Ledger `key` column is not covered by the hash; tamper passes verify() - R3/R10
Repro (a1.py A): `UPDATE ledger SET key='zzz' WHERE seq=1` gives
```
verify: ok=True checked=3 ; find_by_key('k1'): None ; re-append k1 -> new seq 3 len 4 verify True
```
Idempotency is silently defeated and duplicate evidence is appended with a "valid" chain. verify() never checks that the `key` column equals the key inside event_json (which IS hashed), nor that event_json parses.
Fix: in verify(), parse every event_json, assert row key == event.key, and run the permission check (see H1). Add a test that edits the key column.

## HIGH

### H1. verify() does not enforce R3 on stored rows
Repro (a1.py B): an LLM_AGENT EVIDENCE_RECORDED row inserted by raw SQL with a correct chain -> `verify: ok=True checked=2`. There is also no keyed MAC: anyone with file write access can rewrite the whole chain; the only defence is an external anchor, and M0 neither stores nor requires one.
Fix: verify() re-validates each row (schema + permission); emit an anchor (head+len) when a run closes; consider HMAC with a key held by the deterministic services.

### H2. R3 is self-attested: producer_kind is whatever the caller says
Repro (a1.py D): `Event(type=DECISION_ISSUED, producer="llm-author-agent", producer_kind=DETERMINISTIC)` appends at seq 0; a SIGNOFF with producer_kind=HUMAN from an "llm" producer also appends. Tests only prove honest labels are checked.
Fix: bind kind to the writer (e.g. `LedgerWriter(kind=...)` capability handed to each component and the ledger stamps/compares it), or document this as an unenforced trust boundary.

### H3. Unvalidated Event (model_construct / model_copy) can poison the ledger and brick reads
Repro (a1.py C): `Event.model_construct(key="x", type="bogus_type", producer="p", producer_kind=LLM_AGENT, payload={})` appends (unknown types are in neither permission set, so they pass). Afterwards `entries()` raises ValidationError while `verify()` still says ok. One bad write crashes every reader (replay, reports).
Fix: re-validate in append (`Event.model_validate(event.model_dump())`) and make check_write_permission default-deny: an explicit allowlist for LLM_AGENT rather than denylists for the others.

### H4. VerifierInput isolation (R4) is bypassed by a subclass of Claim/EvidenceRef
Repro (a2.py 1):
```
class Leaky(Claim): rationale: str
VerifierInput(claim=Leaky(claim_id="c", text="t", rationale="producer says it is fine"), ...).claim.rationale
```
returns the rationale. Pydantic keeps subclass instances as-is (revalidate_instances="never"), so top-level `extra="forbid"` is moot; the test only tries top-level extra kwargs. (model_construct extras are dropped; that path is fine.) Also `Claim.run_id`, `claim_id`, `source_id`, `evidence_text` are unbounded free strings (covert channels are inherent) and `run_id` lets a verifier fetch the run record.
Fix: `revalidate_instances="always"` (or an exact-type validator) on VerifierInput; drop or justify `run_id`; cap lengths; add a subclass test.

### H5. Concurrent or nested sandbox sessions break the egress guard in both directions
Repro (a3.py): enter A, enter B, exit A, then connect to a non-allowlisted host:
```
after A exit while B active: NOT BLOCKED
LEAK: guard permanently installed after both exited
```
Same result with two overlapping LocalSandbox sessions via asyncio.gather ("post: LEAK still patched"). Each guard restores the originals it captured, not the current state. The patch is process-global, so per-session allowlists cannot differ.
Fix: one process-wide manager with a refcounted stack of allowlists, restore only at depth 0; add an overlapping-session test.

## MEDIUM
- M1 Budget bypass: `charge(calls=-1000, tokens=-1000)` followed by 50 normal `charge()` all succeed with `max_calls=1` (a3.py). SandboxLimits accepts negative limits. check-then-add is unlocked (overrun under threads); kill() does not touch the guard. Fix: NonNegativeInt, reject negative charges, lock.
- M2 Hostname allowlist unusable: `EgressGuard(("localhost",))` permits getaddrinfo, then blocks the connect to the resolved 127.0.0.1. Creating a new event loop inside a guard raises EgressBlockedError (self-pipe socketpair connects to 127.0.0.1). Fix: allowlist resolved addresses; always permit loopback socketpairs; test it.
- M3 Frozen models are shallowly immutable: TestCase.input, Span.attributes, RunRecord.request/response/versions, Policy.loss_matrix are mutable dicts; mutating changes cid() (a2.py 8, "cid changed: True") and the models are unhashable. Fix: deep-freeze, or compute the cid at construction.
- M4 cid() is lossy: bytes vs str and tuple vs list collapse to the same ID, sets are silently listified (a2.py 9). `dict[str, Any]` is not a JSON type. Fix: a recursive JSON alias validated in the model.
- M5 Decision validators are bypassable and shallow: `DecisionRecord(INSUFFICIENT_EVIDENCE...).model_copy(update={"decision": RELEASE})` yields RELEASE with no evidence (a2.py 7d); model_construct likewise (7e). Accepted by the validator: RELEASE with `evidence_ids=("",)`, with uncovered_risks, with empty policy_version; CONDITIONAL with no conditions; REJECT with no evidence (7, 7b, 7c). Fix: override model_copy to revalidate, add min_length on ids, require conditions for CONDITIONAL; state that required_evidence/R9 checks live in the decision service.
- M6 Numeric holes: `Verdict.score` NaN/inf is accepted at construction and only cid() raises later; `AdjudicatedVerdict.confidence=7.5`, `n_eff=-3`, Policy NaN or negative losses, `RegressionCase.pass_k_admission=(5,2)` are all accepted. Fix: allow_inf_nan=False and Field(ge=, le=) bounds.
- M7 Telemetry: enforced only as a side effect of the first `import qe`; nothing re-asserts before an optional dependency reads its flag, and no test imports a dependency (deepeval/ragas are not installed in M0). Other common opt-outs (e.g. OTEL_SDK_DISABLED) are not covered. The first telemetry test is true by construction after `import qe`. Fix: enforce again at CLI entry and before each optional-extra import; add a test that imports the extras when present.

## LOW
- L1 A lone surrogate in a payload ("\ud800") raises UnicodeEncodeError (not ValueError/TypeError) inside append; fail-safe (rolled back, a1.py E) but the exception type is surprising. Deep or cyclic payloads raise RecursionError.
- L2 append returns the caller's mutable Event: mutating its payload afterwards changes the returned Entry, while the ledger copy stays correct (a1.py F).
- L3 `isinstance(FakeSubstringVerifier(), JudgePort)` is True (runtime_checkable only checks attribute presence; `model=None` passes), so the contract test cannot tell a judge from a non-model verifier. R4 family independence has no code or test in M0.
- L4 SQLiteLedger has no context manager; use after close() raises a raw sqlite3 error.

## Test quality: surviving mutants (35 of 75)
Behaviour the suite does not pin:
- Permission matrix: 7 of 10 DETERMINISTIC_ONLY types can be dropped with no failure (ADJUDICATED, ESTIMATE_COMPUTED, RUN_RECORDED, TRACE_RECORDED, CAPABILITY_INVENTORY, FAILURE_RECORDED, MISSING_EVIDENCE). Only EVIDENCE/VERDICT/DECISION are tested. Fix: parametrize EventType x ProducerKind against an explicit expected table.
- verify(): ignoring expected_len alone, expected_head alone, the seq-gap check, and "hash omits seq" all survive.
- append(): removing ROLLBACK and changing BEGIN IMMEDIATE to BEGIN survive (no concurrency or failure-injection test exists in the repo; I ran them only ad hoc).
- Egress: unpatching `connect` entirely survives (tests are caught by getaddrinfo first); unpatching connect_ex survives; not restoring connect_ex on exit survives; a hard-coded backdoor host survives; removing the IPv6 branch survives.
- Sandbox: token budget ignored, and tokens never counted, both survive (LocalSandbox test never charges tokens).
- Telemetry: dropping DEEPEVAL_TELEMETRY_OPT_OUT or DO_NOT_TRACK, or flipping the DEEPEVAL/HF values, survives. Tests compare against REQUIRED_FLAGS itself (circular) rather than hard-coding the R7 flags (`DEEPEVAL_TELEMETRY_OPT_OUT=1`, `RAGAS_DO_NOT_TRACK=true`).
- Schemas: Event frozen/extra=forbid, Frozen frozen/extra=forbid, VerifierInput frozen, empty-key rejection, non-str dict keys, ensure_ascii all survive.
- Fakes: FakeGenerator ignoring the seed survives.
Weak or vacuous tests: `test_egress_guard_restores_socket_functions` only covers the connect/getaddrinfo pair (not connect_ex); the first telemetry test is true by construction; the isinstance contract checks are attribute-only (L3).

## Suggested order before the M0 gate
1. C2, H1, H3: strengthen verify() and append (small, high value).
2. C1, H5: decide whether to downgrade the egress claim or enforce properly; add Proactor and overlapping-session tests.
3. H2, H4, M1.
4. Kill the survivors with a table-driven permission test and token/IPv6/connect_ex/anchor tests.

Not reviewed: sandbox_apps/. No repo file was modified other than writing this report.
