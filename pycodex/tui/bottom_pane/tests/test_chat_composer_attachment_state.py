"""Parity tests for Rust ``codex-tui::bottom_pane::chat_composer::attachment_state``."""

# Rust owner: codex-tui::bottom_pane::chat_composer::attachment_state.
# Rust source: codex/codex-rs/tui/src/bottom_pane/chat_composer/attachment_state.rs
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from pycodex.protocol.models import local_image_label_text
from pycodex.tui.bottom_pane.chat_composer.attachment_state import AttachmentState


class FakeTextArea:
    def __init__(self, cursor: int = 0) -> None:
        self._cursor = cursor
        self.inserted: List[str] = []
        self.replaced: List[Tuple[str, str]] = []

    def cursor(self) -> int:
        return self._cursor

    def insert_element(self, payload: str) -> None:
        self.inserted.append(payload)

    def replace_element_payload(self, current: str, expected: str) -> bool:
        self.replaced.append((current, expected))
        return True


@dataclass
class FakeTextElement:
    value: Optional[str]

    def placeholder(self, text: str) -> Optional[str]:
        return self.value


def test_remote_urls_offset_local_image_numbering_and_take_relabels() -> None:
    textarea = FakeTextArea()
    state = AttachmentState()

    state.set_remote_image_urls(["https://one", "https://two"], textarea)
    state.reset_local_images([Path("a.png"), Path("b.png")], textarea)

    assert [image.placeholder for image in state.local_images()] == [
        local_image_label_text(3),
        local_image_label_text(4),
    ]
    assert state.take_remote_image_urls(textarea) == ["https://one", "https://two"]
    assert [image.placeholder for image in state.local_images()] == [
        local_image_label_text(1),
        local_image_label_text(2),
    ]
    assert textarea.replaced[-2:] == [
        (local_image_label_text(3), local_image_label_text(1)),
        (local_image_label_text(4), local_image_label_text(2)),
    ]


def test_attach_image_inserts_placeholder_and_local_image_views_are_copies() -> None:
    textarea = FakeTextArea()
    state = AttachmentState()

    state.set_remote_image_urls(["remote"], textarea)
    state.attach_image(textarea, "local.png")

    assert textarea.inserted == [local_image_label_text(2)]
    assert state.local_image_paths() == [Path("local.png")]
    assert state.local_images()[0].placeholder == local_image_label_text(2)
    assert state.remote_image_urls() == ["remote"]


def test_prune_and_take_recent_submission_images() -> None:
    textarea = FakeTextArea()
    state = AttachmentState()
    state.reset_local_images([Path("a.png"), Path("b.png")], textarea)

    state.prune_local_images_for_submission(
        "text",
        [FakeTextElement(local_image_label_text(2))],
    )

    assert state.take_recent_submission_images() == [Path("b.png")]
    assert state.is_empty() is True


def test_take_recent_submission_images_with_placeholders_and_clear_remote_urls() -> None:
    textarea = FakeTextArea()
    state = AttachmentState()
    state.set_remote_image_urls(["remote"], textarea)
    state.reset_local_images([Path("a.png")], textarea)
    state.selected_remote_image_index = 0

    state.clear_remote_image_urls()

    assert state.remote_image_urls() == []
    assert state.selected_remote_image_index is None
    assert state.local_images()[0].placeholder == local_image_label_text(2)
    assert textarea.replaced == []

    images = state.take_recent_submission_images_with_placeholders()

    assert len(images) == 1
    assert images[0].placeholder == local_image_label_text(2)
    assert images[0].path == Path("a.png")
    assert state.local_images() == []
    assert state.is_empty() is True


def test_remove_deleted_local_placeholders_relabels_remaining_images() -> None:
    textarea = FakeTextArea()
    state = AttachmentState()
    state.reset_local_images([Path("a.png"), Path("b.png")], textarea)

    assert state.remove_deleted_local_placeholders([local_image_label_text(1)], textarea) is True
    assert [image.placeholder for image in state.local_images()] == [local_image_label_text(1)]
    assert textarea.replaced[-1] == (local_image_label_text(2), local_image_label_text(1))
    assert state.remove_deleted_local_placeholders(["missing"], textarea) is False


def test_remote_image_lines_selection_and_keyboard_navigation() -> None:
    textarea = FakeTextArea(cursor=0)
    state = AttachmentState()
    state.set_remote_image_urls(["one", "two"], textarea)

    assert state.handle_remote_image_selection_key({"code": "Up", "kind": "Press", "modifiers": "NONE"}, textarea) == ("None", True)
    assert state.selected_remote_image_index == 1
    assert [line.style for line in state.remote_image_lines()] == ["cyan", "cyan+reversed"]

    assert state.handle_remote_image_selection_key({"code": "Up", "kind": "Press", "modifiers": "NONE"}, textarea) == ("None", True)
    assert state.selected_remote_image_index == 0
    assert state.handle_remote_image_selection_key({"code": "Down", "kind": "Press", "modifiers": "NONE"}, textarea) == ("None", True)
    assert state.selected_remote_image_index == 1
    assert state.handle_remote_image_selection_key({"code": "Down", "kind": "Press", "modifiers": "NONE"}, textarea) == ("None", True)
    assert state.selected_remote_image_index is None


def test_remote_image_delete_relabels_local_images_and_rejects_modified_events() -> None:
    textarea = FakeTextArea(cursor=0)
    state = AttachmentState()
    state.set_remote_image_urls(["one"], textarea)
    state.reset_local_images([Path("a.png")], textarea)

    assert state.handle_remote_image_selection_key({"code": "Up", "kind": "Release", "modifiers": "NONE"}, textarea) is None
    assert state.handle_remote_image_selection_key({"code": "Up", "kind": "Press", "modifiers": "ALT"}, textarea) is None
    state.handle_remote_image_selection_key({"code": "Up", "kind": "Press", "modifiers": "NONE"}, textarea)
    assert state.handle_remote_image_selection_key({"code": "Delete", "kind": "Press", "modifiers": "NONE"}, textarea) == ("None", True)

    assert state.remote_image_urls() == []
    assert state.selected_remote_image_index is None
    assert state.local_images()[0].placeholder == local_image_label_text(1)

