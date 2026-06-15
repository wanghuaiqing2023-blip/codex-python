"""Startup error types for ``codex-tui::startup_error``.

Rust source: ``codex/codex-rs/tui/src/startup_error.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="startup_error",
    source="codex/codex-rs/tui/src/startup_error.rs",
    status="complete",
)


@dataclass(eq=True)
class LocalStateDbStartupError(Exception):
    state_db_path_value: Path
    detail_value: str

    @classmethod
    def new(cls, state_db_path: str | Path, detail: str) -> "LocalStateDbStartupError":
        return cls(Path(state_db_path), str(detail))

    def state_db_path(self) -> Path:
        return self.state_db_path_value

    def detail(self) -> str:
        return self.detail_value

    def __str__(self) -> str:
        return f"failed to initialize sqlite state db at {self.state_db_path_value}: {self.detail_value}"


__all__ = [
    "LocalStateDbStartupError",
    "RUST_MODULE",
]
