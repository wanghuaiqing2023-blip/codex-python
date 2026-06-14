"""Semantic port of codex-rs/tui/src/chatwidget/session_header.rs."""

from __future__ import annotations

from dataclasses import dataclass

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::session_header",
    source="codex/codex-rs/tui/src/chatwidget/session_header.rs",
)


@dataclass
class SessionHeader:
    """Stores the model text shown in the chat session header."""

    model: str

    @classmethod
    def new(cls, model: str) -> "SessionHeader":
        return cls(str(model))

    def set_model(self, model: str) -> None:
        model_text = str(model)
        if self.model != model_text:
            self.model = model_text


__all__ = [
    "RUST_MODULE",
    "SessionHeader",
]
