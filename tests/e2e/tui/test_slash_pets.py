"""End-to-end coverage for ``/pets`` and its ``/pet`` alias."""

from pathlib import Path

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    assert_local_slash_candidate,
    require_native_slash_comparison,
    run_local_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_pets_slash_command_uses_pet_picker_view_route() -> None:
    route = terminal_slash_command_routes()[SlashCommand.PETS]

    assert SlashCommand.PETS.command() == "pets"
    assert SlashCommand.parse("pet") is SlashCommand.PETS
    assert SlashCommand.PETS.supports_inline_args() is True
    assert SlashCommand.PETS.available_during_task() is False
    assert SlashCommand.PETS.available_in_side_conversation() is False
    assert route.outcome == "view"
    assert route.python_owner == (
        "pycodex.tui.chatwidget.pets + pycodex.tui.pets.picker"
    )


@pytest.mark.parametrize("slash_text", ["/pets", "/pet"])
def test_windows_conpty_native_and_python_pets_guard_unsupported_terminal(
    tmp_path: Path,
    slash_text: str,
) -> None:
    # Rust source/test contract:
    # - chatwidget::pets::warn_if_pets_unsupported guards the picker before
    #   pets::picker is opened.
    # - slash_command::from_str aliases `/pet` to SlashCommand::Pets.
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    for label, command in (("rust", rust), ("python", python)):
        transcript, request_count = run_local_slash_candidate(
            command,
            label=label,
            slash_text=slash_text,
            stop_pattern="Kitty graphics or Sixel support",
            artifact_dir=tmp_path,
        )
        assert_local_slash_candidate(label, transcript, request_count)
        output = transcript.normalized_stdout()
        for expected in (
            "Terminal pets need image support",
            "Kitty graphics or Sixel support",
        ):
            assert expected in output, (
                f"{label}: missing {expected!r}; slash={slash_text!r}; "
                f"artifacts={tmp_path}"
            )
