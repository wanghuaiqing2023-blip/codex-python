"""Hook-facing tool names and matcher aliases ported from Codex core."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HookToolName:
    """Canonical hook payload name plus matcher-only compatibility aliases."""

    name: str
    matcher_aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.matcher_aliases, tuple):
            raise TypeError("matcher_aliases must be a tuple")
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        for alias in self.matcher_aliases:
            if not isinstance(alias, str):
                raise TypeError("matcher aliases must be strings")

    @classmethod
    def new(cls, name: str) -> "HookToolName":
        return cls(name=name)

    @classmethod
    def apply_patch(cls) -> "HookToolName":
        return cls(name="apply_patch", matcher_aliases=("Write", "Edit"))

    @classmethod
    def spawn_agent(cls) -> "HookToolName":
        return cls(name="spawn_agent", matcher_aliases=("Agent",))

    @classmethod
    def bash(cls) -> "HookToolName":
        return cls.new("Bash")

    def matcher_inputs(self) -> tuple[str, ...]:
        return (self.name, *self.matcher_aliases)


__all__ = ["HookToolName"]
