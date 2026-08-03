"""Enforce the one-canonical-slash-command-per-E2E-file convention."""

from pathlib import Path

import pytest

from pycodex.tui.slash_command import SlashCommand

pytestmark = pytest.mark.e2e


def test_each_registered_slash_command_has_exactly_one_canonical_test_file() -> None:
    test_dir = Path(__file__).parent
    expected = {
        f"test_slash_{command.command().replace('-', '_')}.py": command
        for command in SlashCommand
    }
    actual = {
        path.name
        for path in test_dir.glob("test_slash_*.py")
    }

    assert len(expected) == len(SlashCommand), "canonical test filenames collided"
    assert actual == set(expected), (
        f"missing={sorted(set(expected) - actual)!r}; "
        f"unexpected={sorted(actual - set(expected))!r}"
    )
