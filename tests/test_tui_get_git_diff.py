import asyncio
from pathlib import Path

import pytest

from pycodex.tui.get_git_diff import (
    FakeRunner,
    assert_commands,
    get_git_diff,
    null_device,
    response,
)


def run(coro):
    return asyncio.run(coro)


def test_get_git_diff_returns_not_git_for_non_git_cwd_matches_rust():
    cwd = Path("/workspace")
    runner = FakeRunner.new([
        response(["git", "rev-parse", "--is-inside-work-tree"], 128, ""),
    ])

    result = run(get_git_diff(runner, cwd))

    assert result == (False, "")
    assert_commands(
        runner.commands(),
        [["git", "rev-parse", "--is-inside-work-tree"]],
        cwd,
    )


def test_get_git_diff_concatenates_tracked_and_untracked_diffs_matches_rust():
    cwd = Path("/workspace")
    runner = FakeRunner.new([
        response(["git", "rev-parse", "--is-inside-work-tree"], 0, "true\n"),
        response(["git", "diff", "--color"], 1, "tracked\n"),
        response(["git", "ls-files", "--others", "--exclude-standard"], 0, "new.txt\n"),
        response(
            ["git", "diff", "--color", "--no-index", "--", null_device(), "new.txt"],
            1,
            "untracked\n",
        ),
    ])

    result = run(get_git_diff(runner, cwd))

    assert result == (True, "tracked\nuntracked\n")
    assert_commands(
        runner.commands(),
        [
            ["git", "rev-parse", "--is-inside-work-tree"],
            ["git", "diff", "--color"],
            ["git", "ls-files", "--others", "--exclude-standard"],
            ["git", "diff", "--color", "--no-index", "--", null_device(), "new.txt"],
        ],
        cwd,
    )


def test_get_git_diff_accepts_diff_exit_code_one_matches_rust():
    cwd = Path("/workspace")
    runner = FakeRunner.new([
        response(["git", "rev-parse", "--is-inside-work-tree"], 0, "true\n"),
        response(["git", "diff", "--color"], 1, "tracked\n"),
        response(["git", "ls-files", "--others", "--exclude-standard"], 0, ""),
    ])

    assert run(get_git_diff(runner, cwd)) == (True, "tracked\n")


def test_get_git_diff_rejects_unexpected_git_diff_status_matches_rust():
    cwd = Path("/workspace")
    runner = FakeRunner.new([
        response(["git", "rev-parse", "--is-inside-work-tree"], 0, "true\n"),
        response(["git", "diff", "--color"], 2, ""),
        response(["git", "ls-files", "--others", "--exclude-standard"], 0, ""),
    ])

    with pytest.raises(RuntimeError) as excinfo:
        run(get_git_diff(runner, cwd))

    assert 'git ["diff", "--color"] failed with status 2' in str(excinfo.value)


def test_get_git_diff_trims_and_skips_empty_untracked_lines():
    cwd = Path("/workspace")
    runner = FakeRunner.new([
        response(["git", "rev-parse", "--is-inside-work-tree"], 0, "true\n"),
        response(["git", "diff", "--color"], 0, "tracked"),
        response(["git", "ls-files", "--others", "--exclude-standard"], 0, " one.txt \n\n two.txt\n"),
        response(["git", "diff", "--color", "--no-index", "--", null_device(), "one.txt"], 1, "one"),
        response(["git", "diff", "--color", "--no-index", "--", null_device(), "two.txt"], 1, "two"),
    ])

    assert run(get_git_diff(runner, cwd)) == (True, "trackedonetwo")
