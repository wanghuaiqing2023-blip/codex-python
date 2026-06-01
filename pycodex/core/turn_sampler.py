"""Sampling adapters for user-turn runtime.

The user-turn runtime accepts an injected sampler so it does not need to own
HTTP/WebSocket transport. This module provides the first concrete adapter for
the already-ported ``ModelClientSession`` request-preparation boundary.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from pycodex.core.client import ModelClientSession
from pycodex.core.responses_retry import (
    ResponsesStreamRequest,
    RetryableResponseStreamAction,
    RetryableResponseStreamDecision,
    response_stream_retry_decision,
)
from pycodex.core.turn_runtime import UserTurnSamplingRequest
from pycodex.protocol import CodexErr, ResponseItem


TransportFn = Callable[["PreparedSamplingRequest"], Any | Awaitable[Any]]
SleepFn = Callable[[float], Any | Awaitable[Any]]
RetryDecisionFn = Callable[[RetryableResponseStreamDecision], Any | Awaitable[Any]]


@dataclass(frozen=True)
class PreparedSamplingRequest:
    """Prepared request handed to an injected transport."""

    sampling_request: UserTurnSamplingRequest
    prepared_request: dict[str, Any]
    mode: str = "http"


@dataclass(frozen=True)
class PreparedSamplingResult:
    """Transport result plus normalized response items."""

    prepared_request: dict[str, Any]
    response_items: tuple[ResponseItem, ...]
    raw_result: Any = None
    mode: str = "http"
    rate_limits: tuple[Any, ...] = ()
    server_model: str | None = None
    server_models: tuple[str, ...] = ()
    server_reasoning_included: bool | None = None
    models_etag: str | None = None
    model_verifications: tuple[Any, ...] = ()
    end_turn: bool | None = None
    stream_events: tuple[Any, ...] = ()


async def sample_with_model_client_session(
    sampling_request: UserTurnSamplingRequest,
    model_session: ModelClientSession,
    transport: TransportFn,
    *,
    mode: str = "http",
) -> PreparedSamplingResult:
    """Prepare a request through ``ModelClientSession`` and call transport."""

    if mode != "http":
        raise ValueError("only http sampling preparation is supported by this adapter")
    if not callable(transport):
        raise TypeError("transport must be callable")
    prepared_request = model_session.prepare_http_request(sampling_request.request_plan.request)
    raw_result = await _maybe_await(
        transport(
            PreparedSamplingRequest(
                sampling_request=sampling_request,
                prepared_request=prepared_request,
                mode=mode,
            )
        )
    )
    return PreparedSamplingResult(
        prepared_request=prepared_request,
        response_items=response_items_from_transport_result(raw_result),
        raw_result=raw_result,
        mode=mode,
        rate_limits=tuple(getattr(raw_result, "rate_limits", ()) or ()),
        server_model=getattr(raw_result, "server_model", None),
        server_models=tuple(getattr(raw_result, "server_models", ()) or ()),
        server_reasoning_included=getattr(raw_result, "server_reasoning_included", None),
        models_etag=getattr(raw_result, "models_etag", None),
        model_verifications=tuple(getattr(raw_result, "model_verifications", ()) or ()),
        end_turn=getattr(raw_result, "end_turn", None),
        stream_events=tuple(getattr(raw_result, "stream_events", ()) or ()),
    )


async def sample_with_model_client_session_retries(
    sampling_request: UserTurnSamplingRequest,
    model_session: ModelClientSession,
    transport: TransportFn,
    *,
    max_retries: int,
    fallback_transport: TransportFn | None = None,
    responses_websocket_enabled: bool = False,
    sleep: SleepFn | None = None,
    on_retry_decision: RetryDecisionFn | None = None,
    mode: str = "http",
    debug_assertions: bool = __debug__,
) -> PreparedSamplingResult:
    """Prepare and sample with Rust-shaped retry/fallback decisions.

    Transport functions should raise ``CodexErr`` for retryable stream-like
    failures. The default ``sample_with_model_client_session`` remains a
    single-attempt adapter; this helper mirrors the Rust sampling retry loop
    without taking ownership of UI notification side effects.
    """

    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise TypeError("max_retries must be an integer")
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    if fallback_transport is not None and not callable(fallback_transport):
        raise TypeError("fallback_transport must be callable")
    if sleep is not None and not callable(sleep):
        raise TypeError("sleep must be callable")
    if on_retry_decision is not None and not callable(on_retry_decision):
        raise TypeError("on_retry_decision must be callable")

    retries = 0
    current_transport = transport
    while True:
        try:
            return await sample_with_model_client_session(
                sampling_request,
                model_session,
                current_transport,
                mode=mode,
            )
        except CodexErr as err:
            if not err.is_retryable():
                raise
            decision = response_stream_retry_decision(
                retries=retries,
                max_retries=max_retries,
                err=err,
                request=ResponsesStreamRequest.SAMPLING,
                fallback_transport_available=fallback_transport is not None and current_transport is not fallback_transport,
                responses_websocket_enabled=responses_websocket_enabled,
                debug_assertions=debug_assertions,
            )
            if on_retry_decision is not None:
                await _maybe_await(on_retry_decision(decision))
            if decision.action is RetryableResponseStreamAction.RETRY:
                retries = decision.retries
                sleeper = sleep or _sleep_seconds
                if decision.delay is not None:
                    await _maybe_await(sleeper(decision.delay.total_seconds()))
                continue
            if decision.action is RetryableResponseStreamAction.FALLBACK_TRANSPORT and fallback_transport is not None:
                current_transport = fallback_transport
                retries = decision.retries
                continue
            raise decision.error or err


def response_items_from_transport_result(value: Any) -> tuple[ResponseItem, ...]:
    raw_items = getattr(value, "response_items", value)
    if raw_items is None:
        return ()
    if isinstance(raw_items, ResponseItem):
        return (raw_items,)
    if isinstance(raw_items, dict):
        return (ResponseItem.from_mapping(raw_items),)
    if isinstance(raw_items, (str, bytes)) or not isinstance(raw_items, Sequence):
        raise TypeError("transport result must be a ResponseItem, mapping, sequence, or expose response_items")
    items: list[ResponseItem] = []
    for item in raw_items:
        if isinstance(item, ResponseItem):
            items.append(item)
        elif isinstance(item, dict):
            items.append(ResponseItem.from_mapping(item))
        else:
            raise TypeError("transport response_items entries must be ResponseItem or mapping")
    return tuple(items)


async def _maybe_await(value: Any) -> Any:
    if isinstance(value, Awaitable) or inspect.isawaitable(value):
        return await value
    return value


async def _sleep_seconds(seconds: float) -> None:
    await asyncio.sleep(seconds)


__all__ = [
    "PreparedSamplingRequest",
    "PreparedSamplingResult",
    "RetryDecisionFn",
    "SleepFn",
    "TransportFn",
    "response_items_from_transport_result",
    "sample_with_model_client_session",
    "sample_with_model_client_session_retries",
]
