from datetime import timedelta
from pathlib import Path

from pycodex.tui.bottom_pane import (
    APPROVAL_PROMPT_TYPING_IDLE_DELAY,
    DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED,
    QUIT_SHORTCUT_TIMEOUT,
    CancellationEvent,
    LocalImageAttachment,
    MentionBinding,
)


def test_bottom_pane_module_constants_match_rust_defaults() -> None:
    """Rust: codex-tui bottom_pane/mod.rs duration and feature constants."""
    assert QUIT_SHORTCUT_TIMEOUT == timedelta(seconds=1)
    assert APPROVAL_PROMPT_TYPING_IDLE_DELAY == timedelta(seconds=1)
    assert DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED is False


def test_local_image_attachment_preserves_placeholder_and_path() -> None:
    """Rust: LocalImageAttachment owns placeholder text and image path."""
    path = Path("screenshots/example.png")
    attachment = LocalImageAttachment(placeholder="[image 1]", path=path)

    assert attachment.placeholder == "[image 1]"
    assert attachment.path == path


def test_mention_binding_preserves_mention_and_path() -> None:
    """Rust: MentionBinding carries the mention token and resolved path."""
    binding = MentionBinding(mention="@foo", path="src/foo.rs")

    assert binding.mention == "@foo"
    assert binding.path == "src/foo.rs"


def test_cancellation_event_variants_match_rust_enum() -> None:
    """Rust: CancellationEvent has handled and not-handled outcomes."""
    assert CancellationEvent.HANDLED.value == "handled"
    assert CancellationEvent.NOT_HANDLED.value == "not_handled"
