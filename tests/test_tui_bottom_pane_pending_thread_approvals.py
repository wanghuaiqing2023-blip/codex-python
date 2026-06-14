"""Parity tests for Rust ``codex-tui::bottom_pane::pending_thread_approvals``."""

from pycodex.tui.bottom_pane.pending_thread_approvals import (
    PendingThreadApprovals,
    Rect,
    RenderedLine,
    snapshot_rows,
)


def test_set_threads_reports_changes_and_is_empty_tracks_state() -> None:
    widget = PendingThreadApprovals.new()

    assert widget.is_empty() is True
    assert widget.set_threads(["Robie [explorer]"]) is True
    assert widget.is_empty() is False
    assert widget.threads() == ("Robie [explorer]",)
    assert widget.set_threads(["Robie [explorer]"]) is False


def test_set_threads_takes_an_owned_snapshot_of_thread_names() -> None:
    widget = PendingThreadApprovals.new()
    source = ["Main [default]"]

    assert widget.set_threads(source) is True
    source.append("Robie [explorer]")

    assert widget.threads() == ("Main [default]",)


def test_desired_height_empty_and_width_too_narrow() -> None:
    # Rust test: desired_height_empty.
    widget = PendingThreadApprovals.new()

    assert widget.desired_height(40) == 0
    widget.set_threads(["Robie [explorer]"])
    assert widget.desired_height(3) == 0


def test_render_single_thread_snapshot_visible_text() -> None:
    # Rust test: render_single_thread_snapshot.
    widget = PendingThreadApprovals.new()
    widget.set_threads(["Robie [explorer]"])

    assert [line.text for line in widget.as_renderable(40)] == [
        "  ! Approval needed in Robie [explorer]",
        "    /agent to switch threads",
    ]
    assert snapshot_rows(widget, 40).replace(" ", ".") == "\n".join(
        [
            "..!.Approval.needed.in.Robie.[explorer].",
            "..../agent.to.switch.threads............",
        ]
    )


def test_render_multiple_threads_limits_to_three_and_adds_switch_hint() -> None:
    # Rust test: render_multiple_threads_snapshot.
    widget = PendingThreadApprovals.new()
    widget.set_threads(["Main [default]", "Robie [explorer]", "Inspector", "Extra agent"])

    assert [line.text for line in widget.as_renderable(44)] == [
        "  ! Approval needed in Main [default]",
        "  ! Approval needed in Robie [explorer]",
        "  ! Approval needed in Inspector",
        "    ...",
        "    /agent to switch threads",
    ]


def test_render_clips_to_area_height() -> None:
    widget = PendingThreadApprovals.new()
    widget.set_threads(["Main [default]", "Robie [explorer]"])
    rendered: list[RenderedLine] = []

    widget.render(Rect(0, 0, 44, 1), rendered)

    assert [line.text for line in rendered] == ["  ! Approval needed in Main [default]"]
