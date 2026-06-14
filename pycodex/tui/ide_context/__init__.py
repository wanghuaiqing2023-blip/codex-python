"""Python interface scaffold for Rust ``codex-tui::ide_context``.

Upstream source: ``codex/codex-rs/tui/src/ide_context.rs``.
Concrete behavior should be filled in from the Rust source and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(crate="codex-tui", module="ide_context", source="codex/codex-rs/tui/src/ide_context.rs")

@dataclass
class IdeContext:
    """Python boundary for Rust ``ide_context::IdeContext``."""
    _payload: Any = None

@dataclass
class ActiveFile:
    """Python boundary for Rust ``ide_context::ActiveFile``."""
    _payload: Any = None

@dataclass
class FileDescriptor:
    """Python boundary for Rust ``ide_context::FileDescriptor``."""
    _payload: Any = None

@dataclass
class Range:
    """Python boundary for Rust ``ide_context::Range``."""
    _payload: Any = None

@dataclass
class Position:
    """Python boundary for Rust ``ide_context::Position``."""
    _payload: Any = None

def deserializes_existing_ide_context_shape(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``ide_context::deserializes_existing_ide_context_shape``."""
    return not_ported(RUST_MODULE, "deserializes_existing_ide_context_shape")

__all__ = [
    "ActiveFile",
    "FileDescriptor",
    "IdeContext",
    "Position",
    "RUST_MODULE",
    "Range",
    "deserializes_existing_ide_context_shape",
]
