"""Shared stream parser contract from Rust ``stream_text.rs``."""

from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar

T = TypeVar("T")


@dataclass
class StreamTextChunk(Generic[T]):
    visible_text: str = ""
    extracted: list[T] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.visible_text and not self.extracted


class StreamTextParser(Protocol[T]):
    def push_str(self, chunk: str) -> StreamTextChunk[T]:
        ...

    def finish(self) -> StreamTextChunk[T]:
        ...

