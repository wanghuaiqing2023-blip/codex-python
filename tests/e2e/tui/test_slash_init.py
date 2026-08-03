"""End-to-end coverage for the ``/init`` slash command."""

from pathlib import Path
import re

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._common import _repo_root
from tests.e2e.tui._slash_command_common import (
    assert_local_slash_candidate,
    require_native_slash_comparison,
    run_local_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e


def test_init_slash_command_uses_local_effect_route() -> None:
    assert terminal_slash_command_routes()[SlashCommand.INIT].outcome == "effect"


def test_windows_conpty_native_and_python_init_existing_file_guard_when_enabled(
    tmp_path: Path,
) -> None:
    # Rust test contract:
    # chatwidget/tests/slash_commands.rs::init_command_when_agents_md_exists
    # keeps the existing file intact, shows the skip notice, and records the
    # local command without creating a model turn.
    native_exe = require_native_slash_comparison()
    assert (_repo_root() / "AGENTS.md").is_file()
    rust, python = slash_candidate_pair(native_exe)
    notice = "AGENTS.md already exists here. Skipping /init to avoid overwriting it."

    results = [
        (
            label,
            *run_local_slash_candidate(
                command,
                label=label,
                slash_text="/init",
                stop_pattern=re.escape(notice),
                artifact_dir=tmp_path,
            ),
        )
        for label, command in (("rust", rust), ("python", python))
    ]

    for label, transcript, request_count in results:
        assert_local_slash_candidate(label, transcript, request_count)
        assert notice in transcript.normalized_stdout()
