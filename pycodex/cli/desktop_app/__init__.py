"""Rust-aligned codex-cli desktop_app platform dispatch."""

from __future__ import annotations

import sys
from typing import TextIO

from pycodex.cli.app_cmd import workspace_for_app_command
from .mac import run_mac_app_open_or_install
from .windows import run_windows_app_open_or_install


def run_app_open_or_install(
    command_args: tuple[str, ...],
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    del stdout

    workspace_arg = "."
    download_url: str | None = None
    index = 0
    while index < len(command_args):
        arg = command_args[index]
        if arg == "--download-url":
            if index + 1 >= len(command_args):
                print("Missing value for --download-url.", file=stderr)
                return 2
            download_url = command_args[index + 1]
            index += 2
            continue
        if not arg.startswith("-"):
            workspace_arg = arg
        index += 1

    workspace = workspace_for_app_command(workspace_arg)

    if sys.platform == "darwin":
        return run_mac_app_open_or_install(
            workspace=workspace,
            download_url=download_url,
            stderr=stderr,
        )

    if sys.platform.startswith("win"):
        return run_windows_app_open_or_install(
            workspace=workspace,
            download_url=download_url,
            stderr=stderr,
        )

    return 0

def help_text() -> str:
    return "Usage: codex app [OPTIONS] [PATH]"
