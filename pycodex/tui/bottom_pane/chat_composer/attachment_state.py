"""Attachment bookkeeping for the chat composer.

Port of Rust ``codex-tui::bottom_pane::chat_composer::attachment_state``.
The module is intentionally independent from the full textarea implementation:
callers provide any object with the small ``insert_element``,
``replace_element_payload``, and ``cursor`` methods used here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pycodex.protocol.models import local_image_label_text

from ... import LocalImageAttachment
from ..._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::chat_composer::attachment_state",
    source="codex/codex-rs/tui/src/bottom_pane/chat_composer/attachment_state.rs",
)


@dataclass
class AttachedImage:
    placeholder: str
    path: Path


@dataclass(frozen=True)
class RemoteImageLine:
    text: str
    style: str = "cyan"


@dataclass
class AttachmentState:
    local_images_: list[AttachedImage] = field(default_factory=list)
    remote_image_urls_: list[str] = field(default_factory=list)
    selected_remote_image_index: int | None = None

    def is_empty(self) -> bool:
        return not self.local_images_ and not self.remote_image_urls_

    def local_image_paths(self) -> list[Path]:
        return [image.path for image in self.local_images_]

    def local_images(self) -> list[LocalImageAttachment]:
        return [
            LocalImageAttachment(placeholder=image.placeholder, path=image.path)
            for image in self.local_images_
        ]

    def set_remote_image_urls(self, urls: list[str], textarea: Any) -> None:
        self.remote_image_urls_ = list(urls)
        self.selected_remote_image_index = None
        self.relabel_local_images(textarea)

    def remote_image_urls(self) -> list[str]:
        return list(self.remote_image_urls_)

    def take_remote_image_urls(self, textarea: Any) -> list[str]:
        urls = self.remote_image_urls_
        self.remote_image_urls_ = []
        self.selected_remote_image_index = None
        self.relabel_local_images(textarea)
        return urls

    def clear_remote_image_urls(self) -> None:
        self.remote_image_urls_.clear()
        self.selected_remote_image_index = None

    def reset_local_images(self, local_image_paths: list[Path | str], textarea: Any) -> None:
        self.local_images_.clear()
        self.local_images_.extend(
            AttachedImage(
                placeholder=local_image_label_text(len(self.remote_image_urls_) + index + 1),
                path=Path(path),
            )
            for index, path in enumerate(local_image_paths)
        )
        self.selected_remote_image_index = None
        self.relabel_local_images(textarea)

    def attach_image(self, textarea: Any, path: Path | str) -> None:
        image_number = len(self.remote_image_urls_) + len(self.local_images_) + 1
        placeholder = local_image_label_text(image_number)
        textarea.insert_element(placeholder)
        self.local_images_.append(AttachedImage(placeholder=placeholder, path=Path(path)))

    def prune_local_images_for_submission(self, text: str, text_elements: list[Any]) -> None:
        if not self.local_images_:
            return
        placeholders = {
            placeholder
            for element in text_elements
            for placeholder in [_element_placeholder(element, text)]
            if placeholder is not None
        }
        self.local_images_ = [
            image for image in self.local_images_ if image.placeholder in placeholders
        ]

    def take_recent_submission_images(self) -> list[Path]:
        images = self.local_images_
        self.local_images_ = []
        return [image.path for image in images]

    def take_recent_submission_images_with_placeholders(self) -> list[LocalImageAttachment]:
        images = self.local_images_
        self.local_images_ = []
        return [
            LocalImageAttachment(placeholder=image.placeholder, path=image.path)
            for image in images
        ]

    def remote_image_lines(self) -> list[RemoteImageLine]:
        lines: list[RemoteImageLine] = []
        for index, _url in enumerate(self.remote_image_urls_):
            selected = self.selected_remote_image_index == index
            lines.append(
                RemoteImageLine(
                    text=local_image_label_text(index + 1),
                    style="cyan+reversed" if selected else "cyan",
                )
            )
        return lines

    def clear_remote_image_selection(self) -> None:
        self.selected_remote_image_index = None

    def handle_remote_image_selection_key(self, key_event: Any, textarea: Any) -> tuple[str, bool] | None:
        if (
            not self.remote_image_urls_
            or _key_modifiers(key_event) not in (None, "", "NONE")
            or _key_kind(key_event) != "Press"
        ):
            return None

        code = _key_code(key_event)
        if code == "Up":
            if self.selected_remote_image_index is not None:
                self.selected_remote_image_index = max(self.selected_remote_image_index - 1, 0)
                return ("None", True)
            if textarea.cursor() == 0:
                self.selected_remote_image_index = len(self.remote_image_urls_) - 1
                return ("None", True)
            return None

        if code == "Down":
            if self.selected_remote_image_index is None:
                return None
            if self.selected_remote_image_index + 1 < len(self.remote_image_urls_):
                self.selected_remote_image_index += 1
            else:
                self.clear_remote_image_selection()
            return ("None", True)

        if code in {"Delete", "Backspace"}:
            if self.selected_remote_image_index is None:
                return None
            self.remove_selected_remote_image(self.selected_remote_image_index, textarea)
            return ("None", True)

        return None

    def remove_deleted_local_placeholders(self, removed_payloads: list[str], textarea: Any) -> bool:
        previous_len = len(self.local_images_)
        removed = set(removed_payloads)
        self.local_images_ = [
            image for image in self.local_images_ if image.placeholder not in removed
        ]
        removed_any = len(self.local_images_) != previous_len
        if removed_any:
            self.relabel_local_images(textarea)
        return removed_any

    def relabel_local_images(self, textarea: Any) -> None:
        for index, image in enumerate(self.local_images_):
            expected = local_image_label_text(len(self.remote_image_urls_) + index + 1)
            if image.placeholder == expected:
                continue
            current = image.placeholder
            image.placeholder = expected
            textarea.replace_element_payload(current, expected)

    def remove_selected_remote_image(self, selected_index: int, textarea: Any) -> None:
        if selected_index >= len(self.remote_image_urls_):
            self.clear_remote_image_selection()
            return
        del self.remote_image_urls_[selected_index]
        self.selected_remote_image_index = (
            None
            if not self.remote_image_urls_
            else min(selected_index, len(self.remote_image_urls_) - 1)
        )
        self.relabel_local_images(textarea)


def _element_placeholder(element: Any, text: str) -> str | None:
    placeholder = getattr(element, "placeholder", None)
    if callable(placeholder):
        return placeholder(text)
    return placeholder


def _key_code(event: Any) -> str:
    return _event_field(event, "code")


def _key_kind(event: Any) -> str:
    return _event_field(event, "kind", "Press")


def _key_modifiers(event: Any) -> str | None:
    return _event_field(event, "modifiers", "NONE")


def _event_field(event: Any, name: str, default: Any = None) -> Any:
    if isinstance(event, dict):
        return event.get(name, default)
    return getattr(event, name, default)


__all__ = [
    "AttachedImage",
    "AttachmentState",
    "RUST_MODULE",
    "RemoteImageLine",
]
