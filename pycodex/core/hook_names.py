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
            object.__setattr__(self, "matcher_aliases", tuple(self.matcher_aliases))

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
