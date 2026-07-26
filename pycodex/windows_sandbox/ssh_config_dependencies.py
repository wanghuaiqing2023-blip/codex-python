"""Discover profile paths referenced by OpenSSH configuration."""

from __future__ import annotations

import glob
from pathlib import Path


SSH_PROFILE_PATH_DIRECTIVES = {
    "certificatefile",
    "controlpath",
    "globalknownhostsfile",
    "identityagent",
    "identityfile",
    "revokedhostkeys",
    "userknownhostsfile",
}


def ssh_config_dependency_paths(user_profile: str | Path) -> list[Path]:
    profile = Path(user_profile)
    ssh_dir = profile / ".ssh"
    config = ssh_dir / "config"
    paths = [config]
    _visit_config(config, profile, ssh_dir, set(), paths, 0)
    return paths


def _visit_config(
    path: Path,
    user_profile: Path,
    ssh_dir: Path,
    visited: set[Path],
    paths: list[Path],
    depth: int,
) -> None:
    if depth == 32:
        return
    try:
        key = path.resolve(strict=True)
    except OSError:
        key = path
    if key in visited:
        return
    visited.add(key)
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in contents.splitlines():
        parsed = _directive(line)
        if parsed is None:
            continue
        key, args = parsed
        lowered = key.lower()
        if lowered == "include":
            for arg in args:
                for included in _include_paths(arg, user_profile, ssh_dir):
                    paths.append(included)
                    _visit_config(
                        included,
                        user_profile,
                        ssh_dir,
                        visited,
                        paths,
                        depth + 1,
                    )
        elif lowered in SSH_PROFILE_PATH_DIRECTIVES:
            for arg in args:
                dependency = _profile_path_arg(arg, user_profile, None)
                if dependency is not None:
                    paths.append(dependency)


def _include_paths(
    arg: str,
    user_profile: Path,
    ssh_dir: Path,
) -> list[Path]:
    pattern_path = _profile_path_arg(arg, user_profile, ssh_dir)
    if pattern_path is None:
        return []
    pattern = str(pattern_path).replace("\\", "/")
    return [Path(match) for match in glob.glob(pattern)]


def _directive(line: str) -> tuple[str, list[str]] | None:
    words = _words(line)
    if not words:
        return None
    first = words[0]
    if "=" in first:
        key, value = first.split("=", 1)
        if key:
            args = ([value] if value else []) + words[1:]
            return key, args
    key = words.pop(0)
    if words and words[0].startswith("="):
        words[0] = words[0][1:]
    return key, [word for word in words if word]


def _words(line: str) -> list[str]:
    output: list[str] = []
    word: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(line):
        char = line[index]
        if char == "#" and quote is None:
            break
        if char in {"'", '"'}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        elif char == "\\" and index + 1 < len(line):
            next_char = line[index + 1]
            if next_char in {"'", '"', "\\"} or (
                quote is None and next_char == " "
            ):
                word.append(next_char)
                index += 1
            else:
                word.append(char)
        elif char.isspace() and quote is None:
            if word:
                output.append("".join(word))
                word.clear()
        else:
            word.append(char)
        index += 1
    if word:
        output.append("".join(word))
    return output


def _profile_path_arg(
    arg: str,
    user_profile: Path,
    relative_base: Path | None,
) -> Path | None:
    if arg.lower() == "none":
        return None
    if arg in {"~", "%d", "${HOME}"}:
        return user_profile
    for prefix in (
        "~/",
        "~\\",
        "%d/",
        "%d\\",
        "${HOME}/",
        "${HOME}\\",
    ):
        if arg.startswith(prefix):
            return user_profile / arg[len(prefix) :]
    path = Path(arg)
    if path.is_absolute():
        return path
    return relative_base / path if relative_base is not None else None


__all__ = ["ssh_config_dependency_paths"]
