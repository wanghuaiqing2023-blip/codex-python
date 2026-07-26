from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .fragment import ContextualUserFragmentBase


@dataclass(frozen=True)
class UserShellCommand(ContextualUserFragmentBase):
    command: str
    exit_code: int
    duration_seconds: float
    output: str

    @classmethod
    def new(
        cls,
        command: str,
        exit_code: int,
        duration: timedelta,
        output: str,
    ) -> "UserShellCommand":
        return cls(command, exit_code, duration.total_seconds(), output)

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "<user_shell_command>", "</user_shell_command>"

    def body(self) -> str:
        return (
            f"\n<command>\n{self.command}\n</command>\n<result>\n"
            f"Exit code: {self.exit_code}\nDuration: {self.duration_seconds:.4f} seconds\n"
            f"Output:\n{self.output}\n</result>\n"
        )


__all__ = ["UserShellCommand"]
