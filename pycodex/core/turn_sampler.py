"""Sampling adapters for user-turn runtime.

The user-turn runtime accepts an injected sampler so it does not need to own
HTTP/WebSocket transport. This module provides the first concrete adapter for
the already-ported ``ModelClientSession`` request-preparation boundary.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pycodex.core.client import ModelClientSession
from pycodex.core.turn_runtime import UserTurnSamplingRequest
from pycodex.protocol import ResponseItem


TransportFn = Callable[["PreparedSamplingRequest"], Any | Awaitable[Any]]


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
    )


def response_items_from_transport_result(value: Any) -> tuple[ResponseItem, ...]:
    raw_items = getattr(value, "response_items", value)
    if raw_items is None:
        return ()
    if isinstance(raw_items, ResponseItem):
        return (raw_items,)
    if isinstance(raw_items, dict):
        return (ResponseItem.from_mapping(raw_items),)
    if isinstance(raw_items, (str, bytes)) or not isinstance(raw_items, (list, tuple)):
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


__all__ = [
    "PreparedSamplingRequest",
    "PreparedSamplingResult",
    "TransportFn",
    "response_items_from_transport_result",
    "sample_with_model_client_session",
]
