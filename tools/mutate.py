"""Minimal AST mutation tester (mutmut needs fork(); unavailable on Windows).

Usage: python tools/mutate.py OUT.json -m qe/stats/intervals.py -t tests/unit/test_stats.py ...
Mutants run in scratch copies of qe/, tests/, pyproject.toml; the working tree is never edited.
A mutant is KILLED if the selected tests fail/time out, SURVIVED otherwise. Equivalent mutants
are NOT detected automatically: triage survivors by hand and report raw + triaged scores.
Operators: comparison swap (<,<=,>,>=,==,!=), arithmetic swap (+/-, */ /, //), numeric constant
+1 (int) or +0.5-ish tweak (float), and/or swap, `not` removal, `return x` -> `return None`
for non-None returns, `if` test negation, unary minus removal.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CMP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
       ast.Eq: ast.NotEq, ast.NotEq: ast.Eq}
ARITH = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult,
         ast.FloorDiv: ast.Mult}


def _sites(tree: ast.AST) -> list[tuple[int, str, int]]:
    out: list[tuple[int, str, int]] = []
    for i, node in enumerate(ast.walk(tree)):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Compare) and type(node.ops[0]) in CMP:
            out.append((i, "cmp", line))
        elif isinstance(node, ast.BinOp) and type(node.op) in ARITH:
            out.append((i, "arith", line))
        elif isinstance(node, ast.Constant) and type(node.value) in (int, float):
            out.append((i, "const", line))
        elif isinstance(node, ast.BoolOp):
            out.append((i, "boolop", line))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.Not, ast.USub)):
            out.append((i, "unary", line))
        elif isinstance(node, ast.If):
            out.append((i, "if", line))
        elif (isinstance(node, ast.Return) and node.value is not None
              and not (isinstance(node.value, ast.Constant) and node.value.value is None)):
            out.append((i, "return", line))
    return out


def _mutate(src: str, idx: int, kind: str) -> str:
    if kind == "unary":
        return _mutate_unary(src, idx)
    tree = ast.parse(src)
    node = list(ast.walk(tree))[idx]
    if kind == "cmp":
        assert isinstance(node, ast.Compare)
        node.ops[0] = CMP[type(node.ops[0])]()
    elif kind == "arith":
        assert isinstance(node, ast.BinOp)
        node.op = ARITH[type(node.op)]()
    elif kind == "const":
        assert isinstance(node, ast.Constant)
        v = node.value
        node.value = v + 1 if isinstance(v, int) else v + 0.5 if v < 0.5 else v - 0.25
    elif kind == "boolop":
        assert isinstance(node, ast.BoolOp)
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif kind == "if":
        assert isinstance(node, ast.If)
        node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
    elif kind == "return":
        assert isinstance(node, ast.Return)
        node.value = ast.Constant(value=None)
    return ast.unparse(ast.fix_missing_locations(tree))


def _mutate_unary(src: str, idx: int) -> str:
    tree = ast.parse(src)
    target = list(ast.walk(tree))[idx]

    class T(ast.NodeTransformer):
        def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
            if node is target:
                return node.operand
            return self.generic_visit(node)

    return ast.unparse(ast.fix_missing_locations(T().visit(tree)))


def _run(work: Path, tests: list[str], timeout: int) -> bool:
    """Return True if mutant survived."""
    env = {**os.environ, "PYTHONPATH": str(work), "PYTHONHASHSEED": "0"}
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", *tests],
            cwd=work, env=env, capture_output=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False
    return r.returncode == 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("-m", "--module", action="append", required=True)
    ap.add_argument("-t", "--tests", action="append", required=True)
    ap.add_argument("-j", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=180)
    a = ap.parse_args()
    root = Path.cwd()
    scratch = Path(tempfile.mkdtemp(prefix="mut_"))
    jobs = []
    for mod in a.module:
        src = (root / mod).read_text(encoding="utf-8")
        for idx, kind, line in _sites(ast.parse(src)):
            jobs.append((mod, src, idx, kind, line))
    workers = []
    for w in range(a.j):
        d = scratch / f"w{w}"
        ign = shutil.ignore_patterns("__pycache__", "desktop.ini")  # OneDrive litters desktop.ini
        shutil.copytree(root / "qe", d / "qe", ignore=ign)
        shutil.copytree(root / "tests", d / "tests", ignore=ign)
        shutil.copy(root / "pyproject.toml", d / "pyproject.toml")
        workers.append(d)
    free = list(range(a.j))
    import threading
    lock = threading.Lock()

    def one(job: tuple[str, str, int, str, int]) -> dict[str, object]:
        mod, src, idx, kind, line = job
        with lock:
            w = free.pop()
        d = workers[w]
        try:
            mutated = _mutate(src, idx, kind)
            (d / mod).write_text(mutated, encoding="utf-8")
            survived = _run(d, a.tests, a.timeout)
        finally:
            (d / mod).write_text(src, encoding="utf-8")
            with lock:
                free.append(w)
        return {"module": mod, "line": line, "kind": kind, "idx": idx, "survived": survived}

    with ThreadPoolExecutor(a.j) as ex:
        results = list(ex.map(one, jobs))
    Path(a.out).write_text(json.dumps(results, indent=1), encoding="utf-8")
    shutil.rmtree(scratch, ignore_errors=True)
    surv = [r for r in results if r["survived"]]
    print(f"mutants={len(results)} killed={len(results) - len(surv)} survived={len(surv)}")
    for r in surv:
        print(f"  SURVIVED {r['module']}:{r['line']} {r['kind']}")


if __name__ == "__main__":
    main()
