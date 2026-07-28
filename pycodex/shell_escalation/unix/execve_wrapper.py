"""Entrypoint for the intercepted exec helper."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from .escalate_client import run_shell_escalation_execve_wrapper


@dataclass(frozen=True)
class ExecveWrapperCli:
    file: str
    argv: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.argv, tuple):
            object.__setattr__(self, "argv", tuple(self.argv))

    @classmethod
    def parse(
        cls,
        argv: list[str] | tuple[str, ...] | None = None,
    ) -> "ExecveWrapperCli":
        args = tuple(sys.argv[1:] if argv is None else argv)
        if not args:
            raise ValueError("missing required executable path")
        return cls(args[0], args[1:])


async def main_execve_wrapper(
    argv: list[str] | tuple[str, ...] | None = None,
) -> int:
    parsed = ExecveWrapperCli.parse(argv)
    return await run_shell_escalation_execve_wrapper(
        parsed.file,
        list(parsed.argv),
    )


__all__ = ["ExecveWrapperCli", "main_execve_wrapper"]
