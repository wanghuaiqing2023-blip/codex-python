from pycodex.tui.startup_hooks_review import (
    ListSelectionView,
    StartupHooksReviewSelection,
    entry,
    render_lines,
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
