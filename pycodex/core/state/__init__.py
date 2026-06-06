"""State modules aligned with ``codex-rs/core/src/state``."""

from .additional_context import (
    AdditionalContextEntry,
    AdditionalContextKind,
    AdditionalContextStore,
)
from .session import SessionState

__all__ = [
    "AdditionalContextEntry",
    "AdditionalContextKind",
    "AdditionalContextStore",
    "SessionState",
]
