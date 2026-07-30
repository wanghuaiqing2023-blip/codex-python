"""Apply-command orchestration owned by ``apply_command.rs``."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from pycodex.config import CliConfigOverrides, ConfigToml, load_config_layers_state
from pycodex.git_utils import ApplyGitRequest, apply_git_patch
from pycodex.login.auth.manager import DEFAULT_CHATGPT_BACKEND_BASE_URL
from pycodex.utils.home_dir import find_codex_home

from .get_task import GetTaskResponse, PrOutputItem, get_task


@dataclass(frozen=True)
class ApplyCommand:
    task_id: str
    config_overrides: CliConfigOverrides = field(default_factory=CliConfigOverrides)


@dataclass(frozen=True)
class _ChatgptRuntimeConfig:
    codex_home: Path
    chatgpt_base_url: str
    auth_credentials_store_mode: str
    forced_login_method: str | None
    forced_chatgpt_workspace_id: list[str] | None


async def run_apply_command(
    apply_cli: ApplyCommand,
    cwd: Path | None = None,
    *,
    stdout: TextIO | None = None,
) -> None:
    config = _load_config(apply_cli.config_overrides, cwd)
    task_response = await get_task(config, apply_cli.task_id)
    await apply_diff_from_task(task_response, cwd, stdout=stdout)


async def apply_diff_from_task(
    task_response: GetTaskResponse,
    cwd: Path | None = None,
    *,
    stdout: TextIO | None = None,
) -> None:
    diff_turn = task_response.current_diff_task_turn
    if diff_turn is None:
        raise RuntimeError("No diff turn found")
    output_diff = next(
        (
            item.output_diff
            for item in diff_turn.output_items
            if isinstance(item, PrOutputItem)
        ),
        None,
    )
    if output_diff is None:
        raise RuntimeError("No PR output item found")
    await _apply_diff(output_diff.diff, cwd, stdout=stdout)


async def _apply_diff(
    diff: str,
    cwd: Path | None,
    *,
    stdout: TextIO | None,
) -> None:
    target = Path(cwd) if cwd is not None else _current_or_temp_dir()
    result = apply_git_patch(
        ApplyGitRequest(
            cwd=target,
            diff=diff,
            revert=False,
            preflight=False,
        )
    )
    if result.exit_code != 0:
        raise RuntimeError(
            "Git apply failed "
            f"(applied={len(result.applied_paths)}, "
            f"skipped={len(result.skipped_paths)}, "
            f"conflicts={len(result.conflicted_paths)})\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    print("Successfully applied diff", file=stdout or sys.stdout)


def _load_config(
    overrides: CliConfigOverrides,
    cwd: Path | None,
) -> _ChatgptRuntimeConfig:
    config_cwd = Path(cwd) if cwd is not None else _current_or_temp_dir()
    codex_home = find_codex_home()
    stack = load_config_layers_state(
        codex_home,
        cwd=config_cwd,
        cli_overrides=overrides.parse_overrides(),
    )
    config_toml = ConfigToml.from_mapping(stack.effective_config())
    store_mode = config_toml.cli_auth_credentials_store
    forced_login = config_toml.forced_login_method
    workspace_ids = config_toml.forced_chatgpt_workspace_id
    return _ChatgptRuntimeConfig(
        codex_home=codex_home,
        chatgpt_base_url=(
            config_toml.chatgpt_base_url or DEFAULT_CHATGPT_BACKEND_BASE_URL
        ),
        auth_credentials_store_mode=(
            getattr(store_mode, "value", store_mode) if store_mode is not None else "file"
        ),
        forced_login_method=(
            getattr(forced_login, "value", forced_login)
            if forced_login is not None
            else None
        ),
        forced_chatgpt_workspace_id=(
            workspace_ids.into_vec() if workspace_ids is not None else None
        ),
    )


def _current_or_temp_dir() -> Path:
    try:
        return Path.cwd()
    except OSError:
        return Path(os.environ.get("TEMP", "."))


__all__ = [
    "ApplyCommand",
    "apply_diff_from_task",
    "run_apply_command",
]
