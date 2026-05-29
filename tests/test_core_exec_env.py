from __future__ import annotations

import sys
import unittest

from pycodex.core import (
    CODEX_THREAD_ID_ENV_VAR,
    create_env_from_vars,
    populate_env,
)
from pycodex.protocol import ShellEnvironmentPolicy, ShellEnvironmentPolicyInherit, ThreadId


def make_vars(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(key, value) for key, value in pairs]


class CoreExecEnvTests(unittest.TestCase):
    def test_core_inherit_defaults_keep_sensitive_vars(self) -> None:
        vars = make_vars(
            [
                ("PATH", "/usr/bin"),
                ("HOME", "/home/user"),
                ("API_KEY", "secret"),
                ("SECRET_TOKEN", "t"),
            ]
        )

        thread_id = ThreadId.new()
        result = populate_env(vars, ShellEnvironmentPolicy.default(), thread_id)

        self.assertEqual(
            result,
            {
                "PATH": "/usr/bin",
                "HOME": "/home/user",
                "API_KEY": "secret",
                "SECRET_TOKEN": "t",
                CODEX_THREAD_ID_ENV_VAR: thread_id.to_json(),
            },
        )

    def test_core_inherit_with_default_excludes_enabled(self) -> None:
        vars = make_vars(
            [
                ("PATH", "/usr/bin"),
                ("HOME", "/home/user"),
                ("API_KEY", "secret"),
                ("SECRET_TOKEN", "t"),
            ]
        )
        policy = ShellEnvironmentPolicy(ignore_default_excludes=False)

        thread_id = ThreadId.new()
        result = populate_env(vars, policy, thread_id)

        self.assertEqual(
            result,
            {
                "PATH": "/usr/bin",
                "HOME": "/home/user",
                CODEX_THREAD_ID_ENV_VAR: thread_id.to_json(),
            },
        )

    def test_include_only_still_inserts_thread_id(self) -> None:
        policy = ShellEnvironmentPolicy(
            ignore_default_excludes=True,
            include_only=("*PATH",),
        )

        thread_id = ThreadId.new()
        result = populate_env(make_vars([("PATH", "/usr/bin"), ("FOO", "bar")]), policy, thread_id)

        self.assertEqual(result, {"PATH": "/usr/bin", CODEX_THREAD_ID_ENV_VAR: thread_id.to_json()})

    def test_set_overrides(self) -> None:
        policy = ShellEnvironmentPolicy(ignore_default_excludes=True, set_values={"NEW_VAR": "42"})

        thread_id = ThreadId.new()
        result = populate_env(make_vars([("PATH", "/usr/bin")]), policy, thread_id)

        self.assertEqual(result, {"PATH": "/usr/bin", "NEW_VAR": "42", CODEX_THREAD_ID_ENV_VAR: thread_id.to_json()})

    def test_populate_env_omits_thread_id_when_missing(self) -> None:
        result = populate_env(make_vars([("PATH", "/usr/bin")]), ShellEnvironmentPolicy.default())

        self.assertEqual(result, {"PATH": "/usr/bin"})

    def test_inherit_all_and_none_match_upstream_core_wrapper(self) -> None:
        all_policy = ShellEnvironmentPolicy(
            inherit=ShellEnvironmentPolicyInherit.ALL,
            ignore_default_excludes=True,
        )
        none_policy = ShellEnvironmentPolicy(
            inherit=ShellEnvironmentPolicyInherit.NONE,
            ignore_default_excludes=True,
            set_values={"ONLY_VAR": "yes"},
        )

        thread_id = ThreadId.new()
        self.assertEqual(
            populate_env(make_vars([("PATH", "/usr/bin"), ("FOO", "bar")]), all_policy, thread_id),
            {"PATH": "/usr/bin", "FOO": "bar", CODEX_THREAD_ID_ENV_VAR: thread_id.to_json()},
        )
        self.assertEqual(
            populate_env(make_vars([("PATH", "/usr/bin"), ("HOME", "/home")]), none_policy, thread_id),
            {"ONLY_VAR": "yes", CODEX_THREAD_ID_ENV_VAR: thread_id.to_json()},
        )

    def test_core_wrapper_rejects_non_thread_id_values(self) -> None:
        with self.assertRaises(TypeError):
            populate_env(make_vars([("PATH", "/usr/bin")]), ShellEnvironmentPolicy.default(), "thread-1")


    def test_core_wrapper_rejects_implicit_env_coercions(self) -> None:
        with self.assertRaises(TypeError):
            populate_env(make_vars([("PATH", "/usr/bin")]), "default")
        with self.assertRaises(TypeError):
            populate_env([("PATH", 123)], ShellEnvironmentPolicy.default())
        with self.assertRaises(TypeError):
            populate_env([["PATH", "/usr/bin"]], ShellEnvironmentPolicy.default())

    @unittest.skipUnless(sys.platform == "win32", "PATHEXT insertion is Windows-specific upstream")
    def test_create_env_inserts_pathext_on_windows_when_missing(self) -> None:
        policy = ShellEnvironmentPolicy(
            inherit=ShellEnvironmentPolicyInherit.NONE,
            ignore_default_excludes=True,
        )

        result = create_env_from_vars([], policy)

        self.assertEqual(result, {"PATHEXT": ".COM;.EXE;.BAT;.CMD"})


if __name__ == "__main__":
    unittest.main()
