from types import SimpleNamespace

from pycodex.tui.pager_overlay import (
    MAX_SCROLL,
    LiveTailKey,
    Rect,
    StaticOverlay,
    TextRenderable,
    TranscriptOverlay,
    pager_view,
    paragraph_block,
    transcript_overlay,
)
from pycodex.tui.line_truncation import Line
from pycodex.tui.terminal_hyperlinks import HyperlinkLine


def test_transcript_overlay_renders_live_tail() -> None:
    """Rust codex-tui::pager_overlay::tests::transcript_overlay_renders_live_tail."""

    overlay = transcript_overlay([TextRenderable(["alpha"])])
    overlay.sync_live_tail(
        40,
        LiveTailKey(width=40, revision=1, is_stream_continuation=False),
        lambda _width: ["tail"],
    )

    lines = overlay.render(Rect(0, 0, 40, 10))

    assert "alpha" in lines
    assert "tail" in lines


def test_transcript_overlay_sync_live_tail_is_noop_for_identical_key() -> None:
    """Rust codex-tui::pager_overlay::tests::transcript_overlay_sync_live_tail_is_noop_for_identical_key."""

    overlay = transcript_overlay([TextRenderable(["alpha"])])
    calls = 0

    def build(_width: int) -> list[str]:
        nonlocal calls
        calls += 1
        return [f"tail-{calls}"]

    key = {"revision": 1, "is_stream_continuation": False, "animation_tick": None}
    overlay.sync_live_tail(40, key, build)
    overlay.sync_live_tail(40, key, build)

    assert calls == 1
    assert overlay.live_tail_key == LiveTailKey(40, 1, False, None)
    assert overlay.render(Rect(0, 0, 40, 10)).count("tail-1") == 1


def test_transcript_overlay_live_tail_rebuilds_when_width_or_revision_changes() -> None:
    """Rust source contract: ActiveCellTranscriptKey includes width, revision, continuation, and animation tick."""

    overlay = transcript_overlay([])
    calls: list[int] = []

    def build(width: int) -> list[str]:
        calls.append(width)
        return [f"tail width {width}"]

    key = SimpleNamespace(revision=1, is_stream_continuation=False, animation_tick=None)
    overlay.sync_live_tail(40, key, build)
    overlay.sync_live_tail(50, key, build)
    overlay.sync_live_tail(50, SimpleNamespace(revision=2, is_stream_continuation=False), build)

    assert calls == [40, 50, 50]
    assert overlay.live_tail_key == LiveTailKey(50, 2, False, None)


def test_transcript_overlay_keeps_scroll_pinned_at_bottom() -> None:
    """Rust codex-tui::pager_overlay::tests::transcript_overlay_keeps_scroll_pinned_at_bottom."""

    overlay = transcript_overlay([TextRenderable([f"line{i}"]) for i in range(20)])
    area = Rect(0, 0, 40, 12)

    overlay.render(area)
    assert overlay.view.is_scrolled_to_bottom()

    overlay.insert_cell(TextRenderable(["tail"]))

    assert overlay.view.scroll_offset == MAX_SCROLL
    visible = overlay.render(area)
    assert "tail" in visible


def test_transcript_overlay_preserves_manual_scroll_position() -> None:
    """Rust codex-tui::pager_overlay::tests::transcript_overlay_preserves_manual_scroll_position."""

    overlay = transcript_overlay([TextRenderable([f"line{i}"]) for i in range(20)])
    area = Rect(0, 0, 40, 12)
    overlay.render(area)
    overlay.view.scroll_offset = 0

    overlay.insert_cell(TextRenderable(["tail"]))

    assert overlay.view.scroll_offset == 0
    visible = overlay.render(area)
    assert visible[0] == "line0"
    assert "tail" not in visible


def test_transcript_overlay_consolidation_remaps_highlight_inside_range() -> None:
    """Rust codex-tui::pager_overlay::tests::transcript_overlay_consolidation_remaps_highlight_inside_range."""

    overlay = transcript_overlay([TextRenderable([f"line{i}"]) for i in range(6)])
    overlay.set_highlight_cell(3)

    overlay.consolidate_cells(range(2, 5), TextRenderable(["consolidated"]))

    assert overlay.highlight_cell == 2
    assert overlay.committed_cell_count() == 4


def test_transcript_overlay_consolidation_remaps_highlight_after_range() -> None:
    """Rust codex-tui::pager_overlay::tests::transcript_overlay_consolidation_remaps_highlight_after_range."""

    overlay = transcript_overlay([TextRenderable([f"line{i}"]) for i in range(7)])
    overlay.set_highlight_cell(6)

    overlay.consolidate_cells(range(2, 5), TextRenderable(["consolidated"]))

    assert overlay.highlight_cell == 4
    assert overlay.committed_cell_count() == 5


def _visible_line_numbers(overlay: TranscriptOverlay, area: Rect) -> list[int]:
    lines = overlay.render(area)
    numbers: list[int] = []
    for line in lines:
        for token in line.split():
            if token.startswith("line-"):
                numbers.append(int(token.removeprefix("line-")))
    return numbers


def test_transcript_overlay_paging_is_continuous_and_round_trips() -> None:
    """Rust codex-tui::pager_overlay::tests::transcript_overlay_paging_is_continuous_and_round_trips."""

    overlay = transcript_overlay([TextRenderable([f"line-{i:02}"]) for i in range(50)])
    area = Rect(0, 0, 40, 15)

    overlay.view.scroll_offset = 0
    _visible_line_numbers(overlay, area)
    page_height = overlay.view.page_height(area)

    overlay.view.scroll_offset = 0
    page1 = _visible_line_numbers(overlay, area)
    assert page1 == list(range(page1[0], page1[0] + len(page1)))

    overlay.view.scroll_offset += page_height
    page2 = _visible_line_numbers(overlay, area)
    assert page2[0] == page1[-1] + 1

    overlay.view.scroll_offset = 3
    before = _visible_line_numbers(overlay, area)
    overlay.view.scroll_offset += page_height
    _visible_line_numbers(overlay, area)
    overlay.view.scroll_offset -= page_height
    assert _visible_line_numbers(overlay, area) == before

    overlay.view.scroll_offset = page_height
    before2 = _visible_line_numbers(overlay, area)
    overlay.view.scroll_offset -= page_height
    _visible_line_numbers(overlay, area)
    overlay.view.scroll_offset += page_height
    assert _visible_line_numbers(overlay, area) == before2


def test_transcript_overlay_home_then_page_down_lands_on_intermediate_page() -> None:
    """Rust codex-tui::pager_overlay::PagerView::handle_key_event PageDown contract.

    Source contract: Home sets ``scroll_offset = 0``; PageDown adds the last
    rendered content-area height returned by ``PagerView::page_height``. This
    protects the top-edge transition separately from the bottom round trip.
    """

    overlay = transcript_overlay([TextRenderable([f"line-{i:02}"]) for i in range(70)])
    area = Rect(0, 0, 40, 15)

    overlay.view.scroll_offset = 0
    top_page = _visible_line_numbers(overlay, area)
    page_height = overlay.view.page_height(area)

    overlay.view.scroll_offset += page_height
    next_page = _visible_line_numbers(overlay, area)

    assert top_page[0] == 0
    assert page_height > 0
    assert next_page[0] == page_height
    assert next_page[0] > top_page[0]
    assert next_page[-1] < 69


def test_static_overlay_wraps_long_lines() -> None:
    """Rust codex-tui::pager_overlay::tests::static_overlay_wraps_long_lines."""

    overlay = StaticOverlay.with_title(
        ["a very long line that should wrap when rendered within a narrow pager overlay width"],
        "S T A T I C",
    )

    lines = overlay.render(Rect(0, 0, 24, 8))

    assert lines[:4] == [
        "a very long line that sh",
        "ould wrap when rendered ",
        "within a narrow pager ov",
        "erlay width",
    ]


def test_transcript_overlay_uses_history_cell_full_transcript_projection() -> None:
    """Rust pager_overlay::CellRenderable uses transcript_hyperlink_lines, not display lines."""

    class TruncatedExecCell:
        def display_lines(self, _width: int):
            return [Line.from_text("...+9 lines (ctrl + t to view transcript)")]

        def transcript_hyperlink_lines(self, _width: int):
            return [HyperlinkLine.new("line one"), HyperlinkLine.new("line two")]

        def is_stream_continuation(self) -> bool:
            return False

    overlay = TranscriptOverlay.new([TruncatedExecCell()])
    lines = overlay.render_frame(Rect(0, 0, 48, 12))

    assert any("T R A N S C R I P T" in line for line in lines)
    assert "line one" in "\n".join(lines)
    assert "line two" in "\n".join(lines)
    assert "...+9 lines" not in "\n".join(lines)


def test_transcript_overlay_ctrl_t_closes_and_navigation_scrolls() -> None:
    """Rust pager_overlay handles pager navigation and close_transcript via the shared view."""

    overlay = transcript_overlay([TextRenderable([f"line-{index}"]) for index in range(40)])
    area = Rect(0, 0, 40, 12)
    overlay.render_frame(area)
    before = overlay.view.scroll_offset

    assert overlay.handle_input("up", "", area)
    overlay.render_frame(area)
    assert overlay.view.scroll_offset == max(0, before - 1)
    assert overlay.handle_input("ctrl_t", "", area)
    assert overlay.is_done()


def test_transcript_overlay_normalizes_windows_and_ansi_navigation_payloads() -> None:
    """Rust event_stream -> PagerKeymap accepts named and ANSI navigation forms."""

    overlay = transcript_overlay([TextRenderable([f"line-{index}"]) for index in range(80)])
    area = Rect(0, 0, 40, 12)
    overlay.render_frame(area)

    assert overlay.handle_input("text", "home", area)
    overlay.render_frame(area)
    assert overlay.view.scroll_offset == 0

    assert overlay.handle_input("text", "\x1b[6~", area)
    overlay.render_frame(area)
    assert overlay.view.scroll_offset == overlay.view.page_height(Rect(0, 0, 40, 9))

    assert overlay.handle_input("PageUp", "", area)
    overlay.render_frame(area)
    assert overlay.view.scroll_offset == 0


def test_pager_view_content_height_counts_renderables() -> None:
    """Rust codex-tui::pager_overlay::tests::pager_view_content_height_counts_renderables."""

    view = pager_view([paragraph_block("a", 2), paragraph_block("b", 3)], "T", 0)

    assert view.content_height(80) == 5


def test_pager_view_ensure_chunk_visible_scrolls_down_and_up_when_needed() -> None:
    """Rust source contract: PagerView::ensure_chunk_visible keeps requested renderable in viewport."""

    view = pager_view(
        [
            paragraph_block("a", 1),
            paragraph_block("b", 3),
            paragraph_block("c", 3),
        ],
        "T",
        0,
    )
    area = Rect(0, 0, 10, 5)
    content_area = view.content_area(area)

    view.ensure_chunk_visible(2, content_area)
    assert view.scroll_offset > 0

    view.ensure_chunk_visible(0, content_area)
    assert view.scroll_offset == 0
