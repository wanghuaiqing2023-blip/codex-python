"""Shared setup helpers used by legacy and elevated sandbox paths."""

from __future__ import annotations

from collections.abc import MutableMapping
from pathlib import Path


def ensure_codex_home_exists(path: str | Path) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def inject_git_safe_directory(
    env_map: MutableMapping[str, str],
    cwd: str | Path,
) -> None:
    git_root = _find_git_worktree_root_for_safe_directory(Path(cwd))
    if git_root is None:
        return
    try:
        config_count = int(env_map.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        config_count = 0
    env_map[f"GIT_CONFIG_KEY_{config_count}"] = "safe.directory"
    env_map[f"GIT_CONFIG_VALUE_{config_count}"] = str(git_root).replace(
        "\\\\",
        "/",
    )
    env_map["GIT_CONFIG_COUNT"] = str(config_count + 1)


def _find_git_worktree_root_for_safe_directory(start: Path) -> Path | None:
    try:
        current = start.resolve(strict=True)
    except OSError:
        return None
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


__all__ = ["ensure_codex_home_exists", "inject_git_safe_directory"]
