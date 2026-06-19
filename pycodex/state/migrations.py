"""Migration metadata helpers ported from ``codex-state/src/migrations.rs``."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Migrator:
    migrations_path: str
    ignore_missing: bool = False
    locking: bool = True
    no_tx: bool = False
    table_name: str = "_sqlx_migrations"
    create_schemas: tuple[str, ...] = ()


STATE_MIGRATOR = Migrator("./migrations")
LOGS_MIGRATOR = Migrator("./logs_migrations")
GOALS_MIGRATOR = Migrator("./goals_migrations")
MEMORIES_MIGRATOR = Migrator("./memory_migrations")


def runtime_migrator(base: Migrator) -> Migrator:
    if not isinstance(base, Migrator):
        raise TypeError("base must be a Migrator")
    return replace(base, ignore_missing=True)


def runtime_state_migrator() -> Migrator:
    return runtime_migrator(STATE_MIGRATOR)


def runtime_logs_migrator() -> Migrator:
    return runtime_migrator(LOGS_MIGRATOR)


def runtime_goals_migrator() -> Migrator:
    return runtime_migrator(GOALS_MIGRATOR)


def runtime_memories_migrator() -> Migrator:
    return runtime_migrator(MEMORIES_MIGRATOR)


__all__ = [
    "GOALS_MIGRATOR",
    "LOGS_MIGRATOR",
    "MEMORIES_MIGRATOR",
    "STATE_MIGRATOR",
    "Migrator",
    "runtime_goals_migrator",
    "runtime_logs_migrator",
    "runtime_memories_migrator",
    "runtime_migrator",
    "runtime_state_migrator",
]
