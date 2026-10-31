"""Tiny SDK shim (access level B): decorator / context manager that records `Span`s.

Span ids are sequential (`s0`, `s1`, ...) so recording is deterministic and replayable.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import Ledger
from qe.core.schemas import Span

F = TypeVar("F", bound=Callable[..., Any])


class Recorder:
    def __init__(self) -> None:
        self._spans: list[Span] = []

    @contextmanager
    def span(self, kind: str, **attributes: Any) -> Iterator[None]:
        attrs = dict(attributes)
        span_id = f"s{len(self._spans)}"
        self._spans.append(Span(span_id=span_id, kind=kind, attributes=attrs))  # reserve order
        slot = len(self._spans) - 1
        try:
            yield
        except BaseException as exc:
            self._spans[slot] = Span(span_id=span_id, kind=kind,
                                     attributes={**attrs, "error": type(exc).__name__})
            raise

    def traced(self, kind: str, **attributes: Any) -> Callable[[F], F]:
        def wrap(fn: F) -> F:
            @functools.wraps(fn)
            def inner(*args: Any, **kwargs: Any) -> Any:
                with self.span(kind, **attributes):
                    return fn(*args, **kwargs)
            return inner  # type: ignore[return-value]
        return wrap

    def spans(self) -> tuple[Span, ...]:
        return tuple(self._spans)

    def emit(self, ledger: Ledger, key: str) -> None:
        """Append the recorded spans as one TRACE_RECORDED event (idempotent on `key`)."""
        ledger.append(Event(key=key, type=EventType.TRACE_RECORDED, producer="sdk_shim",
                            producer_kind=ProducerKind.DETERMINISTIC,
                            payload={"spans": [s.model_dump(mode="json") for s in self._spans]}))
