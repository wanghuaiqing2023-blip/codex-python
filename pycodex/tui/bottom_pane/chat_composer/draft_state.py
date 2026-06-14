"""Editable composer draft state.

Port of Rust ``codex-tui::bottom_pane::chat_composer::draft_state``.  This
module owns composer draft containers and defaults; the large ``textarea``
behavior remains a separate module boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..._porting import RustTuiModule
from ..paste_burst import PasteBurst
from ..textarea import TextArea, TextAreaState

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::chat_composer::draft_state",
    source="codex/codex-rs/tui/src/bottom_pane/chat_composer/draft_state.rs",
)


@dataclass
class ComposerMentionBinding:
    mention: str
    path: str


@dataclass
class DraftState:
    textarea: TextArea = field(default_factory=TextArea)
    textarea_state: TextAreaState = field(default_factory=TextAreaState)
    is_bash_mode: bool = False
    pending_pastes: list[tuple[str, str]] = field(default_factory=list)
    input_enabled: bool = True
    input_disabled_placeholder: str | None = None
    paste_burst: PasteBurst = field(default_factory=PasteBurst)
    disable_paste_burst: bool = False
    mention_bindings: dict[int, ComposerMentionBinding] = field(default_factory=dict)
    recent_submission_mention_bindings: list[Any] = field(default_factory=list)

    @classmethod
    def new(cls) -> "DraftState":
        return cls()


__all__ = [
    "ComposerMentionBinding",
    "DraftState",
    "RUST_MODULE",
]
