"""Generated thread-config loader client boundary."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from . import LoadThreadConfigRequest, LoadThreadConfigResponse


@dataclass
class ThreadConfigLoaderClient:
    inner: Callable[[LoadThreadConfigRequest], Any]
    origin: str | None = None
    interceptor: Callable[[LoadThreadConfigRequest], LoadThreadConfigRequest] | None = None
    max_decoding_size: int | None = None
    max_encoding_size: int | None = None

    @classmethod
    async def connect(cls, endpoint: Any) -> "ThreadConfigLoaderClient":
        connector = getattr(endpoint, "connect", None)
        inner = connector() if callable(connector) else endpoint
        if inspect.isawaitable(inner):
            inner = await inner
        if not callable(inner):
            raise TypeError("thread config endpoint must produce a callable transport")
        return cls(inner)

    @classmethod
    def new(cls, inner: Callable[[LoadThreadConfigRequest], Any]) -> "ThreadConfigLoaderClient":
        return cls(inner)

    @classmethod
    def with_origin(
        cls,
        inner: Callable[[LoadThreadConfigRequest], Any],
        origin: str,
    ) -> "ThreadConfigLoaderClient":
        return cls(inner, origin=str(origin))

    @classmethod
    def with_interceptor(
        cls,
        inner: Callable[[LoadThreadConfigRequest], Any],
        interceptor: Callable[[LoadThreadConfigRequest], LoadThreadConfigRequest],
    ) -> "ThreadConfigLoaderClient":
        return cls(inner, interceptor=interceptor)

    def send_compressed(self, _encoding: Any) -> "ThreadConfigLoaderClient":
        return self

    def accept_compressed(self, _encoding: Any) -> "ThreadConfigLoaderClient":
        return self

    def max_decoding_message_size(self, limit: int) -> "ThreadConfigLoaderClient":
        self.max_decoding_size = int(limit)
        return self

    def max_encoding_message_size(self, limit: int) -> "ThreadConfigLoaderClient":
        self.max_encoding_size = int(limit)
        return self

    async def load(
        self,
        request: LoadThreadConfigRequest,
    ) -> LoadThreadConfigResponse:
        value = self.interceptor(request) if self.interceptor is not None else request
        response = self.inner(value)
        if inspect.isawaitable(response):
            response = await response
        if isinstance(response, LoadThreadConfigResponse):
            return response
        if isinstance(response, dict):
            return LoadThreadConfigResponse(sources=list(response.get("sources", ())))
        raise TypeError("thread config transport returned an invalid response")


__all__ = ["ThreadConfigLoaderClient"]
