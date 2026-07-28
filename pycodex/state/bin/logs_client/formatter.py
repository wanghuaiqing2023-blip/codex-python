"""Formatter inline module from ``logs_client.rs``."""

from __future__ import annotations

from datetime import UTC, datetime

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"


def _style(value: str, code: int, *, bold: bool = False) -> str:
    prefix = f"\x1b[{code}m"
    if bold:
        prefix = _BOLD + prefix
    return f"{prefix}{value}{_RESET}"


def dim(value: str) -> str:
    return f"{_DIM}{value}{_RESET}"


def blue_dim(value: str) -> str:
    return f"{_DIM}\x1b[34m{value}{_RESET}"


def bold(value: str) -> str:
    return f"{_BOLD}{value}{_RESET}"


def apply_patch(message: str) -> str:
    lines = []
    for line in message.splitlines():
        if line.startswith("+"):
            lines.append(_style(line, 32, bold=True))
        elif line.startswith("-"):
            lines.append(_style(line, 31, bold=True))
        else:
            lines.append(bold(line))
    return "\n".join(lines)


def ts(seconds: int, nanos: int, compact: bool) -> str:
    try:
        value = datetime.fromtimestamp(seconds + max(nanos, 0) / 1_000_000_000, UTC)
    except (OSError, OverflowError, ValueError):
        return f"{seconds}.{nanos:09}Z"
    if compact:
        return value.strftime("%H:%M:%S")
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def level(value: str) -> str:
    padded = f"{value:<5}"
    colors = {
        "error": 31,
        "warn": 33,
        "info": 32,
        "debug": 34,
        "trace": 35,
    }
    code = colors.get(value.lower())
    return bold(padded) if code is None else _style(padded, code, bold=True)


__all__ = ["apply_patch", "blue_dim", "bold", "dim", "level", "ts"]
