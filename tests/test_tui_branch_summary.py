"""Parity tests for Rust ``codex-tui::branch_summary``.

Rust source: ``codex/codex-rs/tui/src/branch_summary.rs``.
"""

import pytest

from pycodex.tui.branch_summary import (
    FakeRunner,
    GitBranchDiffStats,
    StatusLineGitSummary,
    StatusLinePullRequest,
    branch_diff_stats_to_default_branch,
    current_branch_name,
    open_pull_request,
    pull_request_from_api_output,
    pull_request_from_view_output,
    repo_search_order_from_output,
    response,
    status_line_git_summary,
)


@pytest.mark.asyncio
async def test_current_branch_name_trims_branch_and_omits_empty_detached_head() -> None:
    runner = FakeRunner.new(
        [
            response(["git", "branch", "--show-current"], 0, "feature/example\n"),
            response(["git", "branch", "--show-current"], 0, "\n"),
        ]
    )

    assert await current_branch_name(runner, "/repo") == "feature/example"
    assert await current_branch_name(runner, "/repo") is None


@pytest.mark.asyncio
async def test_branch_diff_stats_prefers_remote_default_ref_over_stale_local_branch() -> None:
    runner = FakeRunner.new(
        [
            response(["git", "rev-parse", "--git-dir"], 0, ".git\n"),
            response(["git", "remote"], 0, "origin\n"),
            response(
                ["git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
                0,
                "refs/remotes/origin/main\n",
            ),
            response(
                ["git", "rev-parse", "--verify", "--quiet", "refs/remotes/origin/main"],
                0,
                "remote-main-sha\n",
            ),
            response(["git", "merge-base", "HEAD", "refs/remotes/origin/main"], 0, "base-sha\n"),
            response(["git", "diff", "--numstat", "base-sha..HEAD"], 0, "1\t0\tfile\n"),
        ]
    )
    stats = await branch_diff_stats_to_default_branch(runner, "/repo")
    assert stats == GitBranchDiffStats(additions=1, deletions=0)
    assert runner.saw(["git", "merge-base", "HEAD", "refs/remotes/origin/main"])


@pytest.mark.asyncio
async def test_open_pull_request_uses_current_branch_view_first() -> None:
    runner = FakeRunner.new(
        [
            response(
                ["gh", "pr", "view", "--json", "number,url,state"],
                0,
                '{"number":20252,"url":"https://github.com/openai/codex/pull/20252","state":"OPEN"}',
            )
        ]
    )
    pull_request = await open_pull_request(runner, "/repo")
    assert pull_request == StatusLinePullRequest(
        number=20252, url="https://github.com/openai/codex/pull/20252"
    )
    assert not runner.saw(["git", "rev-parse", "HEAD"])


@pytest.mark.asyncio
async def test_open_pull_request_falls_back_to_parent_repo_commit_lookup() -> None:
    runner = FakeRunner.new(
        [
            response(["gh", "pr", "view", "--json", "number,url,state"], 1, ""),
            response(["git", "rev-parse", "HEAD"], 0, "head-sha\n"),
            response(
                ["gh", "repo", "view", "--json", "nameWithOwner,parent"],
                0,
                '{"nameWithOwner":"fcoury/codex","parent":{"nameWithOwner":"openai/codex"}}',
            ),
            response(
                [
                    "gh",
                    "api",
                    "-H",
                    "Accept: application/vnd.github+json",
                    "repos/openai/codex/commits/head-sha/pulls",
                ],
                0,
                '[{"number":20252,"html_url":"https://github.com/openai/codex/pull/20252","state":"open"}]',
            ),
        ]
    )
    pull_request = await open_pull_request(runner, "/repo")
    assert pull_request == StatusLinePullRequest(
        number=20252, url="https://github.com/openai/codex/pull/20252"
    )
    assert runner.saw(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            "repos/openai/codex/commits/head-sha/pulls",
        ]
    )


def test_status_line_pr_view_parser_requires_open_pr() -> None:
    assert pull_request_from_view_output(
        '{"number":20252,"url":"https://github.com/openai/codex/pull/20252","state":"OPEN"}'
    ) == StatusLinePullRequest(number=20252, url="https://github.com/openai/codex/pull/20252")
    assert pull_request_from_view_output(
        '{"number":20252,"url":"https://github.com/openai/codex/pull/20252","state":"MERGED"}'
    ) is None


def test_status_line_pr_fallback_searches_parent_repo_first() -> None:
    assert repo_search_order_from_output(
        '{"nameWithOwner":"fcoury/codex","parent":{"nameWithOwner":"openai/codex"}}'
    ) == ["openai/codex", "fcoury/codex"]


def test_status_line_pr_api_parser_returns_first_open_pr() -> None:
    assert pull_request_from_api_output(
        "["
        '{"number":1,"html_url":"https://github.com/openai/codex/pull/1","state":"closed"},'
        '{"number":2,"html_url":"https://github.com/openai/codex/pull/2","state":"OPEN"}'
        "]"
    ) == StatusLinePullRequest(number=2, url="https://github.com/openai/codex/pull/2")
    assert pull_request_from_api_output(
        '[{"number":1,"html_url":"https://github.com/openai/codex/pull/1","state":"merged"}]'
    ) is None


@pytest.mark.asyncio
async def test_status_line_git_summary_combines_independent_optional_probes() -> None:
    runner = FakeRunner.new(
        [
            response(
                ["gh", "pr", "view", "--json", "number,url,state"],
                0,
                '{"number":7,"url":"https://github.com/openai/codex/pull/7","state":"open"}',
            ),
            response(["git", "rev-parse", "--git-dir"], 0, ".git\n"),
            response(["git", "remote"], 1, ""),
            response(["git", "rev-parse", "--verify", "--quiet", "refs/heads/main"], 0, "main\n"),
            response(["git", "merge-base", "HEAD", "refs/heads/main"], 0, "base\n"),
            response(["git", "diff", "--numstat", "base..HEAD"], 0, "3\t2\tfile\n-\t4\tbinary\n"),
        ]
    )

    assert await status_line_git_summary(runner, "/repo") == StatusLineGitSummary(
        pull_request=StatusLinePullRequest(
            number=7,
            url="https://github.com/openai/codex/pull/7",
        ),
        branch_change_stats=GitBranchDiffStats(additions=3, deletions=6),
    )
