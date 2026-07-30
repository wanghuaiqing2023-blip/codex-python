"""Test tracing capture derived from ``tracing.rs``."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field


@dataclass
class TestTracingContext(logging.Handler):
    tracer_name: str
    records: list[logging.LogRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        logging.Handler.__init__(self)

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def close(self) -> None:
        logging.getLogger(self.tracer_name).removeHandler(self)
        super().close()


def install_test_tracing(tracer_name: str) -> TestTracingContext:
    context = TestTracingContext(tracer_name)
    logging.getLogger(tracer_name).addHandler(context)
    return context


__all__ = ["TestTracingContext", "install_test_tracing"]
