"""Resolve deny-read filesystem policy entries into Windows ACL targets.

Rust owner: ``codex-windows-sandbox::deny_read_resolver``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    ReadDenyMatcher,
)


@dataclass(frozen=True)
class GlobScanPlan:
    root: Path
    max_depth: int | None


def resolve_windows_deny_read_paths(
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    cwd: str | Path,
) -> tuple[Path, ...]:
    """Snapshot-expand denied globs while preserving exact future paths."""

    cwd = Path(cwd)
    paths: list[Path] = []
    seen_paths: set[Path] = set()

    for path in file_system_sandbox_policy.get_unreadable_roots_with_cwd(cwd):
        _push_absolute_path(paths, seen_paths, Path(path))

    unreadable_globs = file_system_sandbox_policy.get_unreadable_globs_with_cwd(cwd)
    if not unreadable_globs:
        return tuple(paths)

    glob_policy = FileSystemSandboxPolicy.restricted(
        [
            FileSystemSandboxEntry(
                FileSystemPath.glob_pattern(pattern),
                FileSystemAccessMode.DENY,
            )
            for pattern in unreadable_globs
        ]
    )
    matcher = ReadDenyMatcher.try_new(glob_policy, cwd)
    if matcher is None:
        return tuple(paths)

    for pattern in unreadable_globs:
        scan_plan = glob_scan_plan(pattern, file_system_sandbox_policy.glob_scan_max_depth)
        _collect_existing_glob_matches(
            scan_plan.root,
            matcher,
            paths,
            seen_paths,
            set(),
            scan_plan.max_depth,
            0,
        )

    return tuple(paths)


def glob_scan_plan(
    pattern: str,
    configured_max_depth: int | None,
) -> GlobScanPlan:
    first_glob = next(
        (index for index, character in enumerate(pattern) if character in "*?["),
        len(pattern),
    )
    literal_prefix = pattern[:first_glob]
    separator_index = max(literal_prefix.rfind("/"), literal_prefix.rfind("\\"))
    if separator_index < 0:
        return GlobScanPlan(
            Path("."),
            effective_glob_scan_max_depth(pattern, configured_max_depth),
        )

    pattern_suffix = pattern[separator_index + 1 :]
    max_depth = effective_glob_scan_max_depth(pattern_suffix, configured_max_depth)
    is_drive_root_separator = separator_index > 0 and literal_prefix[separator_index - 1] == ":"
    if separator_index == 0 or is_drive_root_separator:
        return GlobScanPlan(Path(literal_prefix[: separator_index + 1]), max_depth)
    return GlobScanPlan(Path(literal_prefix[:separator_index]), max_depth)


def effective_glob_scan_max_depth(
    pattern_suffix: str,
    configured_max_depth: int | None,
) -> int | None:
    components = tuple(
        component
        for component in re.split(r"[/\\]", pattern_suffix)
        if component
    )
    if "**" in components:
        return configured_max_depth
    component_depth = len(components)
    if configured_max_depth is None:
        return component_depth
    return min(configured_max_depth, component_depth)


def _collect_existing_glob_matches(
    path: Path,
    matcher: ReadDenyMatcher,
    paths: list[Path],
    seen_paths: set[Path],
    seen_scan_dirs: set[Path],
    max_depth: int | None,
    depth: int,
) -> None:
    if not path.exists():
        return

    if matcher.is_read_denied(path):
        _push_absolute_path(paths, seen_paths, path)

    try:
        if not path.is_dir():
            return
        scan_key = path.resolve(strict=False)
    except OSError:
        return
    if scan_key in seen_scan_dirs:
        return
    seen_scan_dirs.add(scan_key)

    if max_depth is not None and depth >= max_depth:
        return

    try:
        entries = tuple(path.iterdir())
    except OSError:
        return
    for entry in entries:
        _collect_existing_glob_matches(
            entry,
            matcher,
            paths,
            seen_paths,
            seen_scan_dirs,
            max_depth,
            depth + 1,
        )


def _push_absolute_path(
    paths: list[Path],
    seen: set[Path],
    path: Path,
) -> None:
    if not path.is_absolute():
        raise ValueError(f"deny-read path is not absolute: {path}")
    if path not in seen:
        seen.add(path)
        paths.append(path)


__all__ = [
    "GlobScanPlan",
    "effective_glob_scan_max_depth",
    "glob_scan_plan",
    "resolve_windows_deny_read_paths",
]
