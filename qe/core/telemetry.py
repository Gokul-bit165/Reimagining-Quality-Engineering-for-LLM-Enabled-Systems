"""Telemetry kill-switches for dependencies (rule R7). Enforced at import of `qe`."""

from __future__ import annotations

import os
from collections.abc import MutableMapping

# flag -> required value. Sources: research/23 (DeepEval, RAGAS) plus common ecosystem opt-outs.
REQUIRED_FLAGS: dict[str, str] = {
    "DEEPEVAL_TELEMETRY_OPT_OUT": "1",
    "RAGAS_DO_NOT_TRACK": "true",
    "DO_NOT_TRACK": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "ANONYMIZED_TELEMETRY": "False",
}


def enforce_telemetry_off(env: MutableMapping[str, str] | None = None) -> None:
    target = os.environ if env is None else env
    for flag, value in REQUIRED_FLAGS.items():
        target[flag] = value


def telemetry_violations(env: MutableMapping[str, str] | None = None) -> list[str]:
    source = os.environ if env is None else env
    return [f for f, v in REQUIRED_FLAGS.items() if source.get(f) != v]
