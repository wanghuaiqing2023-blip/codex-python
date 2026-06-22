from pycodex.cloud_tasks import ScrollableDiff, ScrollViewState


def test_scroll_view_state_clamps_to_saturating_max_scroll():
    # Rust crate/module: codex-cloud-tasks/src/scrollable_diff.rs::ScrollViewState::clamp.
    state = ScrollViewState(scroll=9, viewport_h=3, content_h=7)
    state.clamp()
    assert state.scroll == 4

    state = ScrollViewState(scroll=9, viewport_h=10, content_h=7)
    state.clamp()
    assert state.scroll == 0


def test_set_content_forces_rewrap_even_when_width_repeats():
    # Rust crate/module: codex-cloud-tasks/src/scrollable_diff.rs::set_content/set_width.
    diff = ScrollableDiff.new()
    diff.set_content(["abcdef"])
    diff.set_width(3)
    assert diff.wrapped_lines() == ["abc", "def"]
    assert diff.wrapped_src_indices() == [0, 0]

    diff.set_content(["xy"])
    diff.set_width(3)
    assert diff.wrapped_lines() == ["xy"]
    assert diff.wrapped_src_indices() == [0]
    assert diff.state.content_h == 1


def test_rewrap_tracks_source_indices_tabs_empty_and_newline_splits():
    # Rust crate/module: codex-cloud-tasks/src/scrollable_diff.rs::rewrap.
    diff = ScrollableDiff.new()
    diff.set_content(["a\tb", "", "one\ntwo"])
    diff.set_width(4)

    assert diff.wrapped_lines() == ["a", " b", "", "one", "two"]
    assert diff.wrapped_src_indices() == [0, 0, 1, 2, 2]
    assert diff.raw_line_at(0) == "a\tb"
    assert diff.raw_line_at(99) == ""
    assert diff.state.content_h == 5


def test_rewrap_soft_breaks_before_punctuation_and_trims_space_edges():
    # Rust crate/module: codex-cloud-tasks/src/scrollable_diff.rs::rewrap.
    diff = ScrollableDiff.new()
    diff.set_content(["hello world", "alpha-beta"])
    diff.set_width(7)

    assert diff.wrapped_lines() == ["hello", "world", "alpha", "-beta"]
    assert diff.wrapped_src_indices() == [0, 0, 1, 1]


def test_rewrap_width_zero_keeps_raw_lines_and_rust_stale_indices_behavior():
    # Rust crate/module: codex-cloud-tasks/src/scrollable_diff.rs::rewrap width == 0 branch.
    diff = ScrollableDiff.new()
    diff.set_content(["abcdef", "gh"])
    diff.set_width(3)
    assert diff.wrapped_src_indices() == [0, 0, 1]

    diff.set_width(0)
    assert diff.wrapped_lines() == ["abcdef", "gh"]
    # Rust assigns wrapped = raw.clone() and content_h only; it does not rebuild wrapped_src_idx.
    assert diff.wrapped_src_indices() == [0, 0, 1]
    assert diff.state.content_h == 2


def test_scroll_methods_clamp_and_percent_scrolled_matches_rust_rounding():
    # Rust crate/module: codex-cloud-tasks/src/scrollable_diff.rs scroll methods/percent_scrolled.
    diff = ScrollableDiff.new()
    diff.set_content([str(i) for i in range(10)])
    diff.set_width(10)

    assert diff.percent_scrolled() is None
    diff.set_viewport(4)
    assert diff.percent_scrolled() == 40

    diff.scroll_by(3)
    assert diff.state.scroll == 3
    assert diff.percent_scrolled() == 70

    diff.page_by(99)
    assert diff.state.scroll == 6
    assert diff.percent_scrolled() == 100

    diff.scroll_by(-99)
    assert diff.state.scroll == 0
    diff.scroll_to_bottom()
    assert diff.state.scroll == 6
    diff.scroll_to_top()
    assert diff.state.scroll == 0

    diff.set_viewport(20)
    assert diff.state.scroll == 0
    assert diff.percent_scrolled() is None


def test_wide_characters_use_display_width_for_wrapping():
    # Rust crate/module: codex-cloud-tasks/src/scrollable_diff.rs uses unicode_width.
    diff = ScrollableDiff.new()
    diff.set_content(["好好好"])
    diff.set_width(4)

    assert diff.wrapped_lines() == ["好好", "好"]
    assert diff.wrapped_src_indices() == [0, 0]
