"""Campaign request/target models and shared constants."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from qe.core.schemas import Policy
from qe.ingest.target_config import TargetConfig

STAGES = ("risk_definition", "test_plan", "execution", "verification", "classification",
          "scoring", "comparison", "recommendation", "review")
ID_RE = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
CAMPAIGN_ID = re.compile(r"^cmp-[0-9a-f]{8}$")
LABEL_RE = r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,39}$"
MAX_TARGETS = 8
MAX_CALLS_CAP = 20_000
DEFAULT_MAX_CALLS = 2000
DEFAULT_TIMEOUT_S = 1800.0
DEFAULT_ALPHA = 0.05  # conventional two-sided significance level; the user may set it
MAX_STUFF_CHARS = 48_000  # context-stuffing cap for model targets (stated limit, noted in run)


class TargetSpec(BaseModel):
    """One system under test. `endpoint` = the company's RAG app over HTTP (the project's own
    endpoint when endpoint_url is omitted); `model` = a bare OpenAI-compatible chat endpoint
    given the user's documents by context stuffing (RAG-less baseline)."""

    model_config = ConfigDict(extra="forbid")
    label: str = Field(pattern=LABEL_RE)
    kind: Literal["endpoint", "model"]
    endpoint_url: str | None = Field(default=None, max_length=500)
    target_config: TargetConfig | None = None
    model: str | None = Field(default=None, max_length=200)
    base_url: str | None = Field(default=None, max_length=500)
    api_key_secret: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict, max_length=20)

    @model_validator(mode="after")
    def _kind_fields(self) -> TargetSpec:
        if self.kind == "model" and not (self.model and self.base_url):
            raise ValueError("model targets need `model` and `base_url`")
        if self.kind == "endpoint" and (self.model or self.base_url):
            raise ValueError("endpoint targets take endpoint_url/target_config, not model/base_url")
        return self


@dataclass
class CampaignParams:
    name: str
    project_id: str
    risk_focus: list[str] = field(default_factory=list)
    repeats: int = 3
    max_cases: int = 50
    max_calls: int = DEFAULT_MAX_CALLS
    timeout_s: float = DEFAULT_TIMEOUT_S
    include_security: bool = True
    generate_with_llm: bool = True
    seed: int = 0
    alpha: float = DEFAULT_ALPHA
    policy: Policy | None = None
    use_example_policy: bool = False
    imported_plan: dict[str, Any] | None = None

    def public(self) -> dict[str, Any]:
        return {"risk_focus": self.risk_focus, "repeats": self.repeats,
                "max_cases": self.max_cases, "max_calls": self.max_calls,
                "timeout_s": self.timeout_s, "include_security": self.include_security,
                "generate_with_llm": self.generate_with_llm, "seed": self.seed,
                "alpha": self.alpha, "use_example_policy": self.use_example_policy,
                "policy": self.policy.model_dump(mode="json") if self.policy else None,
                "plan_imported": self.imported_plan is not None}
