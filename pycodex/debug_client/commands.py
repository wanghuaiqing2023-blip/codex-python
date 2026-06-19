"""Interactive command parsing for Rust ``codex-debug-client/src/commands.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class UserCommand(str, Enum):
    HELP = "Help"
    QUIT = "Quit"
    NEW_THREAD = "NewThread"
    RESUME = "Resume"
    USE = "Use"
    REFRESH_THREAD = "RefreshThread"


@dataclass(frozen=True)
class InputAction:
    kind: str
    value: str | UserCommand | None = None

    @classmethod
    def message(cls, text: str) -> "InputAction":
        return cls("Message", text)

    @classmethod
    def command(cls, command: UserCommand, argument: str | None = None) -> "InputAction":
        if argument is None:
            return cls("Command", command)
        return cls("Command", (command, argument))  # type: ignore[arg-type]

    @classmethod
    def help(cls) -> "InputAction":
        return cls.command(UserCommand.HELP)

    @classmethod
    def quit(cls) -> "InputAction":
        return cls.command(UserCommand.QUIT)

    @classmethod
    def new_thread(cls) -> "InputAction":
        return cls.command(UserCommand.NEW_THREAD)

    @classmethod
    def resume(cls, thread_id: str) -> "InputAction":
        return cls.command(UserCommand.RESUME, thread_id)

    @classmethod
    def use(cls, thread_id: str) -> "InputAction":
        return cls.command(UserCommand.USE, thread_id)

    @classmethod
    def refresh_thread(cls) -> "InputAction":
        return cls.command(UserCommand.REFRESH_THREAD)

    @property
    def command_name(self) -> UserCommand | None:
        if self.kind != "Command":
            return None
        if isinstance(self.value, tuple):
            return self.value[0]
        if isinstance(self.value, UserCommand):
            return self.value
        return None

    @property
    def argument(self) -> str | None:
        if self.kind == "Command" and isinstance(self.value, tuple):
            return self.value[1]
        return None


class ParseErrorKind(str, Enum):
    EMPTY_COMMAND = "EmptyCommand"
    MISSING_ARGUMENT = "MissingArgument"
    UNKNOWN_COMMAND = "UnknownCommand"


@dataclass(frozen=True)
class ParseError(Exception):
    kind: ParseErrorKind
    name: str | None = None
    command: str | None = None

    @classmethod
    def empty_command(cls) -> "ParseError":
        return cls(ParseErrorKind.EMPTY_COMMAND)

    @classmethod
    def missing_argument(cls, name: str) -> "ParseError":
        return cls(ParseErrorKind.MISSING_ARGUMENT, name=name)

    @classmethod
    def unknown_command(cls, command: str) -> "ParseError":
        return cls(ParseErrorKind.UNKNOWN_COMMAND, command=command)

    def message(self) -> str:
        if self.kind is ParseErrorKind.EMPTY_COMMAND:
            return "empty command after ':'"
        if self.kind is ParseErrorKind.MISSING_ARGUMENT:
            return f"missing required argument: {self.name}"
        if self.kind is ParseErrorKind.UNKNOWN_COMMAND:
            return f"unknown command: {self.command}"
        raise ValueError(f"unknown parse error kind: {self.kind}")

    def __str__(self) -> str:
        return self.message()


def parse_input(line: str) -> InputAction | None:
    trimmed = str(line).strip()
    if not trimmed:
        return None
    if not trimmed.startswith(":"):
        return InputAction.message(trimmed)

    command_line = trimmed[1:]
    parts = command_line.split()
    if not parts:
        raise ParseError.empty_command()

    command = parts[0]
    if command in {"help", "h"}:
        return InputAction.help()
    if command in {"quit", "q", "exit"}:
        return InputAction.quit()
    if command == "new":
        return InputAction.new_thread()
    if command == "resume":
        if len(parts) < 2:
            raise ParseError.missing_argument("thread-id")
        return InputAction.resume(parts[1])
    if command == "use":
        if len(parts) < 2:
            raise ParseError.missing_argument("thread-id")
        return InputAction.use(parts[1])
    if command == "refresh-thread":
        return InputAction.refresh_thread()
    raise ParseError.unknown_command(command)


__all__ = [
    "InputAction",
    "ParseError",
    "ParseErrorKind",
    "UserCommand",
    "parse_input",
]
