"""Popup lifecycle state for the chat composer.

Port of Rust ``codex-tui::bottom_pane::chat_composer::popup_state``.  The
contained popup payloads are intentionally duck-typed because each popup's
behavior is owned by its own Rust module boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::chat_composer::popup_state",
    source="codex/codex-rs/tui/src/bottom_pane/chat_composer/popup_state.rs",
)


@dataclass(frozen=True)
class ActivePopup:
    """Semantic equivalent of Rust ``ActivePopup``."""

    kind: str = "None"
    value: Any = None

    @classmethod
    def none(cls) -> "ActivePopup":
        return cls("None")

    @classmethod
    def command(cls, popup: Any) -> "ActivePopup":
        return cls("Command", popup)

    @classmethod
    def file(cls, popup: Any) -> "ActivePopup":
        return cls("File", popup)

    @classmethod
    def skill(cls, popup: Any) -> "ActivePopup":
        return cls("Skill", popup)

    @classmethod
    def mention_v2(cls, popup: Any) -> "ActivePopup":
        return cls("MentionV2", popup)

    def is_none(self) -> bool:
        return self.kind == "None"


@dataclass
class PopupState:
    active_popup: ActivePopup = ActivePopup.none()
    dismissed_file_token: str | None = None
    current_file_query: str | None = None
    dismissed_mention_token: str | None = None

    # Rust field name is `active`; Python keeps the method name by storing the
    # field as `active_popup`.
    def active(self) -> bool:
        return not self.active_popup.is_none()


__all__ = [
    "ActivePopup",
    "PopupState",
    "RUST_MODULE",
]
