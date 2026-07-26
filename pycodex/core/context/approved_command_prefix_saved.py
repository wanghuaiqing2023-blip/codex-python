from __future__ import annotations

from dataclasses import dataclass

from .fragment import ContextualUserFragmentBase


@dataclass(frozen=True)
class ApprovedCommandPrefixSaved(ContextualUserFragmentBase):
    prefixes: str

    @classmethod
    def new(cls, prefixes: str) -> "ApprovedCommandPrefixSaved":
        return cls(prefixes)

    @classmethod
    def role(cls) -> str:
        return "developer"

    def body(self) -> str:
        return f"Approved command prefix saved:\n{self.prefixes}"


__all__ = ["ApprovedCommandPrefixSaved"]
