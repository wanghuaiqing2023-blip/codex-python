"""Responses stream retry and fallback decisions.

Ported from ``codex/codex-rs/core/src/responses_retry.rs``.

The Rust function performs side effects as well as decision-making: it may
switch transport, send a warning event, notify the UI, sleep, or return the
error.  This stdlib port keeps the same retry/fallback policy in a pure decision
helper so the client/session layer can perform those side effects explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum

from pycodex.core.util import backoff
from pycodex.protocol import CodexErr


class ResponsesStreamRequest(str, Enum):
    SAMPLING = "sampling"
    REMOTE_COMPACTION_V2 = "remote_compaction_v2"


class RetryableResponseStreamAction(str, Enum):
    RETRY = "retry"
    FALLBACK_TRANSPORT = "fallback_transport"
    FAIL = "fail"


@dataclass(frozen=True)
class RetryableResponseStreamDecision:
    action: RetryableResponseStreamAction
    retries: int
    delay: timedelta | None = None
    report_error: bool = False
    warning_message: str | None = None
    notify_message: str | None = None
    error: CodexErr | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", RetryableResponseStreamAction(self.action))
        if isinstance(self.retries, bool) or not isinstance(self.retries, int):
            raise TypeError("retries must be an integer")
        if self.retries < 0:
            raise ValueError("retries must be non-negative")
        if self.delay is not None and not isinstance(self.delay, timedelta):
            raise TypeError("delay must be a timedelta")
        if not isinstance(self.report_error, bool):
            raise TypeError("report_error must be a bool")
        if self.warning_message is not None and not isinstance(self.warning_message, str):
            raise TypeError("warning_message must be a string")
        if self.notify_message is not None and not isinstance(self.notify_message, str):
            raise TypeError("notify_message must be a string")
        if self.error is not None and not isinstance(self.error, CodexErr):
            raise TypeError("error must be a CodexErr")


def response_stream_retry_decision(
    *,
    retries: int,
    max_retries: int,
    err: CodexErr,
    request: ResponsesStreamRequest,
    fallback_transport_available: bool,
    responses_websocket_enabled: bool,
    debug_assertions: bool = __debug__,
) -> RetryableResponseStreamDecision:
    if isinstance(retries, bool) or not isinstance(retries, int):
        raise TypeError("retries must be an integer")
    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise TypeError("max_retries must be an integer")
    if retries < 0:
        raise ValueError("retries must be non-negative")
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    if not isinstance(err, CodexErr):
        raise TypeError("err must be a CodexErr")
    request = ResponsesStreamRequest(request)
    if not isinstance(fallback_transport_available, bool):
        raise TypeError("fallback_transport_available must be a bool")
    if not isinstance(responses_websocket_enabled, bool):
        raise TypeError("responses_websocket_enabled must be a bool")
    if not isinstance(debug_assertions, bool):
        raise TypeError("debug_assertions must be a bool")

    if retries >= max_retries and fallback_transport_available:
        return RetryableResponseStreamDecision(
            action=RetryableResponseStreamAction.FALLBACK_TRANSPORT,
            retries=0,
            warning_message=f"Falling back from WebSockets to HTTPS transport. {err}",
        )

    if retries < max_retries:
        next_retries = retries + 1
        delay = retry_delay_for_error(err, next_retries)
        report_error = next_retries > 1 or debug_assertions or not responses_websocket_enabled
        return RetryableResponseStreamDecision(
            action=RetryableResponseStreamAction.RETRY,
            retries=next_retries,
            delay=delay,
            report_error=report_error,
            notify_message=f"Reconnecting... {next_retries}/{max_retries}" if report_error else None,
        )

    return RetryableResponseStreamDecision(
        action=RetryableResponseStreamAction.FAIL,
        retries=retries,
        error=err,
    )


def retry_delay_for_error(err: CodexErr, retry_count: int) -> timedelta:
    if not isinstance(err, CodexErr):
        raise TypeError("err must be a CodexErr")
    if isinstance(retry_count, bool) or not isinstance(retry_count, int):
        raise TypeError("retry_count must be an integer")
    if retry_count <= 0:
        raise ValueError("retry_count must be positive")
    if err.kind == "stream":
        requested_delay = _requested_delay(err.payload)
        if requested_delay is not None:
            return requested_delay
    return backoff(retry_count)


def retry_log_message(
    request: ResponsesStreamRequest,
    *,
    retries: int,
    max_retries: int,
    delay: timedelta,
    err: CodexErr,
    turn_id: str | None = None,
) -> str:
    request = ResponsesStreamRequest(request)
    if request is ResponsesStreamRequest.SAMPLING:
        return f"stream disconnected - retrying sampling request ({retries}/{max_retries} in {delay})..."
    if turn_id is None:
        return "remote compaction v2 stream failed; retrying request after delay"
    return f"remote compaction v2 stream failed for turn {turn_id}; retrying request after delay: {err}"


def _requested_delay(value: object) -> timedelta | None:
    if value is None:
        return None
    if isinstance(value, timedelta):
        return value
    if isinstance(value, bool):
        raise TypeError("retry-after delay must not be a bool")
    if isinstance(value, int | float):
        if value < 0:
            raise ValueError("retry-after delay must be non-negative")
        return timedelta(seconds=float(value))
    raise TypeError("retry-after delay must be a timedelta or seconds")


__all__ = [
    "ResponsesStreamRequest",
    "RetryableResponseStreamAction",
    "RetryableResponseStreamDecision",
    "response_stream_retry_decision",
    "retry_delay_for_error",
    "retry_log_message",
]
