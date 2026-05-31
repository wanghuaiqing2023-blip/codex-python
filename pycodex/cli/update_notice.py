"""Update-available notice formatting.

Ported from ``codex/codex-rs/tui/src/history_cell/notices.rs`` raw-line output.
"""

from __future__ import annotations

from pycodex import __version__
from .update_action import UpdateAction


RELEASE_NOTES_URL = "https://github.com/openai/codex/releases/latest"
INSTALL_OPTIONS_URL = "https://github.com/openai/codex"


def update_available_raw_lines(
    latest_version: str,
    update_action: UpdateAction | None,
    *,
    current_version: str = __version__,
) -> list[str]:
    if not isinstance(latest_version, str):
        raise TypeError("latest_version must be a string")
    if not isinstance(current_version, str):
        raise TypeError("current_version must be a string")
    if update_action is not None and not isinstance(update_action, UpdateAction):
        raise TypeError("update_action must be an UpdateAction or None")

    if update_action is not None:
        update_instruction = f"Run {update_action.command_str()} to update."
    else:
        update_instruction = f"See {INSTALL_OPTIONS_URL} for installation options."

    return [
        "Update available!",
        f"{current_version} -> {latest_version}",
        update_instruction,
        "",
        "See full release notes:",
        RELEASE_NOTES_URL,
    ]
