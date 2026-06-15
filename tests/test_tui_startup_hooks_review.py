from types import SimpleNamespace

import pytest

from pycodex.tui.startup_hooks_review import (
    ListSelectionView,
    StartupHooksReviewOutcome,
    StartupHooksReviewSelection,
    entry,
    maybe_run_startup_hooks_review,
    render_lines,
    run_startup_hooks_review_app,
    review_is_needed,
    review_needed_count,
    selected_choice,
    selection_item,
    selection_view,
    selection_view_params,
)


def test_bypass_hook_trust_suppresses_startup_review() -> None:
    # Rust source: startup_hooks_review.rs::tests::bypass_hook_trust_suppresses_startup_review.
    assert not review_is_needed(True, entry())


def test_untrusted_hooks_need_review_without_bypass() -> None:
    # Rust source: startup_hooks_review.rs::tests::untrusted_hooks_need_review_without_bypass.
    assert review_is_needed(False, entry())
    assert review_needed_count(entry()) == 2


def test_selected_choice_maps_completed_indices() -> None:
    params = selection_view_params(entry(), None, False, None)
    view = ListSelectionView(params)
    assert selected_choice(view) is None

    view.select(0)
    assert selected_choice(view) is StartupHooksReviewSelection.REVIEW_HOOKS
    view.select(1)
    assert selected_choice(view) is StartupHooksReviewSelection.TRUST_ALL_AND_CONTINUE
    view.select(2)
    assert selected_choice(view) is StartupHooksReviewSelection.CONTINUE_WITHOUT_TRUSTING
    view.select(None)
    assert selected_choice(view) is StartupHooksReviewSelection.CONTINUE_WITHOUT_TRUSTING
    view.select(99)
    assert selected_choice(view) is None


def test_selection_view_params_prompt_content() -> None:
    params = selection_view_params(entry(), None, False, None)
    assert params.header == [
        "Hooks need review",
        "2 hooks are new or changed.",
        "Hooks can run outside the sandbox after you trust them.",
    ]
    assert [item.name for item in params.items] == [
        "Review hooks",
        "Trust all and continue",
        "Continue without trusting (hooks won't run)",
    ]
    assert [item.is_disabled for item in params.items] == [False, False, False]
    assert params.footer_hint == "Use arrows to move, Enter to select"


def test_selection_view_params_singular_trusting_and_error_states() -> None:
    singular = {"hooks": [{"trust_status": "Untrusted", "key": "k", "current_hash": "h"}]}
    trusting = selection_view_params(singular, None, True, None)
    assert "1 hook is new or changed." in trusting.header
    assert "Trusting hooks..." in trusting.header
    assert all(item.is_disabled for item in trusting.items)

    errored = selection_view_params(singular, "Failed to trust hooks: disk full", False, None)
    assert "Failed to trust hooks: disk full" in errored.header
    assert "Trusting hooks..." not in errored.header


def test_selection_item_defaults_match_rust() -> None:
    item = selection_item("Review hooks", True)
    assert item.name == "Review hooks"
    assert item.dismiss_on_select is True
    assert item.is_disabled is True


def test_render_lines_semantic_prompt_contains_snapshot_text() -> None:
    view = selection_view(entry(), None, False, None, None)
    rendered = render_lines(view, 80)
    assert "Hooks need review" in rendered
    assert "2 hooks are new or changed." in rendered
    assert "Review hooks" in rendered
    assert "Trust all and continue" in rendered
    assert "Continue without trusting (hooks won't run)" in rendered


def test_render_lines_semantic_prompt_with_trust_error() -> None:
    view = selection_view(entry(), "Failed to trust hooks: disk full", False, None, None)
    assert "Failed to trust hooks: disk full" in render_lines(view, 80)


class RecordingTui:
    def __init__(self, events):
        self.events = list(events)
        self.drawn = []

    def draw(self, view):
        self.drawn.append(view)

    async def event_stream(self):
        for event in self.events:
            yield event


class RecordingAppServer:
    def __init__(self):
        self.handle = object()

    def request_handle(self):
        return self.handle


def key_event(code, kind="Press"):
    return SimpleNamespace(kind="Key", key=SimpleNamespace(code=code, kind=kind))


@pytest.mark.asyncio
async def test_maybe_run_startup_hooks_review_fetch_error_and_bypass_continue() -> None:
    async def failing_fetch(_handle, _cwd):
        raise RuntimeError("offline")

    result = await maybe_run_startup_hooks_review(
        RecordingAppServer(),
        RecordingTui([]),
        SimpleNamespace(cwd="/tmp"),
        False,
        fetch_hooks_list_fn=failing_fetch,
        hooks_list_entry_for_cwd_fn=lambda response, cwd: response,
    )
    assert result.outcome is StartupHooksReviewOutcome.CONTINUE

    async def fetch(_handle, _cwd):
        return entry()

    result = await maybe_run_startup_hooks_review(
        RecordingAppServer(),
        RecordingTui([]),
        SimpleNamespace(cwd="/tmp"),
        True,
        fetch_hooks_list_fn=fetch,
        hooks_list_entry_for_cwd_fn=lambda response, cwd: response,
    )
    assert result.outcome is StartupHooksReviewOutcome.CONTINUE


@pytest.mark.asyncio
async def test_run_startup_hooks_review_review_and_continue_choices() -> None:
    app_server = RecordingAppServer()
    review = await run_startup_hooks_review_app(
        app_server,
        RecordingTui([key_event("1")]),
        SimpleNamespace(tui_keymap=None),
        entry(),
    )
    assert review.outcome is StartupHooksReviewOutcome.OPEN_HOOKS_BROWSER
    assert review.entry == entry()

    cont = await run_startup_hooks_review_app(
        app_server,
        RecordingTui([key_event("3")]),
        SimpleNamespace(tui_keymap=None),
        entry(),
    )
    assert cont.outcome is StartupHooksReviewOutcome.CONTINUE


@pytest.mark.asyncio
async def test_run_startup_hooks_review_ignores_release_paste_draw_and_trusts_all() -> None:
    writes = []

    async def write_hook_trusts(_handle, updates):
        writes.append(updates)

    tui = RecordingTui([
        SimpleNamespace(kind="Paste"),
        SimpleNamespace(kind="Draw"),
        key_event("1", kind="Release"),
        key_event("2"),
    ])

    result = await run_startup_hooks_review_app(
        RecordingAppServer(),
        tui,
        SimpleNamespace(tui_keymap=None),
        entry(),
        write_hook_trusts_fn=write_hook_trusts,
    )

    assert result.outcome is StartupHooksReviewOutcome.CONTINUE
    assert writes == [[
        {"key": "path:new", "current_hash": "sha256:path:new"},
        {"key": "path:changed", "current_hash": "sha256:path:changed"},
    ]]
    assert len(tui.drawn) >= 2
    assert "Trusting hooks..." in tui.drawn[-1].params.header


@pytest.mark.asyncio
async def test_run_startup_hooks_review_trust_error_redraws_and_allows_continue_without_trusting() -> None:
    calls = 0

    async def write_hook_trusts(_handle, _updates):
        nonlocal calls
        calls += 1
        raise RuntimeError("disk full")

    tui = RecordingTui([key_event("2"), key_event("3")])

    result = await run_startup_hooks_review_app(
        RecordingAppServer(),
        tui,
        SimpleNamespace(tui_keymap=None),
        entry(),
        write_hook_trusts_fn=write_hook_trusts,
    )

    assert result.outcome is StartupHooksReviewOutcome.CONTINUE
    assert calls == 1
    assert any("Failed to trust hooks: disk full" in view.params.header for view in tui.drawn)
