"""Generated thread-config loader server boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from . import LoadThreadConfigRequest, LoadThreadConfigResponse


class ThreadConfigLoader(Protocol):
    async def load(
        self,
        request: LoadThreadConfigRequest,
    ) -> LoadThreadConfigResponse: ...


@dataclass
class ThreadConfigLoaderServer:
    inner: ThreadConfigLoader
    max_decoding_size: int | None = None
    max_encoding_size: int | None = None

    @classmethod
    def new(cls, inner: ThreadConfigLoader) -> "ThreadConfigLoaderServer":
        return cls(inner)

    @classmethod
    def from_arc(cls, inner: ThreadConfigLoader) -> "ThreadConfigLoaderServer":
        return cls(inner)

    @classmethod
    def with_interceptor(
        cls,
        inner: ThreadConfigLoader,
        _interceptor: Any,
    ) -> "ThreadConfigLoaderServer":
        return cls(inner)

    def accept_compressed(self, _encoding: Any) -> "ThreadConfigLoaderServer":
        return self

    def send_compressed(self, _encoding: Any) -> "ThreadConfigLoaderServer":
        return self

    def max_decoding_message_size(self, limit: int) -> "ThreadConfigLoaderServer":
        self.max_decoding_size = int(limit)
        return self

    def max_encoding_message_size(self, limit: int) -> "ThreadConfigLoaderServer":
        self.max_encoding_size = int(limit)
        return self


SERVICE_NAME = "codex.thread_config.v1.ThreadConfigLoader"

__all__ = ["SERVICE_NAME", "ThreadConfigLoader", "ThreadConfigLoaderServer"]
