# Parity source: codex-rs/tui/src/pager_overlay.rs

from pycodex.tui.pager_overlay import (
    MAX_SCROLL,
    LiveTailKey,
    PagerView,
    Rect,
    TextRenderable,
    first_or_empty,
    pager_view,
    paragraph_block,
    render_key_hints,
    static_overlay,
    transcript_overlay,
)


def test_first_or_empty_matches_rust_helper():
    assert first_or_empty(["a", "b"]) == ["a"]
    assert first_or_empty([]) == []


def test_render_key_hints_joins_keys_and_descriptions():
    assert render_key_hints([(["q"], "quit"), (["j", "down"], "scroll")]) == " q quit   j/down scroll"


def test_pager_view_content_height_counts_renderables():
    view = pager_view([paragraph_block("a", 2), paragraph_block("b", 3)], "T")

    assert view.content_height(80) == 5


def test_pager_view_page_height_prefers_last_rendered_content_height():
    view = pager_view([paragraph_block("a", 10)], "T")
    area = Rect(0, 0, 20, 8)

    assert view.page_height(area) == 6
    view.render(area)
    assert view.page_height(Rect(0, 0, 20, 3)) == 6


def test_pager_view_ensure_chunk_visible_scrolls_down_when_needed():
    view = pager_view(
        [paragraph_block("a", 1), paragraph_block("b", 3), paragraph_block("c", 3)],
        "T",
    )
    content_area = view.content_area(Rect(0, 0, 20, 8))

    view.ensure_chunk_visible(2, content_area)
    rendered = view.render(Rect(0, 0, 20, 8))

    assert "c0" in rendered
    assert "c1" in rendered
    assert "c2" in rendered


def test_pager_view_ensure_chunk_visible_scrolls_up_when_needed():
    view = pager_view(
        [paragraph_block("a", 2), paragraph_block("b", 3), paragraph_block("c", 3)],
        "T",
    )
    view.scroll_offset = 6

    view.ensure_chunk_visible(0, Rect(0, 0, 20, 3))

    assert view.scroll_offset == 0


def test_pager_view_reports_scrolled_to_bottom_after_max_scroll_render():
    view = pager_view([paragraph_block("a", 10)], "T")
    area = Rect(0, 0, 20, 8)

    view.render(area)
    assert view.is_scrolled_to_bottom() is False

    view.scroll_offset = MAX_SCROLL
    view.render(area)
    assert view.is_scrolled_to_bottom() is True


def test_transcript_overlay_sync_live_tail_is_noop_for_identical_key():
    overlay = transcript_overlay([TextRenderable(["alpha"])])
    calls = {"count": 0}
    key = LiveTailKey(width=40, revision=1, is_stream_continuation=False)

    def build_tail(width):
        calls["count"] += 1
        return [f"tail-{width}-{calls['count']}"]

    overlay.sync_live_tail(40, key, build_tail)
    overlay.sync_live_tail(40, key, build_tail)

    assert calls["count"] == 1
    assert overlay.live_tail is not None


def test_transcript_overlay_sync_live_tail_rebuilds_on_key_change_and_clears_on_none():
    overlay = transcript_overlay([TextRenderable(["alpha"])])
    calls = {"count": 0}

    def build_tail(width):
        calls["count"] += 1
        return [f"tail-{width}-{calls['count']}"]

    overlay.sync_live_tail(40, LiveTailKey(width=40, revision=1, is_stream_continuation=False), build_tail)
    assert calls["count"] == 1
    assert overlay.live_tail is not None
    assert overlay.view.renderables[-1] is overlay.live_tail

    overlay.sync_live_tail(41, LiveTailKey(width=41, revision=1, is_stream_continuation=False), build_tail)
    assert calls["count"] == 2
    assert overlay.live_tail is not None

    overlay.sync_live_tail(41, None, build_tail)
    assert calls["count"] == 2
    assert overlay.live_tail is None
    assert overlay.live_tail_key is None
    assert len(overlay.view.renderables) == overlay.committed_cell_count()


def test_transcript_overlay_keeps_scroll_pinned_at_bottom_on_insert():
    overlay = transcript_overlay([TextRenderable([f"line{i}"]) for i in range(20)])
    overlay.render(Rect(0, 0, 40, 12))
    assert overlay.view.is_scrolled_to_bottom()

    overlay.insert_cell(TextRenderable(["tail"]))

    assert overlay.view.scroll_offset == MAX_SCROLL


def test_transcript_overlay_preserves_manual_scroll_position_on_insert():
    overlay = transcript_overlay([TextRenderable([f"line{i}"]) for i in range(20)])
    overlay.render(Rect(0, 0, 40, 12))
    overlay.view.scroll_offset = 0

    overlay.insert_cell(TextRenderable(["tail"]))

    assert overlay.view.scroll_offset == 0


def test_transcript_overlay_consolidation_remaps_highlight_inside_range():
    overlay = transcript_overlay([TextRenderable([f"line{i}"]) for i in range(6)])
    overlay.set_highlight_cell(3)

    overlay.consolidate_cells((2, 5), TextRenderable(["consolidated"]))

    assert overlay.highlight_cell == 2
    assert overlay.committed_cell_count() == 4


def test_transcript_overlay_consolidation_remaps_highlight_after_range():
    overlay = transcript_overlay([TextRenderable([f"line{i}"]) for i in range(7)])
    overlay.set_highlight_cell(6)

    overlay.consolidate_cells((2, 5), TextRenderable(["consolidated"]))

    assert overlay.highlight_cell == 4


def test_static_overlay_wraps_long_lines_semantically():
    overlay = static_overlay(["a very long line"], "S T A T I C")

    rendered = overlay.render(Rect(0, 0, 5, 6))

    assert rendered[:4] == ["a ver", "y lon", "g lin", "e"]
