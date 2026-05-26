"""Turn environment selection helpers ported from ``core/src/environment_selection.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from pycodex.protocol import CodexErr, TurnEnvironmentSelection


@dataclass(frozen=True)
class TurnEnvironment:
    environment_id: str
    environment: Any
    cwd: Path
    shell: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cwd", Path(self.cwd))

    def selection(self) -> TurnEnvironmentSelection:
        return TurnEnvironmentSelection(self.environment_id, self.cwd)


@dataclass(frozen=True)
class ResolvedTurnEnvironments:
    turn_environments: tuple[TurnEnvironment, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "turn_environments", tuple(self.turn_environments))

    def to_selections(self) -> list[TurnEnvironmentSelection]:
        return [environment.selection() for environment in self.turn_environments]

    def primary(self) -> TurnEnvironment | None:
        return self.turn_environments[0] if self.turn_environments else None

    def primary_environment(self) -> Any | None:
        primary = self.primary()
        return primary.environment if primary is not None else None

    def primary_filesystem(self) -> Any | None:
        environment = self.primary_environment()
        if environment is None:
            return None
        get_filesystem = getattr(environment, "get_filesystem", None)
        if callable(get_filesystem):
            return get_filesystem()
        return None


def default_thread_environment_selections(environment_manager: Any, cwd: Path | str) -> list[TurnEnvironmentSelection]:
    cwd_path = Path(cwd)
    return [
        TurnEnvironmentSelection(str(environment_id), cwd_path)
        for environment_id in environment_manager.default_environment_ids()
    ]


def resolve_environment_selections(
    environment_manager: Any,
    environments: Iterable[TurnEnvironmentSelection | dict[str, object]],
) -> ResolvedTurnEnvironments:
    seen_environment_ids: set[str] = set()
    turn_environments: list[TurnEnvironment] = []

    for selected_environment in environments:
        selection = (
            selected_environment
            if isinstance(selected_environment, TurnEnvironmentSelection)
            else TurnEnvironmentSelection.from_mapping(selected_environment)
        )
        if selection.environment_id in seen_environment_ids:
            raise CodexErr.invalid_request(f"duplicate turn environment id `{selection.environment_id}`")
        seen_environment_ids.add(selection.environment_id)

        environment = environment_manager.get_environment(selection.environment_id)
        if environment is None:
            raise CodexErr.invalid_request(f"unknown turn environment id `{selection.environment_id}`")
        turn_environments.append(
            TurnEnvironment(
                environment_id=selection.environment_id,
                environment=environment,
                cwd=selection.cwd,
                shell=None,
            )
        )

    return ResolvedTurnEnvironments(tuple(turn_environments))


__all__ = [
    "ResolvedTurnEnvironments",
    "TurnEnvironment",
    "default_thread_environment_selections",
    "resolve_environment_selections",
]
