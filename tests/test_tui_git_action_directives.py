"""Parity tests for Rust ``codex-tui::git_action_directives``.

Rust source: ``codex/codex-rs/tui/src/git_action_directives.rs``.
"""

from pycodex.tui.git_action_directives import (
    GitActionDirective,
    parse_assistant_markdown,
    parse_attributes,
    parse_git_action,
)


def test_strips_and_parses_git_action_directives() -> None:
    parsed = parse_assistant_markdown(
        'Done\n\n::git-stage{cwd="/repo"} ::git-push{cwd="/repo" branch="feat/x"}'
    )
    assert parsed.visible_markdown == "Done"
    assert parsed.git_actions == [
        GitActionDirective.Stage(cwd="/repo"),
        GitActionDirective.Push(cwd="/repo", branch="feat/x"),
    ]


def test_hides_malformed_directives_without_materializing_rows() -> None:
    parsed = parse_assistant_markdown('Done ::git-push{cwd="/repo"}')
    assert parsed.visible_markdown == "Done"
    assert parsed.git_actions == []


def test_last_created_branch_cwd_uses_the_last_matching_directive() -> None:
    parsed = parse_assistant_markdown(
        '::git-create-branch{cwd="/first" branch="first"}\n'
        '::git-push{cwd="/repo" branch="first"}\n'
        '::git-create-branch{cwd="/second" branch="second"}'
    )
    assert parsed.last_created_branch_cwd() == "/second"


def test_parse_attributes_supports_quoted_and_bare_values() -> None:
    assert parse_attributes('cwd="/repo" branch=feat/x isDraft=true') == {
        "cwd": "/repo",
        "branch": "feat/x",
        "isDraft": "true",
    }


def test_parse_git_create_pr_optional_url_and_draft_flag() -> None:
    action = parse_git_action(
        "git-create-pr",
        'cwd="/repo" branch="feat/x" url="https://example.test/pr/1" isDraft=true',
    )
    assert action == GitActionDirective.CreatePr(
        cwd="/repo",
        branch="feat/x",
        url="https://example.test/pr/1",
        is_draft=True,
    )


def test_duplicate_actions_are_deduplicated_in_first_seen_order() -> None:
    parsed = parse_assistant_markdown(
        '::git-stage{cwd="/repo"}\n::git-stage{cwd="/repo"}\n::git-commit{cwd="/repo"}'
    )
    assert parsed.git_actions == [
        GitActionDirective.Stage("/repo"),
        GitActionDirective.Commit("/repo"),
    ]
