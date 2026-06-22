"""Port of Rust ``codex-cloud-tasks/src/new_task.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field

from pycodex.tui.public_widgets.composer_input import ComposerInput


NEW_TASK_HINT_ITEMS: tuple[tuple[str, str], ...] = (
    ("Enter", "send"),
    ("Shift+Enter", "newline"),
    ("Ctrl+O", "env"),
    ("Ctrl+N", "attempts"),
    ("Ctrl+C", "quit"),
)


@dataclass
class NewTaskPage:
    composer: ComposerInput = field(default_factory=ComposerInput)
    submitting: bool = False
    env_id: str | None = None
    best_of_n: int = 1

    @classmethod
    def new(cls, env_id: str | None, best_of_n: int) -> "NewTaskPage":
        composer = ComposerInput.new()
        composer.set_hint_items(NEW_TASK_HINT_ITEMS)
        return cls(
            composer=composer,
            submitting=False,
            env_id=env_id,
            best_of_n=best_of_n,
        )

    @classmethod
    def default(cls) -> "NewTaskPage":
        return cls.new(None, 1)


__all__ = ["NEW_TASK_HINT_ITEMS", "NewTaskPage"]
