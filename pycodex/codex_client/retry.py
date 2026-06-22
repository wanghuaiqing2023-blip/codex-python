"""Retry policy helpers for the Rust ``codex-client`` port.

Rust source:
- ``codex/codex-rs/codex-client/src/retry.rs``
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

from .error import TransportError


T = TypeVar("T")
RequestT = TypeVar("RequestT")


@dataclass(frozen=True)
class RetryOn:
    retry_429: bool
    retry_5xx: bool
    retry_transport: bool

    def should_retry(
        self, err: TransportError, attempt: int, max_attempts: int
    ) -> bool:
        if attempt >= max_attempts:
            return False
        if err.kind == "http":
            status = err.status or 0
            return (self.retry_429 and status == 429) or (
                self.retry_5xx and 500 <= status <= 599
            )
        if err.kind in {"timeout", "network"}:
            return self.retry_transport
        return False


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    base_delay: float
    retry_on: RetryOn


def _saturating_pow2(exponent: int) -> int:
    if exponent <= 0:
        return 1
    value = 1 << exponent
    return min(value, (1 << 64) - 1)


def backoff(
    base_delay: float,
    attempt: int,
    *,
    random_range: Callable[[float, float], float] | None = None,
) -> float:
    if attempt == 0:
        return base_delay
    exponent = _saturating_pow2(attempt - 1)
    raw = base_delay * exponent
    jitter_source = random_range or random.uniform
    return raw * jitter_source(0.9, 1.1)


def run_with_retry(
    policy: RetryPolicy,
    make_req: Callable[[], RequestT],
    op: Callable[[RequestT, int], T],
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    for attempt in range(policy.max_attempts + 1):
        req = make_req()
        try:
            return op(req, attempt)
        except TransportError as err:
            if policy.retry_on.should_retry(err, attempt, policy.max_attempts):
                sleep(backoff(policy.base_delay, attempt + 1))
                continue
            raise
    raise TransportError.retry_limit()
