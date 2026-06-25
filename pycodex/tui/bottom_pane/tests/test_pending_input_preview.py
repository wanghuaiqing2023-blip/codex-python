"""Parity tests for Rust ``codex-tui::bottom_pane::pending_input_preview``."""

from typing import List

from pycodex.tui.bottom_pane.pending_input_preview import (
    CONTINUATION_PREFIX,
    ITEM_PREFIX,
    OVERFLOW_PREFIX,
    PREVIEW_LINE_LIMIT,
    PendingInputPreview,
    Rect,
    RenderedLine,
    SECTION_PREFIX,
)


def test_desired_height_empty_and_width_too_narrow() -> None:
    # Rust test: desired_height_empty.
    queue = PendingInputPreview.new()

    assert queue.desired_height(40) == 0
    queue.queued_messages.append("Hello, world!")
    assert queue.desired_height(3) == 0


def test_desired_height_one_message() -> None:
    # Rust test: desired_height_one_message.
    queue = PendingInputPreview.new()
    queue.queued_messages.append("Hello, world!")

    assert queue.desired_height(40) == 3
    assert [line.text for line in queue.as_renderable(40)] == [
        f"{SECTION_PREFIX}Queued follow-up inputs",
        f"{ITEM_PREFIX}Hello, world!",
        "    ⌥ + ↑ edit last queued message",
    ]


def test_render_one_message_with_remapped_edit_binding_and_height_clip() -> None:
    # Rust snapshot behavior: hint line reflects caller-provided edit binding.
    queue = PendingInputPreview.new()
    queue.queued_messages.append("Hello, world!")
    queue.set_edit_binding("Shift+Left")
    rendered: List[RenderedLine] = []

    queue.render(Rect(0, 0, 40, 2), rendered)

    assert [line.text for line in rendered] == [
        f"{SECTION_PREFIX}Queued follow-up inputs",
        f"{ITEM_PREFIX}Hello, world!",
    ]
    assert queue.as_renderable(40)[-1].text == "    Shift+Left edit last queued message"


def test_render_more_than_three_wrapped_message_lines_adds_overflow_marker() -> None:
    # Rust behavior: each queued message contributes at most PREVIEW_LINE_LIMIT
    # wrapped preview lines, then an ellipsis overflow row.
    queue = PendingInputPreview.new()
    queue.queued_messages.append("This is\na message\nwith many\nlines")
    texts = [line.text for line in queue.as_renderable(40)]

    assert PREVIEW_LINE_LIMIT == 3
    assert texts == [
        f"{SECTION_PREFIX}Queued follow-up inputs",
        f"{ITEM_PREFIX}This is",
        f"{CONTINUATION_PREFIX}a message",
        f"{CONTINUATION_PREFIX}with many",
        OVERFLOW_PREFIX,
        "    ⌥ + ↑ edit last queued message",
    ]


def test_long_url_like_message_does_not_expand_into_wrapped_ellipsis_rows() -> None:
    # Rust test: long_url_like_message_does_not_expand_into_wrapped_ellipsis_rows.
    queue = PendingInputPreview.new()
    queue.queued_messages.append(
        "example.test/api/v1/projects/alpha-team/releases/2026-02-17/builds/1234567890/artifacts"
    )

    lines = queue.as_renderable(36)

    assert len(lines) == 3
    assert not any(line.text == OVERFLOW_PREFIX for line in lines)


def test_pending_steers_render_above_rejected_and_queued_messages() -> None:
    # Rust test: render_pending_steers_above_queued_messages.
    queue = PendingInputPreview.new()
    queue.pending_steers.extend(["Please continue.", "Check output."])
    queue.rejected_steers.append("Rejected steer.")
    queue.queued_messages.append("Queued follow-up question")
    texts = [line.text for line in queue.as_renderable(80)]

    assert texts[:3] == [
        f"{SECTION_PREFIX}Messages to be submitted after next tool call (press esc to interrupt and send immediately)",
        f"{ITEM_PREFIX}Please continue.",
        f"{ITEM_PREFIX}Check output.",
    ]
    rejected_header = f"{SECTION_PREFIX}Messages to be submitted at end of turn"
    queued_header = f"{SECTION_PREFIX}Queued follow-up inputs"
    assert rejected_header in texts
    assert queued_header in texts
    assert texts.index(rejected_header) < texts.index(queued_header)


def test_pending_interrupt_binding_can_be_hidden_or_remapped() -> None:
    queue = PendingInputPreview.new()
    queue.pending_steers.append("Please continue.")
    queue.set_interrupt_binding("F12")
    assert "press F12" in queue.as_renderable(80)[0].text

    queue.set_interrupt_binding(None)
    assert queue.as_renderable(80)[0].text == f"{SECTION_PREFIX}Messages to be submitted after next tool call"


def test_edit_hint_only_appears_for_queued_messages() -> None:
    queue = PendingInputPreview.new()
    queue.pending_steers.append("Please continue.")
    assert "edit last queued message" not in "\n".join(line.text for line in queue.as_renderable(80))

    queue.queued_messages.append("Follow up")
    assert "edit last queued message" in queue.as_renderable(80)[-1].text


def test_edit_binding_none_hides_queued_message_hint() -> None:
    # Rust source: the bottom hint is guarded by queued_messages and
    # Some(edit_binding); queued messages alone are not enough.
    queue = PendingInputPreview.new()
    queue.queued_messages.append("Follow up")
    queue.set_edit_binding(None)

    texts = [line.text for line in queue.as_renderable(80)]

    assert texts == [
        f"{SECTION_PREFIX}Queued follow-up inputs",
        f"{ITEM_PREFIX}Follow up",
    ]


def test_render_empty_area_is_noop() -> None:
    # Rust source: render returns before building the paragraph when area is
    # empty.
    queue = PendingInputPreview.new()
    queue.queued_messages.append("Follow up")
    rendered: List[RenderedLine] = []

    queue.render(Rect(0, 0, 0, 10), rendered)
    queue.render(Rect(0, 0, 80, 0), rendered)

    assert rendered == []

