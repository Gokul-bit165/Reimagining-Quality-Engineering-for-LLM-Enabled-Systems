from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_third_party_notices_cover_declared_integrations() -> None:
    text = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for name in ("DeepEval", "RAGAS", "openai/evals", "Apache-2.0", "MIT"):
        assert name in text


def test_no_vendored_third_party_packages() -> None:
    banned = {"deepeval", "ragas", "evals"}
    found = {p.name for p in ROOT.rglob("*") if p.is_dir() and ".venv" not in p.parts
             and p.name in banned and "research" not in p.parts and "runs" not in p.parts}
    assert not found, f"vendored third-party directories: {found}"
