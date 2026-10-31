"""Static run-plan detection and Dockerfile generation. Nothing here runs repo code.

`detect_run_plan(root)` answers one question: can we build and run this repo as a service in a
container, and how? It reads files only (ast.parse never executes). The result is a `RunPlan`:
either "use the repo's own Dockerfile" or a deterministic Dockerfile we generate. Raises
`NotRunnableError` with a precise reason otherwise.
"""

from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from qe.ingest.limits import (
    DOCKER_APP_PORT,
    DOCKER_NODE_IMAGE,
    DOCKER_PYTHON_IMAGE,
    MAX_ANALYZED_FILE_BYTES,
)

SKIP_DIRS = frozenset({"node_modules", ".git", ".venv", "venv", "env", "__pycache__", "dist",
                       "build", "site-packages", ".next", ".tox", ".mypy_cache", "tests", "test",
                       "docs", "examples"})
MAX_SCAN_FILES = 500
MAX_SCAN_DEPTH = 4
QA_FUNC = re.compile(r"^(ask|query|answer|chat|rag|run_query|generate_answer|"
                     r"answer_question|handle_question)\w*$")
ROUTE_PREFERRED = re.compile(r"ask|query|chat|answer|invoke|rag|generate|predict", re.I)
EXPOSE = re.compile(r"^\s*EXPOSE\s+(\d{2,5})", re.I | re.M)
JS_LISTEN = re.compile(r"\.listen\(\s*(?:process\.env\.\w+\s*(?:\|\||\?\?)\s*)?(\d{2,5})")
JS_ROUTE = re.compile(r"""\b(?:app|router)\.(get|post|put|delete)\(\s*["'`]([^"'`]+)["'`]""")
WRAPPER_NAME = "_qe_server.py"

# Stdlib-only HTTP wrapper for apps that expose a plain `ask(question)` function. It is copied
# into the image (never run on the host). POST any path with {"question": ...}.
WRAPPER_SOURCE = '''\
import importlib, json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/app")
_fn = getattr(importlib.import_module(os.environ["QE_MODULE"]), os.environ["QE_FUNC"])
_ANS = ("answer", "output", "response", "result", "text", "message")
_CTX = ("contexts", "context", "sources", "source_documents", "citations", "documents")


def _ctx(c):
    if isinstance(c, str):
        return c
    if isinstance(c, dict):
        for k in ("text", "content", "page_content", "snippet", "chunk"):
            if isinstance(c.get(k), str):
                return c[k]
    return json.dumps(c, default=str)[:2000]


def _normalise(raw):
    if isinstance(raw, str):
        return {"answer": raw, "contexts": []}
    if isinstance(raw, (list, tuple)) and raw:
        ctx = raw[1] if len(raw) > 1 and isinstance(raw[1], list) else []
        return {"answer": str(raw[0]), "contexts": [_ctx(c) for c in ctx]}
    if isinstance(raw, dict):
        ans = next((str(raw[k]) for k in _ANS if raw.get(k) is not None), "")
        for k in _CTX:
            v = raw.get(k)
            if isinstance(v, list):
                return {"answer": ans, "contexts": [_ctx(c) for c in v]}
            if isinstance(v, str) and v:
                return {"answer": ans, "contexts": [v]}
        return {"answer": ans, "contexts": []}
    return {"answer": str(raw), "contexts": []}


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(200, {"status": "ok"})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(n, 1000000)) or b"{}")
            q = body.get("question") or body.get("query") or body.get("input") or ""
            self._send(200, _normalise(_fn(q)))
        except Exception as exc:
            self._send(500, {"error": type(exc).__name__ + ": " + str(exc)[:300]})

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8000"))), H).serve_forever()
'''


class NotRunnableError(Exception):
    """The repo cannot be built and run as a service; the message is the precise reason."""


@dataclass(frozen=True)
class RunPlan:
    kind: str  # dockerfile | python-asgi | python-flask | python-function | node
    use_repo_dockerfile: bool
    port: int
    http_path: str
    description: str
    dockerfile: str = ""  # generated text ("" when the repo's own Dockerfile is used)
    extra_files: dict[str, str] = field(default_factory=dict)
    entry: str = ""


def _walk_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    base = root.resolve()
    for cur, dirs, names in os.walk(root, followlinks=False):
        depth = len(Path(cur).resolve().relative_to(base).parts)
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        if depth >= MAX_SCAN_DEPTH:
            dirs[:] = []
        for n in sorted(names):
            p = Path(cur) / n
            if p.suffix in suffixes and not p.is_symlink():
                try:
                    if p.stat().st_size <= MAX_ANALYZED_FILE_BYTES:
                        out.append(p)
                except OSError:
                    continue
        if len(out) >= MAX_SCAN_FILES:
            break
    # shallow first, then conventional names, then alphabetical
    pref = {"main.py": 0, "app.py": 1, "server.py": 2, "api.py": 3}
    return sorted(out, key=lambda p: (len(p.relative_to(root).parts), pref.get(p.name, 9),
                                      str(p)))


def _module_of(root: Path, p: Path) -> str | None:
    parts = list(p.relative_to(root).with_suffix("").parts)
    return ".".join(parts) if parts and all(x.isidentifier() for x in parts) else None


def _call_name(node: ast.expr) -> str:
    f = node.func if isinstance(node, ast.Call) else node
    if isinstance(f, ast.Name):
        return f.id
    return f.attr if isinstance(f, ast.Attribute) else ""


def _routes(tree: ast.Module) -> list[tuple[str, str]]:
    """(METHOD, path) for decorated functions: @app.post("/x"), @app.route("/x", methods=[...])."""
    found: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                    and dec.args and isinstance(dec.args[0], ast.Constant)
                    and isinstance(dec.args[0].value, str)):
                continue
            verb, path = dec.func.attr.lower(), dec.args[0].value
            if verb in ("get", "post", "put", "delete"):
                found.append((verb.upper(), path))
            elif verb == "route":
                methods = ["GET"]
                for kw in dec.keywords:
                    if kw.arg == "methods" and isinstance(kw.value, ast.List):
                        methods = [str(getattr(e, "value", "")).upper() for e in kw.value.elts]
                found.extend((m, path) for m in methods)
    return found


def _pick_route(routes: list[tuple[str, str]]) -> str:
    static = [(m, p) for m, p in routes if "{" not in p and "<" not in p]
    for pool in ([r for r in static if r[0] == "POST"], static):
        named = [r for r in pool if ROUTE_PREFERRED.search(r[1])]
        if named or pool:
            return (named or pool)[0][1]
    return "/"


@dataclass
class _PyFacts:
    asgi: tuple[str, str] | None = None  # (module, var)
    flask: tuple[str, str] | None = None
    function: tuple[str, str] | None = None  # (module, func)
    routes: list[tuple[str, str]] = field(default_factory=list)
    imports: set[str] = field(default_factory=set)


def _scan_python(root: Path) -> _PyFacts:
    facts = _PyFacts()
    for p in _walk_files(root, (".py",)):
        mod = _module_of(root, p)
        try:
            tree = ast.parse(p.read_text("utf-8", errors="replace"))
        except (SyntaxError, ValueError, OSError):
            continue
        facts.routes.extend(_routes(tree))
        for node in tree.body:
            if mod and isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                kind = _call_name(node.value)
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if kind == "FastAPI" and names and facts.asgi is None:
                    facts.asgi = (mod, names[0])
                elif kind == "Flask" and names and facts.flask is None:
                    facts.flask = (mod, names[0])
            elif mod and isinstance(node, ast.FunctionDef) and QA_FUNC.match(node.name) \
                    and facts.function is None and _one_required_arg(node):
                facts.function = (mod, node.name)
            elif isinstance(node, ast.Import | ast.ImportFrom):
                facts.imports.add((getattr(node, "module", None) or "").split(".")[0])
    return facts


def _one_required_arg(fn: ast.FunctionDef) -> bool:
    a = fn.args
    positional = [x.arg for x in [*a.posonlyargs, *a.args] if x.arg not in ("self", "cls")]
    required = len(positional) - len(a.defaults)
    kw_required = [k for k, d in zip(a.kwonlyargs, a.kw_defaults, strict=True) if d is None]
    return required == 1 and not kw_required


def _read(root: Path, name: str) -> str:
    p = root / name
    if p.is_file() and not p.is_symlink() and p.stat().st_size <= MAX_ANALYZED_FILE_BYTES:
        return p.read_text("utf-8", errors="replace")
    return ""


def _python_install(root: Path, needed: dict[str, str]) -> tuple[list[str], str]:
    """RUN lines that install dependencies, plus the manifest text (for extras detection)."""
    lines: list[str] = []
    manifest = ""
    if (root / "requirements.txt").is_file():
        lines.append("RUN pip install --no-cache-dir -r requirements.txt")
        manifest = _read(root, "requirements.txt")
    elif (root / "pyproject.toml").is_file() or (root / "setup.py").is_file():
        # covers PEP 621, poetry (poetry-core backend), uv projects (uv.lock is not used)
        lines.append("RUN pip install --no-cache-dir .")
        manifest = _read(root, "pyproject.toml") + _read(root, "setup.py")
    low = manifest.lower()
    extras = [pkg for imp, pkg in needed.items() if imp not in low]
    if extras:
        lines.append("RUN pip install --no-cache-dir " + " ".join(extras))
    return lines, manifest


def _py_dockerfile(install: list[str], cmd: list[str], port: int) -> str:
    return "\n".join([
        f"FROM {DOCKER_PYTHON_IMAGE}",
        "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 "
        "HOME=/tmp",
        "WORKDIR /app",
        "COPY . /app",
        *install,
        "RUN chmod -R a+rX /app",
        "USER 65534:65534",
        f"EXPOSE {port}",
        f"CMD {json.dumps(cmd)}",
        ""])


def _repo_dockerfile_plan(root: Path, facts: _PyFacts) -> RunPlan:
    text = _read(root, "Dockerfile")
    m = EXPOSE.search(text)
    port = int(m.group(1)) if m else DOCKER_APP_PORT
    path = _pick_route(facts.routes) if facts.routes else _js_path(root)
    return RunPlan("dockerfile", True, port, path,
                   f"uses the repository's own Dockerfile (port {port})")


def _js_path(root: Path) -> str:
    routes: list[tuple[str, str]] = []
    for p in _walk_files(root, (".js", ".mjs", ".ts")):
        routes.extend((m.group(1).upper(), m.group(2))
                      for m in JS_ROUTE.finditer(p.read_text("utf-8", errors="replace")))
    return _pick_route(routes)


def _node_plan(root: Path) -> RunPlan:
    try:
        pkg = json.loads(_read(root, "package.json") or "{}")
    except json.JSONDecodeError:
        raise NotRunnableError("package.json is not valid JSON") from None
    scripts = pkg.get("scripts") if isinstance(pkg, dict) else None
    if not isinstance(scripts, dict) or "start" not in scripts:
        raise NotRunnableError("no entrypoint detected: package.json has no 'start' script")
    port = DOCKER_APP_PORT
    for p in _walk_files(root, (".js", ".mjs", ".ts")):
        m = JS_LISTEN.search(p.read_text("utf-8", errors="replace"))
        if m:
            port = int(m.group(1))
            break
    locked = (root / "package-lock.json").is_file()
    install = f"RUN npm {'ci' if locked else 'install'} --omit=dev --no-audit --no-fund"
    df = "\n".join([
        f"FROM {DOCKER_NODE_IMAGE}", "ENV NODE_ENV=production HOME=/tmp HOST=0.0.0.0 "
        f"PORT={port}", "WORKDIR /app", "COPY . /app", install, "RUN chmod -R a+rX /app",
        "USER 65534:65534", f"EXPOSE {port}", 'CMD ["npm", "start"]', ""])
    return RunPlan("node", False, port, _js_path(root),
                   f"Node app started with `npm start` (port {port})", dockerfile=df,
                   entry="npm start")


def detect_run_plan(root: Path, app_port: int | None = None,
                    app_path: str | None = None) -> RunPlan:
    """Pick how to run the repo in a container, or raise NotRunnableError with the reason."""
    plan = _detect(root)
    changes: dict[str, object] = {}
    if app_port and app_port != plan.port:
        changes["port"] = app_port
        if plan.dockerfile:
            changes["dockerfile"] = plan.dockerfile.replace(
                f"EXPOSE {plan.port}", f"EXPOSE {app_port}")
    if app_path:
        changes["http_path"] = app_path
    return RunPlan(**{**plan.__dict__, **changes}) if changes else plan


def _detect(root: Path) -> RunPlan:
    if not root.is_dir():
        raise NotRunnableError("workspace not found")
    has_py = any(True for _ in _walk_files(root, (".py",)))
    facts = _scan_python(root) if has_py else _PyFacts()
    if (root / "Dockerfile").is_file() and not (root / "Dockerfile").is_symlink():
        return _repo_dockerfile_plan(root, facts)
    port = DOCKER_APP_PORT
    if facts.asgi:
        mod, var = facts.asgi
        install, _ = _python_install(root, {"uvicorn": "uvicorn", "fastapi": "fastapi"})
        cmd = ["python", "-m", "uvicorn", f"{mod}:{var}", "--host", "0.0.0.0",  # noqa: S104
               "--port", str(port)]
        return RunPlan("python-asgi", False, port, _pick_route(facts.routes),
                       f"FastAPI app {mod}:{var} served by uvicorn", dockerfile=_py_dockerfile(
                           install, cmd, port), entry=f"{mod}:{var}")
    if facts.flask:
        mod, var = facts.flask
        install, _ = _python_install(root, {"flask": "flask"})
        cmd = ["python", "-m", "flask", "--app", f"{mod}:{var}", "run", "--host", "0.0.0.0",  # noqa: S104
               "--port", str(port)]
        return RunPlan("python-flask", False, port, _pick_route(facts.routes),
                       f"Flask app {mod}:{var}", dockerfile=_py_dockerfile(install, cmd, port),
                       entry=f"{mod}:{var}")
    if facts.function:
        mod, fn = facts.function
        install, _ = _python_install(root, {})
        df = _py_dockerfile(install, ["python", "-I", f"/app/{WRAPPER_NAME}"], port)
        df = df.replace("USER 65534", f"ENV QE_MODULE={mod} QE_FUNC={fn}\nUSER 65534")
        return RunPlan("python-function", False, port, "/",
                       f"function {mod}.{fn}(question) behind a generated HTTP wrapper",
                       dockerfile=df, extra_files={WRAPPER_NAME: WRAPPER_SOURCE},
                       entry=f"{mod}.{fn}")
    if (root / "package.json").is_file():
        return _node_plan(root)
    raise NotRunnableError("no entrypoint detected (no Dockerfile, FastAPI/Flask app, "
                           "ask/query function or Node start script)")
