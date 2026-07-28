"""Platform-specific MCP server program resolution."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


def _environment_value(environment: Mapping[str, str], name: str) -> str | None:
    if name in environment:
        return str(environment[name])
    name_lower = name.lower()
    return next(
        (
            str(value)
            for key, value in environment.items()
            if str(key).lower() == name_lower
        ),
        None,
    )


def resolve(
    program: str | os.PathLike[str],
    environment: Mapping[str, str],
    cwd: str | os.PathLike[str],
) -> str:
    value = os.fspath(program)
    if os.name != "nt":
        return value

    cwd_path = Path(cwd)
    program_path = Path(value)
    if program_path.parent != Path(".") or program_path.drive:
        roots = (cwd_path,)
    else:
        raw_path = _environment_value(environment, "PATH")
        roots = tuple(
            Path(entry) if Path(entry).is_absolute() else cwd_path / entry
            for entry in (raw_path or os.defpath).split(os.pathsep)
            if entry
        )

    raw_extensions = _environment_value(environment, "PATHEXT")
    extensions = tuple(
        extension if extension.startswith(".") else f".{extension}"
        for extension in (raw_extensions or ".COM;.EXE;.BAT;.CMD").split(";")
        if extension
    )
    if program_path.suffix:
        names = (program_path.name,)
    else:
        names = (program_path.name, *(program_path.name + ext for ext in extensions))

    for root in roots:
        base = program_path if program_path.parent != Path(".") else Path(program_path.name)
        for name in names:
            candidate = root / base.with_name(name)
            if candidate.is_file():
                return str(candidate.resolve())
    return value


__all__ = ["resolve"]
