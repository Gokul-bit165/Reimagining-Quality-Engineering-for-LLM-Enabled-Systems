"""Plain-language summary, next steps and env template for non-expert users."""

from __future__ import annotations

from qe.ingest.models import ExecutionMode, ProjectAnalysis

_MODE_TEXT = {
    "endpoint": "Tests will call your deployed app over HTTP (the app is run by you, not by us).",
    "docker": "Tests will run your code inside an isolated container with no network access.",
    "static_only": "Your code was only read, not run: results are a code review, not test "
                   "results. Provide a deployed endpoint URL or install Docker to run tests.",
}


def choose_mode(endpoint_url: str | None, analysis: ProjectAnalysis,
                docker_ok: bool) -> ExecutionMode:
    if endpoint_url:
        return "endpoint"
    runnable = analysis.language == "python" and any(
        e.kind == "function" and e.file.endswith(".py") for e in analysis.entrypoints)
    return "docker" if docker_ok and runnable else "static_only"


def decorate(a: ProjectAnalysis, mode: ExecutionMode) -> ProjectAnalysis:
    """Return a copy with execution_mode, summary, next_steps and env_template filled in."""
    parts = [f"This looks like a {a.language} project"]
    if a.framework not in ("unknown", "raw"):
        parts.append(f"built with {a.framework}")
    elif a.framework == "raw":
        parts.append("that calls its model and search code directly")
    desc = " ".join(parts) + "."
    found = []
    if a.vector_store:
        found.append(f"documents are stored in {a.vector_store}")
    if a.retriever:
        found.append(f"it finds passages using {a.retriever.replace('_', ' ')}")
    if a.llm_providers:
        found.append("it talks to " + ", ".join(a.llm_providers))
    if found:
        desc += " " + "; ".join(found).capitalize() + "."
    if not (a.retriever or a.vector_store or a.prompts):
        desc += " We did not find clear retrieval code, so results may be limited."
    n = len(a.risk_flags)
    desc += (f" We spotted {n} possible weak spot{'s' if n != 1 else ''} to check."
             if n else " No obvious weak spots were spotted by the code scan.")
    steps = [
        "Confirm you own or are authorised to test this app (required before any test runs).",
    ]
    if mode == "static_only":
        steps.append("Add the URL of your deployed app, or install Docker, so tests can run.")
    elif mode == "endpoint":
        steps.append("Check the endpoint URL points at a test or staging copy, not production.")
    else:
        steps.append("Docker is available: tests run your code in a locked-down container.")
    if a.env_vars:
        steps.append("Enter values for the settings your app needs (listed in the env "
                     "template). They are kept in memory only.")
    steps.append("Accept the suggested documents as the knowledge base, or upload your own.")
    steps.append("Add a few real questions with the answers you expect, then start the test.")
    template = "\n".join(f"{v}=" for v in a.env_vars)
    return a.model_copy(update={
        "execution_mode": mode, "summary": desc + " " + _MODE_TEXT[mode],
        "next_steps": steps, "env_template": template})
