"""Python interface scaffold for Rust ``codex-tui::chatwidget::user_messages``.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/user_messages.rs``.
Concrete behavior should be filled in from the Rust source and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(crate="codex-tui", module="chatwidget::user_messages", source="codex/codex-rs/tui/src/chatwidget/user_messages.rs")

@dataclass
class UserMessage:
    """Python boundary for Rust ``chatwidget::user_messages::UserMessage``."""
    _payload: Any = None

class UserMessageHistoryRecord(Enum):
    """Python boundary for Rust enum ``chatwidget::user_messages::UserMessageHistoryRecord``."""
    UNPORTED = "unported"

@dataclass
class UserMessageHistoryOverride:
    """Python boundary for Rust ``chatwidget::user_messages::UserMessageHistoryOverride``."""
    _payload: Any = None

class ShellEscapePolicy(Enum):
    """Python boundary for Rust enum ``chatwidget::user_messages::ShellEscapePolicy``."""
    UNPORTED = "unported"

@dataclass
class QueuedUserMessage:
    """Python boundary for Rust ``chatwidget::user_messages::QueuedUserMessage``."""
    _payload: Any = None

    def new(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "QueuedUserMessage.new")

    def into_user_message(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "QueuedUserMessage.into_user_message")

def from_(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::user_messages::from``."""
    return not_ported(RUST_MODULE, "from")

Target: Any = None

def deref(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::user_messages::deref``."""
    return not_ported(RUST_MODULE, "deref")

class QueueDrain(Enum):
    """Python boundary for Rust enum ``chatwidget::user_messages::QueueDrain``."""
    UNPORTED = "unported"

@dataclass
class ThreadComposerState:
    """Python boundary for Rust ``chatwidget::user_messages::ThreadComposerState``."""
    _payload: Any = None

    def has_content(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "ThreadComposerState.has_content")

@dataclass
class ThreadInputState:
    """Python boundary for Rust ``chatwidget::user_messages::ThreadInputState``."""
    _payload: Any = None

@dataclass
class PendingSteer:
    """Python boundary for Rust ``chatwidget::user_messages::PendingSteer``."""
    _payload: Any = None

def create_initial_user_message(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::user_messages::create_initial_user_message``."""
    return not_ported(RUST_MODULE, "create_initial_user_message")

def append_text_with_rebased_elements(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::user_messages::append_text_with_rebased_elements``."""
    return not_ported(RUST_MODULE, "append_text_with_rebased_elements")

def app_server_text_elements(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::user_messages::app_server_text_elements``."""
    return not_ported(RUST_MODULE, "app_server_text_elements")

def build_placeholder_mapping(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::user_messages::build_placeholder_mapping``."""
    return not_ported(RUST_MODULE, "build_placeholder_mapping")

def remap_placeholders_in_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::user_messages::remap_placeholders_in_text``."""
    return not_ported(RUST_MODULE, "remap_placeholders_in_text")

def remap_placeholders_for_message_and_history_record(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::user_messages::remap_placeholders_for_message_and_history_record``."""
    return not_ported(RUST_MODULE, "remap_placeholders_for_message_and_history_record")

def remap_placeholders_for_message(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::user_messages::remap_placeholders_for_message``."""
    return not_ported(RUST_MODULE, "remap_placeholders_for_message")

def remap_user_messages_with_history_records(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::user_messages::remap_user_messages_with_history_records``."""
    return not_ported(RUST_MODULE, "remap_user_messages_with_history_records")

def merge_user_messages(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::user_messages::merge_user_messages``."""
    return not_ported(RUST_MODULE, "merge_user_messages")

def merge_remapped_user_messages(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::user_messages::merge_remapped_user_messages``."""
    return not_ported(RUST_MODULE, "merge_remapped_user_messages")

def user_message_for_restore(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::user_messages::user_message_for_restore``."""
    return not_ported(RUST_MODULE, "user_message_for_restore")

def user_message_preview_text(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::user_messages::user_message_preview_text``."""
    return not_ported(RUST_MODULE, "user_message_preview_text")

def user_message_display_for_history(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::user_messages::user_message_display_for_history``."""
    return not_ported(RUST_MODULE, "user_message_display_for_history")

def merge_user_messages_with_history_record(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``chatwidget::user_messages::merge_user_messages_with_history_record``."""
    return not_ported(RUST_MODULE, "merge_user_messages_with_history_record")

@dataclass
class UserMessageDisplay:
    """Python boundary for Rust ``chatwidget::user_messages::UserMessageDisplay``."""
    _payload: Any = None

@dataclass
class PendingSteerCompareKey:
    """Python boundary for Rust ``chatwidget::user_messages::PendingSteerCompareKey``."""
    _payload: Any = None

__all__ = [
    "PendingSteer",
    "PendingSteerCompareKey",
    "QueueDrain",
    "QueuedUserMessage",
    "RUST_MODULE",
    "ShellEscapePolicy",
    "Target",
    "ThreadComposerState",
    "ThreadInputState",
    "UserMessage",
    "UserMessageDisplay",
    "UserMessageHistoryOverride",
    "UserMessageHistoryRecord",
    "app_server_text_elements",
    "append_text_with_rebased_elements",
    "build_placeholder_mapping",
    "create_initial_user_message",
    "deref",
    "from_",
    "merge_remapped_user_messages",
    "merge_user_messages",
    "merge_user_messages_with_history_record",
    "remap_placeholders_for_message",
    "remap_placeholders_for_message_and_history_record",
    "remap_placeholders_in_text",
    "remap_user_messages_with_history_records",
    "user_message_display_for_history",
    "user_message_for_restore",
    "user_message_preview_text",
]
