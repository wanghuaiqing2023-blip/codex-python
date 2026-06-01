"""Shell selection helpers ported from ``core/src/shell.rs``."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ShellType(str, Enum):
    ZSH = "zsh"
    BASH = "bash"
    POWERSHELL = "powershell"
    SH = "sh"
    CMD = "cmd"


@dataclass(frozen=True)
class Shell:
    shell_type: ShellType
    shell_path: Path
    shell_snapshot: object | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.shell_type, ShellType):
            object.__setattr__(self, "shell_type", ShellType(str(self.shell_type)))
        if not isinstance(self.shell_path, Path):
            object.__setattr__(self, "shell_path", Path(self.shell_path))

    def name(self) -> str:
        return self.shell_type.value

    def derive_exec_args(self, command: str, use_login_shell: bool = False) -> list[str]:
        if self.shell_type in {ShellType.ZSH, ShellType.BASH, ShellType.SH}:
            shell_path = _posix_shell_path_for_exec(self.shell_path)
            arg = "-lc" if use_login_shell else "-c"
            return [shell_path, arg, command]
        shell_path = str(self.shell_path)
        if self.shell_type is ShellType.POWERSHELL:
            args = [shell_path]
            if not use_login_shell:
                args.append("-NoProfile")
            args.extend(("-Command", command))
            return args
        return [shell_path, "/c", command]


def _posix_shell_path_for_exec(path: Path) -> str:
    value = str(path)
    if "\\" in value:
        return value.replace("\\", "/")
    return value


def empty_shell_snapshot_receiver() -> None:
    return None


def detect_shell_type(shell_path: str | Path) -> ShellType | None:
    name = str(shell_path)
    if name in {"zsh", "sh", "cmd", "bash", "pwsh", "powershell"}:
        return _shell_type_from_name(name)

    previous = None
    current = name
    while current and current != previous:
        candidate = _shell_type_from_name(current)
        if candidate is not None:
            return candidate
        previous = current
        current = _file_stem(current)
    return None


def get_shell_by_model_provided_path(shell_path: str | Path) -> Shell:
    path = Path(shell_path)
    shell_type = detect_shell_type(path)
    if shell_type is None:
        return ultimate_fallback_shell()
    return get_shell(shell_type, path) or ultimate_fallback_shell()


def get_shell(shell_type: ShellType, path: str | Path | None = None) -> Shell | None:
    if not isinstance(shell_type, ShellType):
        shell_type = ShellType(str(shell_type))
    path_value = Path(path) if path is not None else None
    if shell_type is ShellType.ZSH:
        return _get_zsh_shell(path_value)
    if shell_type is ShellType.BASH:
        return _get_bash_shell(path_value)
    if shell_type is ShellType.POWERSHELL:
        return _get_powershell_shell(path_value)
    if shell_type is ShellType.SH:
        return _get_sh_shell(path_value)
    return _get_cmd_shell(path_value)


def default_user_shell() -> Shell:
    return default_user_shell_from_path(get_user_shell_path())


def default_user_shell_from_path(user_shell_path: str | Path | None) -> Shell:
    user_path = Path(user_shell_path) if user_shell_path is not None else None
    if sys.platform == "win32":
        return get_shell(ShellType.POWERSHELL) or ultimate_fallback_shell()

    user_default_shell = None
    if user_path is not None:
        shell_type = detect_shell_type(user_path)
        if shell_type is not None:
            user_default_shell = get_shell(shell_type)

    if sys.platform == "darwin":
        shell_with_fallback = (
            user_default_shell
            or get_shell(ShellType.ZSH)
            or get_shell(ShellType.BASH)
        )
    else:
        shell_with_fallback = (
            user_default_shell
            or get_shell(ShellType.BASH)
            or get_shell(ShellType.ZSH)
        )
    return shell_with_fallback or ultimate_fallback_shell()


def ultimate_fallback_shell() -> Shell:
    if sys.platform == "win32":
        return Shell(ShellType.CMD, Path("cmd.exe"))
    return Shell(ShellType.SH, Path("/bin/sh"))


def get_user_shell_path() -> Path | None:
    if sys.platform == "win32":
        return None
    try:
        import os
        import pwd

        shell = pwd.getpwuid(os.getuid()).pw_shell
        return Path(shell) if shell else None
    except (ImportError, KeyError, OSError):
        return None
    return None


def _get_zsh_shell(path: Path | None = None) -> Shell | None:
    return _shell_from_path(ShellType.ZSH, path, "zsh", ("/bin/zsh",))


def _get_bash_shell(path: Path | None = None) -> Shell | None:
    return _shell_from_path(ShellType.BASH, path, "bash", ("/bin/bash",))


def _get_sh_shell(path: Path | None = None) -> Shell | None:
    return _shell_from_path(ShellType.SH, path, "sh", ("/bin/sh",))


def _get_powershell_shell(path: Path | None = None) -> Shell | None:
    pwsh_fallback = (r"C:\Program Files\PowerShell\7\pwsh.exe",) if sys.platform == "win32" else ("/usr/local/bin/pwsh",)
    powershell_fallback = (
        (r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",)
        if sys.platform == "win32"
        else ()
    )
    return _shell_from_path(
        ShellType.POWERSHELL,
        path,
        "pwsh",
        pwsh_fallback,
    ) or _shell_from_path(
        ShellType.POWERSHELL,
        path,
        "powershell",
        powershell_fallback,
    )


def _get_cmd_shell(path: Path | None = None) -> Shell | None:
    return _shell_from_path(ShellType.CMD, path, "cmd", ())


def _shell_from_path(
    shell_type: ShellType,
    provided_path: Path | None,
    binary_name: str,
    fallback_paths: tuple[str, ...],
) -> Shell | None:
    shell_path = get_shell_path(shell_type, provided_path, binary_name, fallback_paths)
    return Shell(shell_type, shell_path) if shell_path is not None else None


def get_shell_path(
    shell_type: ShellType,
    provided_path: Path | None,
    binary_name: str,
    fallback_paths: tuple[str, ...],
) -> Path | None:
    if provided_path is not None and file_exists(provided_path) is not None:
        return provided_path

    default_path = get_user_shell_path()
    if (
        default_path is not None
        and detect_shell_type(default_path) is shell_type
        and file_exists(default_path) is not None
    ):
        return default_path

    which_path = shutil.which(binary_name)
    if which_path is not None:
        return Path(which_path)

    for fallback in fallback_paths:
        path = file_exists(Path(fallback))
        if path is not None:
            return path
    return None


def file_exists(path: Path) -> Path | None:
    try:
        return path if path.is_file() else None
    except OSError:
        return None


def _shell_type_from_name(name: str) -> ShellType | None:
    if name == "zsh":
        return ShellType.ZSH
    if name == "bash":
        return ShellType.BASH
    if name in {"pwsh", "powershell"}:
        return ShellType.POWERSHELL
    if name == "sh":
        return ShellType.SH
    if name == "cmd":
        return ShellType.CMD
    return None


def _file_stem(value: str) -> str:
    normalized = value.replace("\\", "/").rstrip("/")
    base = normalized.rsplit("/", 1)[-1]
    if "." not in base:
        return base
    return base.rsplit(".", 1)[0]


__all__ = [
    "Shell",
    "ShellType",
    "default_user_shell",
    "default_user_shell_from_path",
    "detect_shell_type",
    "empty_shell_snapshot_receiver",
    "file_exists",
    "get_shell",
    "get_shell_by_model_provided_path",
    "get_shell_path",
    "get_user_shell_path",
    "ultimate_fallback_shell",
]
