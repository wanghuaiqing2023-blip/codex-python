"""Rust integration parity for ``core/tests/suite/image_rollout.rs``.

The Rust suite drives a mocked Codex turn and then asserts the user image
message shape persisted in the rollout.  Python keeps the same observable
contract at the rollout payload boundary: user image inputs are converted,
persisted, and read back as the same ``ResponseItem`` content sequence.
"""

from __future__ import annotations

from pathlib import Path

from pycodex.exec.local_runtime import _local_http_input_rollout_payload
from pycodex.protocol import (
    DEFAULT_IMAGE_DETAIL,
    ContentItem,
    ResponseItem,
    UserInput,
    image_close_tag_text,
    local_image_open_tag_text,
)
from pycodex.rollout import append_turn_to_rollout, read_response_items_from_rollout


PNG_1X1_RGBA = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _persisted_user_message(tmp_path: Path, input_items: tuple[UserInput, ...]) -> ResponseItem:
    payload = _local_http_input_rollout_payload(input_items)
    assert payload is not None

    rollout_path = tmp_path / "rollout.jsonl"
    append_turn_to_rollout(
        rollout_path,
        payload,
        (),
        timestamp="2026-06-11T00:00:00Z",
        cwd=tmp_path,
    )

    user_messages = [
        item
        for item in read_response_items_from_rollout(rollout_path)
        if item.type == "message"
        and item.role == "user"
        and any(content.type == "input_image" for content in item.content)
    ]
    assert len(user_messages) == 1
    return user_messages[0]


def test_copy_paste_local_image_persists_rollout_request_shape(tmp_path: Path) -> None:
    """Rust: ``copy_paste_local_image_persists_rollout_request_shape``."""

    image_path = tmp_path / "images" / "paste.png"
    image_path.parent.mkdir()
    image_path.write_bytes(PNG_1X1_RGBA)

    actual = _persisted_user_message(
        tmp_path,
        (
            UserInput.local_image(image_path),
            UserInput.text_input("pasted image"),
        ),
    )
    image_url = next(content.image_url for content in actual.content if content.type == "input_image")

    assert actual == ResponseItem.message(
        "user",
        (
            ContentItem.input_text(local_image_open_tag_text(1)),
            ContentItem.input_image(image_url or "", detail=DEFAULT_IMAGE_DETAIL),
            ContentItem.input_text(image_close_tag_text()),
            ContentItem.input_text("pasted image"),
        ),
    )
    assert image_url is not None
    assert image_url.startswith("data:image/png;base64,")


def test_drag_drop_image_persists_rollout_request_shape(tmp_path: Path) -> None:
    """Rust: ``drag_drop_image_persists_rollout_request_shape``."""

    image_url = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
    )

    actual = _persisted_user_message(
        tmp_path,
        (
            UserInput.image(image_url),
            UserInput.text_input("dropped image"),
        ),
    )

    assert actual == ResponseItem.message(
        "user",
        (
            ContentItem.input_image(image_url, detail=DEFAULT_IMAGE_DETAIL),
            ContentItem.input_text("dropped image"),
        ),
    )
