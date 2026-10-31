"""Static, regex-based RAG structure analysis. Never imports, executes or shells out repo code."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

from qe.ingest.limits import MAX_ANALYZED_FILE_BYTES, MAX_ANALYZED_FILES
from qe.ingest.models import (
    Chunking,
    Entrypoint,
    ProjectAnalysis,
    PromptTemplate,
    RiskFlag,
)

SKIP_DIRS = frozenset({"node_modules", ".git", ".venv", "venv", "env", "__pycache__", "dist",
                       "build", "site-packages", ".next", ".tox", ".mypy_cache"})
CODE_EXT = {".py": "python", ".js": "javascript", ".mjs": "javascript", ".jsx": "javascript",
            ".ts": "typescript", ".tsx": "typescript"}
MANIFESTS = frozenset({"requirements.txt", "pyproject.toml", "package.json", ".env.example",
                       ".env.sample", ".env.template"})
MAX_LINE = 2000

FRAMEWORKS = (("langchain", r"langchain"), ("llama_index", r"llama[_-]?index"),
              ("haystack", r"\bhaystack\b"))
VECTOR_STORES = (("faiss", r"\bfaiss"), ("chroma", r"chromadb|\bChroma\b|langchain_chroma"),
                 ("pinecone", r"pinecone"), ("weaviate", r"weaviate"), ("qdrant", r"qdrant"),
                 ("milvus", r"milvus|pymilvus"), ("pgvector", r"pgvector"),
                 ("lancedb", r"lancedb"), ("elasticsearch", r"elasticsearch|opensearch"),
                 ("redis", r"redisvl|RedisVectorStore"))
RETRIEVERS = (("bm25", r"bm25|BM25"), ("tfidf", r"Tfidf(Vectorizer|Retriever)"),
              ("vector_similarity", r"similarity_search|as_retriever|VectorStoreIndex|"
                                    r"\.query\(\s*query_embeddings|cosine"),
              ("hybrid", r"EnsembleRetriever|hybrid"))
LLM_PROVIDERS = (("openai", r"\bopenai\b|ChatOpenAI"), ("anthropic", r"anthropic|ChatAnthropic"),
                 ("groq", r"\bgroq\b|ChatGroq"), ("google", r"google\.generativeai|google\.genai|"
                                                  r"ChatGoogle|gemini"),
                 ("ollama", r"ollama"), ("cohere", r"\bcohere\b"), ("mistral", r"mistralai"),
                 ("huggingface", r"huggingface|transformers"), ("openrouter", r"openrouter"),
                 ("litellm", r"litellm"), ("bedrock", r"bedrock"))
EMBEDDING_LINE = re.compile(r"embed", re.I)
DOC_LOADERS = re.compile(
    r"\b(PyPDFLoader|TextLoader|DirectoryLoader|WebBaseLoader|UnstructuredFileLoader|CSVLoader|"
    r"SimpleDirectoryReader|JSONLoader|NotionDirectoryLoader|PDFPlumberLoader)\b")
DOC_FILE = re.compile(r"""["'][^"'\n]{0,120}\.(pdf|md|txt|csv|docx|json)["']""")
CHUNK_SIZE = re.compile(r"chunk[_]?size\s*[=:]\s*(\d+)", re.I)
CHUNK_OVERLAP = re.compile(r"chunk[_]?overlap\s*[=:]\s*(\d+)", re.I)
ENV_PY = re.compile(
    r"""os\.(?:environ\s*\[\s*|environ\.get\(\s*|getenv\(\s*)["']([A-Z][A-Z0-9_]*)["']""")
ENV_JS = re.compile(r"process\.env\.([A-Z][A-Z0-9_]*)|process\.env\[\s*[\"']([A-Z][A-Z0-9_]*)[\"']")
ENV_FILE = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=", re.M)
ROUTE_PY = re.compile(r"""@\w+\.(get|post|put|delete|route)\(\s*["']([^"']+)["']""")
ROUTE_JS = re.compile(r"""\b(?:app|router)\.(get|post|put|delete)\(\s*["'`]([^"'`]+)["'`]""")
NEXT_ROUTE = re.compile(r"export\s+(?:async\s+)?function\s+(GET|POST)\b")
DEF_PY = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(")
QA_FUNC = re.compile(r"^(ask|query|answer|chat|rag|run_query|generate_answer|"
                     r"answer_question|handle_question)\w*$")
PROMPT_HINT = re.compile(r"\{(context|question|query|documents|retrieved)\}|"
                         r"PromptTemplate|ChatPromptTemplate|from_template", re.I)
CONTEXT_IN_PROMPT = re.compile(r"\{(context|retrieved|documents|docs)\}|\$\{(context|docs)\}", re.I)
GUARD_WORDS = re.compile(r"untrusted|ignore (any )?instructions|do not follow|delimit|sanitiz|"
                         r"<context>|only use the (context|provided)", re.I)
CITATION_WORDS = re.compile(r"citation|cite|source_documents|\bsources?\b|metadata|references?\b",
                            re.I)
RETRIEVAL_CALL = re.compile(
    r"(similarity_search\w*|as_retriever|\.query)\(|\bget_relevant_documents\(")
TOPK_WORDS = re.compile(r"\b(k|top_k|topk|n_results|similarity_top_k|limit)\s*[=:]|search_kwargs",
                        re.I)
SECRET_LIT = re.compile(
    r"""(sk-[A-Za-z0-9_-]{20,}|gsk_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"""
    r"""(?:api[_-]?key|secret|token)\s*[=:]\s*["'][A-Za-z0-9_\-]{24,}["'])""", re.I)


def _iter_files(root: Path) -> list[Path]:
    out: list[Path] = []
    base = root.resolve()
    for cur, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".git"))
        for n in sorted(names):
            p = Path(cur) / n
            if p.is_symlink() or not p.resolve().is_relative_to(base):
                continue
            if p.suffix in CODE_EXT or n in MANIFESTS:
                try:
                    if p.stat().st_size <= MAX_ANALYZED_FILE_BYTES:
                        out.append(p)
                except OSError:
                    continue
            if len(out) >= MAX_ANALYZED_FILES:
                return out
    return out


def _first(table: tuple[tuple[str, str], ...], text: str) -> str | None:
    counts = Counter({name: len(re.findall(pat, text)) for name, pat in table})
    best = [(n, c) for n, c in counts.most_common() if c > 0]
    return best[0][0] if best else None


def _all(table: tuple[tuple[str, str], ...], text: str) -> list[str]:
    return [name for name, pat in table if re.search(pat, text)]


class _Acc:
    def __init__(self) -> None:
        self.a = ProjectAnalysis()
        self.env: set[str] = set()
        self.docs: list[str] = []
        self.first_code: str = ""
        self.has_citation = False
        self.has_guard = False
        self.langs: set[str] = set()
        self.flags: list[RiskFlag] = []
        self.rag_signal = False


def _scan_code(acc: _Acc, rel: str, text: str, lang: str) -> None:
    acc.langs.add(lang)
    acc.first_code = acc.first_code or rel
    lines = [ln[:MAX_LINE] for ln in text.splitlines()]
    if CITATION_WORDS.search(text):
        acc.has_citation = True
    if GUARD_WORDS.search(text):
        acc.has_guard = True
    for i, line in enumerate(lines, 1):
        for m in ENV_PY.finditer(line):
            acc.env.add(m.group(1))
        for jm in ENV_JS.finditer(line):
            acc.env.add(jm.group(1) or jm.group(2))
        for dm in DOC_LOADERS.finditer(line):
            acc.docs.append(dm.group(1))
        if lang == "python":
            for rm in ROUTE_PY.finditer(line):
                verb = rm.group(1).upper()
                acc.a.entrypoints.append(Entrypoint(
                    kind="http_route", name=rm.group(2), file=rel, line=i,
                    detail=f"{'ANY' if verb == 'ROUTE' else verb} {rm.group(2)}"))
            fm = DEF_PY.match(line)
            if fm and QA_FUNC.match(fm.group(1)):
                acc.a.entrypoints.append(Entrypoint(kind="function", name=fm.group(1),
                                                    file=rel, line=i, detail="query function"))
            if line.startswith("if __name__") and "__main__" in line:
                acc.a.entrypoints.append(Entrypoint(kind="cli", name="__main__", file=rel,
                                                    line=i))
        else:
            for rm in ROUTE_JS.finditer(line):
                acc.a.entrypoints.append(Entrypoint(
                    kind="express_route", name=rm.group(2), file=rel, line=i,
                    detail=f"{rm.group(1).upper()} {rm.group(2)}"))
            for nm in NEXT_ROUTE.finditer(line):
                acc.a.entrypoints.append(Entrypoint(kind="http_route", name=nm.group(1),
                                                    file=rel, line=i, detail=nm.group(1)))
        if PROMPT_HINT.search(line) and len(acc.a.prompts) < 20:
            acc.a.prompts.append(PromptTemplate(file=rel, line=i, snippet=line.strip()[:200]))
            if CONTEXT_IN_PROMPT.search(line):
                acc.flags.append(RiskFlag(
                    id="unsanitized-context-in-prompt", evidence_file=rel, line=i,
                    title="Retrieved context is inserted into the prompt without visible "
                          "delimiting or sanitising"))
        cm = CHUNK_SIZE.search(line)
        if cm and acc.a.chunking is None:
            om = CHUNK_OVERLAP.search(line)
            acc.a.chunking = Chunking(chunk_size=int(cm.group(1)), file=rel, line=i,
                                      chunk_overlap=int(om.group(1)) if om else None)
        if RETRIEVAL_CALL.search(line):
            window = " ".join(lines[i - 1:i + 3])
            if not TOPK_WORDS.search(window):
                acc.flags.append(RiskFlag(
                    id="no-top-k-bound", evidence_file=rel, line=i,
                    title="Retrieval call has no explicit top-k / result limit"))
        sm = SECRET_LIT.search(line)
        if sm:
            acc.flags.append(RiskFlag(id="hardcoded-secret", evidence_file=rel, line=i,
                                      title="Possible hardcoded credential in source"))


def _scan_manifest(acc: _Acc, name: str, text: str) -> None:
    if name.startswith(".env"):
        acc.env.update(ENV_FILE.findall(text))
    if name == "package.json":
        try:
            data = json.loads(text)
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            acc.langs.add("javascript")
            acc.a.notes.append("package.json dependencies: " + ", ".join(sorted(deps)[:30]))
        except (ValueError, AttributeError):
            pass


def _dedupe_flags(flags: list[RiskFlag]) -> list[RiskFlag]:
    seen: set[tuple[str, str, int]] = set()
    out: list[RiskFlag] = []
    for f in flags:
        key = (f.id, f.evidence_file, f.line)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def _language(langs: set[str]) -> str:
    if not langs:
        return "unknown"
    if len(langs) == 1:
        return next(iter(langs))
    return "typescript" if langs <= {"javascript", "typescript"} else "mixed"


def analyze_workspace(root: Path) -> ProjectAnalysis:
    acc = _Acc()
    corpus: list[str] = []
    files = _iter_files(root)
    base = root.resolve()
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = p.resolve().relative_to(base).as_posix()
        corpus.append(text)
        if p.suffix in CODE_EXT:
            _scan_code(acc, rel, text, CODE_EXT[p.suffix])
        else:
            _scan_manifest(acc, p.name, text)
    whole = "\n".join(corpus)
    a = acc.a
    a.files_scanned = len(files)
    if not files:
        a.notes.append("No analysable Python/JS/TS files were found.")
        return a
    a.language = _language(acc.langs)
    a.retriever = _first(RETRIEVERS, whole)
    a.vector_store = _first(VECTOR_STORES, whole)
    a.llm_providers = _all(LLM_PROVIDERS, whole)
    emb_text = "\n".join(ln for ln in whole.splitlines() if EMBEDDING_LINE.search(ln))
    a.embedding_providers = _all(LLM_PROVIDERS, emb_text)
    a.framework = _first(FRAMEWORKS, whole) or (
        "raw" if (a.llm_providers or a.vector_store or a.retriever) else "unknown")
    a.doc_sources = sorted(set(acc.docs))
    a.env_vars = sorted(acc.env)
    a.entrypoints = a.entrypoints[:50]
    rag = bool(a.retriever or a.vector_store or a.prompts)
    anchor = (a.prompts[0] if a.prompts else None)
    ev_file = anchor.file if anchor else acc.first_code
    ev_line = anchor.line if anchor else 1
    flags = list(acc.flags)
    if acc.has_guard:
        flags = [f for f in flags if f.id != "unsanitized-context-in-prompt"]
    if rag and not acc.has_citation:
        flags.append(RiskFlag(id="no-citation-handling", evidence_file=ev_file, line=ev_line,
                              title="No citation / source handling found in the answer path"))
    a.risk_flags = _dedupe_flags(flags)[:100]
    return a
