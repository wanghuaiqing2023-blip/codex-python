"""Telemetry helpers from Rust ``codex-api/src/telemetry.rs``."""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any
from typing import Protocol
from typing import TypeVar
from typing import runtime_checkable

from pycodex.codex_client import Request
from pycodex.codex_client import RequestTelemetry
from pycodex.codex_client import RetryPolicy
from pycodex.codex_client import TransportError
from pycodex.codex_client.retry import backoff


T = TypeVar("T")


@runtime_checkable
class SseTelemetry(Protocol):
    def on_sse_poll(self, result: Any, duration: float) -> None:
        """Record one SSE poll result."""


@runtime_checkable
class WebsocketTelemetry(Protocol):
    def on_ws_request(self, duration: float, error: BaseException | None, connection_reused: bool) -> None:
        """Record one WebSocket request attempt."""

    def on_ws_event(self, result: Any, duration: float) -> None:
        """Record one WebSocket event poll result."""


def response_status(response: Any) -> int:
    status = getattr(response, "status", None)
    if status is None:
        raise AttributeError("response must expose status")
    return int(status)


def http_status(err: TransportError) -> int | None:
    return err.status if err.kind == "http" else None


async def run_with_request_telemetry(
    policy: RetryPolicy,
    telemetry: RequestTelemetry | None,
    make_request: Any,
    send: Any,
    *,
    sleep: Any = asyncio.sleep,
    clock: Any = time.perf_counter,
) -> T:
    for attempt in range(policy.max_attempts + 1):
        req = make_request()
        start = clock()
        try:
            result = await _maybe_await(send(req))
        except TransportError as err:
            duration = clock() - start
            if telemetry is not None:
                telemetry.on_request(attempt, http_status(err), err, duration)
            if policy.retry_on.should_retry(err, attempt, policy.max_attempts):
                await _maybe_await(sleep(backoff(policy.base_delay, attempt + 1)))
                continue
            raise
        except BaseException:
            raise

        duration = clock() - start
        if telemetry is not None:
            telemetry.on_request(attempt, response_status(result), None, duration)
        return result

    raise TransportError.retry_limit()


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "SseTelemetry",
    "WebsocketTelemetry",
    "http_status",
    "response_status",
    "run_with_request_telemetry",
]
