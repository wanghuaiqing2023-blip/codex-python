from pathlib import Path

from pycodex.tui.chatwidget.review_popups import (
    CommitLogEntry,
    custom_review_prompt_action,
    open_review_popup,
    show_review_branch_picker,
    show_review_branch_picker_with_branches,
    show_review_commit_picker,
    show_review_commit_picker_with_entries,
    show_review_custom_prompt,
)


def test_open_review_popup_builds_four_presets_in_rust_order() -> None:
    # Rust parity: ChatWidget::open_review_popup.
    view = open_review_popup(Path("/repo"))

    assert view.title == "Select a review preset"
    assert [item.name for item in view.items] == [
        "Review against a base branch",
        "Review uncommitted changes",
        "Review a commit",
        "Custom review instructions",
    ]
    assert view.items[0].description == "(PR Style)"
    assert view.items[0].actions[0].kind == "open_review_branch_picker"
    assert view.items[0].actions[0].cwd == Path("/repo")
    assert not view.items[0].dismiss_on_select
    assert view.items[0].dismiss_parent_on_child_accept
    assert view.items[1].actions[0].kind == "review_uncommitted_changes"
    assert view.items[1].dismiss_on_select
    assert view.items[3].actions[0].kind == "open_review_custom_prompt"


def test_branch_picker_uses_current_branch_arrow_names_and_search_values() -> None:
    # Rust parity: ChatWidget::show_review_branch_picker item construction.
    view = show_review_branch_picker_with_branches(["main", "feature"], "topic")

    assert view.title == "Select a base branch"
    assert view.is_searchable
    assert view.search_placeholder == "Type to search branches"
    assert [item.name for item in view.items] == ["topic -> main", "topic -> feature"]
    assert view.items[1].search_value == "feature"
    assert view.items[1].actions[0].kind == "review_base_branch"
    assert view.items[1].actions[0].branch == "feature"


def test_branch_picker_uses_detached_head_fallback() -> None:
    # Rust parity: current_branch_name fallback is "(detached HEAD)".
    view = show_review_branch_picker_with_branches(["main"], None)
    assert view.items[0].name == "(detached HEAD) -> main"


def test_branch_picker_wrapper_uses_git_providers() -> None:
    # Rust parity: ChatWidget::show_review_branch_picker delegates to branch/current-branch helpers.
    view = show_review_branch_picker(
        Path("/repo"),
        lambda cwd: ["main"] if cwd == Path("/repo") else [],
        lambda cwd: "topic" if cwd == Path("/repo") else None,
    )

    assert view.items[0].name == "topic -> main"


def test_commit_picker_shows_subjects_without_timestamps_and_searches_sha() -> None:
    # Rust parity: review_commit_picker_shows_subjects_without_timestamps.
    view = show_review_commit_picker_with_entries(
        [
            CommitLogEntry(sha="1111111deadbeef", timestamp=0, subject="Add new feature X"),
            CommitLogEntry(sha="2222222cafebabe", timestamp=0, subject="Fix bug Y"),
        ]
    )

    assert view.title == "Select a commit to review"
    assert view.is_searchable
    assert [item.name for item in view.items] == ["Add new feature X", "Fix bug Y"]
    assert "1970" not in " ".join(item.name for item in view.items)
    assert view.items[0].search_value == "Add new feature X 1111111deadbeef"
    assert view.items[0].actions[0].kind == "review_commit"
    assert view.items[0].actions[0].sha == "1111111deadbeef"
    assert view.items[0].actions[0].title == "Add new feature X"


def test_commit_picker_wrapper_uses_recent_commit_provider_with_limit_100() -> None:
    # Rust parity: ChatWidget::show_review_commit_picker requests recent commits with limit 100.
    calls = []

    def recent(cwd, limit):
        calls.append((cwd, limit))
        return [CommitLogEntry(sha="abc", subject="Subject")]

    view = show_review_commit_picker(Path("/repo"), recent)

    assert calls == [(Path("/repo"), 100)]
    assert view.items[0].name == "Subject"


def test_commit_picker_with_no_entries_preserves_searchable_empty_view_shape() -> None:
    # Rust still constructs the searchable selection view even when recent_commits returns empty.
    view = show_review_commit_picker_with_entries([])

    assert view.title == "Select a commit to review"
    assert view.is_searchable
    assert view.search_placeholder == "Type to search commits"
    assert view.items == []


def test_custom_prompt_view_metadata_and_trimmed_submit_behavior() -> None:
    # Rust parity: show_review_custom_prompt and CustomPromptView submit callback.
    metadata = show_review_custom_prompt()
    assert metadata == {
        "title": "Custom review instructions",
        "placeholder": "Type instructions and press Enter",
        "initial_text": "",
    }

    assert custom_review_prompt_action("   ") is None
    action = custom_review_prompt_action("  please audit dependencies  ")
    assert action is not None
    assert action.kind == "review_custom"
    assert action.instructions == "please audit dependencies"
