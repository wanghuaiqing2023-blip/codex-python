from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unittest

from pycodex.core.environment_selection import (
    ResolvedTurnEnvironments,
    TurnEnvironment,
    default_thread_environment_selections,
    resolve_environment_selections,
)
from pycodex.protocol import CodexErr, TurnEnvironmentSelection


@dataclass(frozen=True)
class FakeEnvironment:
    filesystem: str

    def get_filesystem(self) -> str:
        return self.filesystem


class FakeEnvironmentManager:
    def __init__(self, environments: dict[str, FakeEnvironment], defaults: tuple[str, ...] = ()) -> None:
        self.environments = environments
        self.defaults = defaults

    def default_environment_ids(self) -> tuple[str, ...]:
        return self.defaults

    def get_environment(self, environment_id: str) -> FakeEnvironment | None:
        return self.environments.get(environment_id)


class EnvironmentSelectionTests(unittest.TestCase):
    def test_default_thread_environment_selections_use_manager_default_ids(self) -> None:
        manager = FakeEnvironmentManager({}, ("local", "remote"))

        self.assertEqual(
            default_thread_environment_selections(manager, Path("/repo")),
            [
                TurnEnvironmentSelection("local", Path("/repo")),
                TurnEnvironmentSelection("remote", Path("/repo")),
            ],
        )

    def test_resolve_environment_selections_rejects_duplicate_ids(self) -> None:
        manager = FakeEnvironmentManager({"local": FakeEnvironment("fs")})

        with self.assertRaisesRegex(CodexErr, "duplicate turn environment id `local`"):
            resolve_environment_selections(
                manager,
                (
                    TurnEnvironmentSelection("local", Path("/repo")),
                    TurnEnvironmentSelection("local", Path("/other")),
                ),
            )

    def test_resolve_environment_selections_rejects_unknown_ids(self) -> None:
        manager = FakeEnvironmentManager({})

        with self.assertRaisesRegex(CodexErr, "unknown turn environment id `remote`"):
            resolve_environment_selections(manager, (TurnEnvironmentSelection("remote", Path("/repo")),))

    def test_resolved_environment_selections_use_first_selection_as_primary(self) -> None:
        local = FakeEnvironment("local-fs")
        remote = FakeEnvironment("remote-fs")
        manager = FakeEnvironmentManager({"local": local, "remote": remote})

        resolved = resolve_environment_selections(
            manager,
            (
                {"environment_id": "remote", "cwd": str(Path("/selected"))},
                TurnEnvironmentSelection("local", Path("/repo")),
            ),
        )

        self.assertEqual(
            resolved.to_selections(),
            [
                TurnEnvironmentSelection("remote", Path("/selected")),
                TurnEnvironmentSelection("local", Path("/repo")),
            ],
        )
        self.assertEqual(
            resolved.primary(),
            TurnEnvironment("remote", remote, Path("/selected"), shell=None),
        )
        self.assertIs(resolved.primary_environment(), remote)
        self.assertEqual(resolved.primary_filesystem(), "remote-fs")

    def test_empty_resolved_environment_has_no_primary(self) -> None:
        resolved = ResolvedTurnEnvironments()

        self.assertEqual(resolved.to_selections(), [])
        self.assertIsNone(resolved.primary())
        self.assertIsNone(resolved.primary_environment())
        self.assertIsNone(resolved.primary_filesystem())


if __name__ == "__main__":
    unittest.main()
