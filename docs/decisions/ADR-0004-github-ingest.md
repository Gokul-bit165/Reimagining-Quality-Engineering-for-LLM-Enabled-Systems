# ADR-0004: Bring-your-own-app ingest (GitHub URL / zip) and supersession of the gate flow

Date: 2026-10-31. Status: accepted.

## Context
The product pivots from synthetic demo apps to testing the user's own RAG app. Users give a GitHub URL (or a zip); the platform clones it, analyses it statically and exposes it as a test target. This means handling untrusted code and untrusted URLs.

## Decision on process
CLAUDE.md says "stop at each milestone gate and wait for approval". The user is the product owner and explicitly asked to ship this pivot without stopping at gates, so that flow is superseded for this work only. All other rules (R1-R12) still apply: honest claims, deterministic decisions, INSUFFICIENT_EVIDENCE as a valid outcome, no secrets in logs or disk.

## Threat model
Assets: the host machine, host secrets (provider keys, GITHUB_TOKEN), other users' projects, third-party systems.
Attackers: a malicious repo/zip, a malicious URL or endpoint supplied through the API, a user pointing the platform at systems they do not own.

| Threat | Mitigation |
|---|---|
| Option/URL injection into git | Strict allowlist `https://github.com/<owner>/<repo>[.git][/tree/<branch>/<subdir>]`; owner/repo/branch/subdir regexes; no credentials, ports, query, `%`, `\`, leading `-`, `..`. Clone uses an argument list (never a shell) and `--` before the URL. |
| Malicious git config / hooks / protocols | `core.hooksPath=<devnull>`, `protocol.file.allow=never`, `protocol.allow=never` (https only), `GIT_ALLOW_PROTOCOL=https`, `GIT_CONFIG_NOSYSTEM`, empty global config, no submodules, `core.symlinks=false`, `credential.helper=` empty, `GIT_TERMINAL_PROMPT=0`. |
| Resource exhaustion | Clone timeout, repo byte and file-count caps (checked after clone; oversized workspace is deleted), analyser file-size and file-count caps, max 100 projects, max 2 concurrent jobs. |
| Symlink / junction escape | After clone or unzip every symlink and junction is deleted; `.git` is removed; analyser and suggestion code additionally skip links and verify resolved paths stay inside the workspace. |
| Zip-slip, symlink entries, zip bombs | Member names normalised and rejected if absolute, drive-lettered or containing `..`; resolved target must stay in the workspace; symlink entries rejected; declared and actual (streamed) expanded sizes capped; 50 MiB upload cap. |
| Repo code executing on host | Analyser is regex-only: no import, eval, exec or shell. Execution happens only in (a) the user's own deployed endpoint, or (b) a Docker container: `--network none`, `--read-only`, `--cap-drop ALL`, `no-new-privileges`, non-root uid, memory/CPU/pids limits, tmpfs `/tmp` noexec, repo mounted read-only, wall-clock timeout, kill switch. Without either, mode is `static_only` and reported as "not executed". |
| SSRF via `endpoint_url` | Only https to public hosts, or http(s) to localhost. Credentials in URL rejected. All resolved addresses must be public; link-local and cloud-metadata ranges (169.254.0.0/16, fd00:ec2::/32) are always blocked. RFC1918 needs operator opt-in `QE_ALLOW_PRIVATE_ENDPOINTS=1`. No redirects followed, 30 s timeout, 1 MB response cap. Re-validated on every call. |
| Testing systems the user does not own | `authorized: true` is a required attestation (422 otherwise), stored with a timestamp on the project and appended to a hash-chained audit ledger (`runs/projects/audit.sqlite`, human-producer event). The platform never calls anything except the user-supplied endpoint or a sandbox. |
| Secret leakage | `GITHUB_TOKEN` is read from the environment only for the clone, passed via git config env vars (not argv), scrubbed from errors, never stored. Target secrets live only in an in-memory vault (never serialised, absent from GET responses and files); names are listed, values never returned. The analyser records only file and line for hard-coded credential findings, never the value. |

## Known limitations
- DNS rebinding between validation and connect is narrowed (re-validated per call) but not eliminated; fixing it needs IP-pinned connections.
- Clone size is checked after download, so the clone timeout is the real bound on bandwidth.
- Docker mode runs a detected top-level Python `ask/query/...(question)` function in a stock `python:3.12-slim` image with no network and no dependency install, so apps needing third-party packages or LLM calls will report an error. An allowlisted LLM egress proxy and dependency-baked images are future work.
- The analyser is heuristic (regex); flags are candidates, not findings. Only the outcome oracles and deterministic verifiers (R4, R6) decide anything.
- `python-multipart` is not installed; multipart upload returns 415 with guidance, raw `application/zip` upload works.

## Addendum 2026-10-31: hardening after independent security review
- Endpoint SSRF: non-local hosts must be globally routable (`ip.is_global`) and outside extra deny ranges (CGNAT 100.64/10 incl. Alibaba metadata 100.100.100.200, 192.88.99/24, 198.18/15, multicast/reserved, fec0::/10, NAT64, 6to4). IPv4-mapped IPv6 is unwrapped before checks. `QE_ALLOW_PRIVATE_ENDPOINTS=1` only unlocks RFC1918/ULA, never link-local, metadata, CGNAT or loopback.
- DNS pinning: the host is resolved once per request, validated, and the socket connects to that IP (`http.client`, Host header and TLS SNI/cert check use the original hostname). `http.client` never reads proxy env vars; redirects are errors.
- Loopback endpoints: allowed unless they target the platform itself (ports 8000/8001/`QE_UI_PORT`, or paths under `/api/`). `QE_ALLOW_LOCAL_ENDPOINTS=1` lifts that restriction (use for a local demo app on a platform port). A demo app on e.g. `http://127.0.0.1:9100/invoke` works without the variable.
- Endpoint URLs may not carry userinfo, query string or fragment; GET responses show scheme://host:port/path only.
- API surface: Host allowlist (127.0.0.1, localhost, ::1, testserver, plus `QE_ALLOWED_HOSTS`), cross-origin POST/PUT/DELETE rejected via `Origin` and `Sec-Fetch-Site: cross-site`, streamed request-body caps (50 MiB upload, 8 MiB JSON). Residual: a page served from another localhost port is not distinguishable by Origin hostname alone.
- DoS: ingest runs on a 2-worker pool with a bounded queue (429 when full); uploads stream to disk, not memory; clone uses `--filter=blob:limit=5m` and a watchdog that kills git when the workspace passes the byte cap.
- Secrets: names must match `^[A-Z][A-Z0-9_]{0,63}$` and avoid DOCKER_*, QE_*, LD_*, PYTHON*, BASH_*, SSL*, GIT_*, *_PROXY, PATH, HOME etc. The docker CLI gets a minimal env (operator docker config + the allowed secrets for that one call), never the server's full environment.
- Docker adds `--memory-swap`, `--ipc none`, `--init`, nofile/nproc ulimits.
- Generated questions: documents are wrapped in `<untrusted_document>` blocks (embedded tags neutralised), evidence and the answer must both be verbatim in the document, and items carry `lineage.advisory=true, confirmed=false`. Decision code must treat them as advisory until a user confirms (not yet enforced in scoring).
