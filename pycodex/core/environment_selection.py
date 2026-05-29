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
        if not isinstance(self.environment_id, str):
            raise TypeError("environment_id must be a string")
        if self.shell is not None and not isinstance(self.shell, str):
            raise TypeError("shell must be a string or None")
        if not isinstance(self.cwd, Path | str):
            raise TypeError("cwd must be a path")
        object.__setattr__(self, "cwd", Path(self.cwd))

    def selection(self) -> TurnEnvironmentSelection:
        return TurnEnvironmentSelection(self.environment_id, self.cwd)


@dataclass(frozen=True)
class ResolvedTurnEnvironments:
    turn_environments: tuple[TurnEnvironment, ...] = ()

    def __post_init__(self) -> None:
        turn_environments = tuple(self.turn_environments)
        if any(not isinstance(environment, TurnEnvironment) for environment in turn_environments):
            raise TypeError("turn_environments must contain TurnEnvironment values")
        object.__setattr__(self, "turn_environments", turn_environments)

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
    default_environment_ids = getattr(environment_manager, "default_environment_ids", None)
    if not callable(default_environment_ids):
        raise TypeError("environment_manager must expose default_environment_ids()")
    if not isinstance(cwd, Path | str):
        raise TypeError("cwd must be a path")
    cwd_path = Path(cwd)
    selections: list[TurnEnvironmentSelection] = []
    for environment_id in default_environment_ids():
        if not isinstance(environment_id, str):
            raise TypeError("default environment ids must be strings")
        selections.append(TurnEnvironmentSelection(environment_id, cwd_path))
    return selections


def resolve_environment_selections(
    environment_manager: Any,
    environments: Iterable[TurnEnvironmentSelection],
) -> ResolvedTurnEnvironments:
    get_environment = getattr(environment_manager, "get_environment", None)
    if not callable(get_environment):
        raise TypeError("environment_manager must expose get_environment()")
    if isinstance(environments, dict | str):
        raise TypeError("environments must be an iterable of TurnEnvironmentSelection values")
    seen_environment_ids: set[str] = set()
    turn_environments: list[TurnEnvironment] = []

    for selection in environments:
        if not isinstance(selection, TurnEnvironmentSelection):
            raise TypeError("environments must contain TurnEnvironmentSelection values")
        if selection.environment_id in seen_environment_ids:
            raise CodexErr.invalid_request(f"duplicate turn environment id `{selection.environment_id}`")
        seen_environment_ids.add(selection.environment_id)

        environment = get_environment(selection.environment_id)
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
