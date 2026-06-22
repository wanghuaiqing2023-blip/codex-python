import unittest
from unittest.mock import patch

from pycodex.protocol import ShellEnvironmentPolicy, ShellEnvironmentPolicyInherit
from pycodex.protocol.shell_environment import (
    CODEX_THREAD_ID_ENV_VAR,
    WINDOWS_DEFAULT_PATHEXT,
    create_env_from_vars,
    populate_env,
)


class ProtocolShellEnvironmentTests(unittest.TestCase):
    def test_core_inherit_preserves_non_windows_core_vars_case_insensitively(self) -> None:
        # Rust: codex-protocol/src/shell_environment.rs
        # Rust test: core_inherit_preserves_non_windows_core_vars_case_insensitively
        vars = [
            ("path", "/usr/bin"),
            ("home", "/home/codex"),
            ("TmpDir", "/tmp/custom"),
            ("OPENAI_API_KEY", "secret"),
        ]
        policy = ShellEnvironmentPolicy(
            inherit=ShellEnvironmentPolicyInherit.CORE,
            ignore_default_excludes=True,
        )

        with patch("pycodex.protocol.shell_environment.sys.platform", "linux"):
            self.assertEqual(
                populate_env(vars, policy),
                {
                    "path": "/usr/bin",
                    "home": "/home/codex",
                    "TmpDir": "/tmp/custom",
                },
            )

    def test_core_inherit_preserves_windows_startup_vars_case_insensitively(self) -> None:
        # Rust: codex-protocol/src/shell_environment.rs
        # Rust test: core_inherit_preserves_windows_startup_vars_case_insensitively
        vars = [
            ("Shell", r"C:\Program Files\Git\bin\bash.exe"),
            ("SystemRoot", r"C:\Windows"),
            ("AppData", r"C:\Users\codex\AppData\Roaming"),
            ("TmpDir", r"C:\Temp\custom"),
            ("OPENAI_API_KEY", "secret"),
        ]
        policy = ShellEnvironmentPolicy(
            inherit=ShellEnvironmentPolicyInherit.CORE,
            ignore_default_excludes=True,
        )

        with patch("pycodex.protocol.shell_environment.sys.platform", "win32"):
            self.assertEqual(
                populate_env(vars, policy),
                {
                    "Shell": r"C:\Program Files\Git\bin\bash.exe",
                    "SystemRoot": r"C:\Windows",
                    "AppData": r"C:\Users\codex\AppData\Roaming",
                    "TmpDir": r"C:\Temp\custom",
                },
            )

    def test_default_excludes_custom_excludes_set_include_only_and_thread_id_order(self) -> None:
        # Rust behavior: populate_env applies inherit, default excludes, custom
        # excludes, set overrides, include_only, then thread id insertion.
        vars = [
            ("PATH", "/bin"),
            ("OPENAI_API_KEY", "secret"),
            ("SESSION_TOKEN", "secret"),
            ("DROP_ME", "drop"),
            ("KEEP_ME", "keep"),
        ]
        policy = ShellEnvironmentPolicy(
            inherit=ShellEnvironmentPolicyInherit.ALL,
            ignore_default_excludes=False,
            exclude=("DROP_*",),
            set_values={"OPENAI_API_KEY": "override", "ADDED": "value"},
            include_only=("PATH", "OPENAI_*", "ADDED"),
        )

        self.assertEqual(
            populate_env(vars, policy, thread_id="thread-123"),
            {
                "PATH": "/bin",
                "OPENAI_API_KEY": "override",
                "ADDED": "value",
                CODEX_THREAD_ID_ENV_VAR: "thread-123",
            },
        )

    def test_create_env_inserts_pathext_on_windows_when_missing(self) -> None:
        # Rust: codex-protocol/src/shell_environment.rs
        # Rust test: create_env_inserts_pathext_on_windows_when_missing
        policy = ShellEnvironmentPolicy(
            inherit=ShellEnvironmentPolicyInherit.NONE,
            ignore_default_excludes=True,
        )

        with patch("pycodex.protocol.shell_environment.sys.platform", "win32"):
            self.assertEqual(create_env_from_vars([], policy), {"PATHEXT": WINDOWS_DEFAULT_PATHEXT})
            self.assertEqual(create_env_from_vars([("pathext", ".EXE")], ShellEnvironmentPolicy()), {"pathext": ".EXE"})

    def test_rejects_invalid_policy_thread_id_and_environment_pairs(self) -> None:
        with self.assertRaisesRegex(TypeError, "policy must be a ShellEnvironmentPolicy"):
            populate_env([], object())  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "thread_id must be a string or None"):
            populate_env([], ShellEnvironmentPolicy(), thread_id=123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "environment variables must be key/value pairs"):
            populate_env(["PATH=/bin"], ShellEnvironmentPolicy())  # type: ignore[list-item]
        with self.assertRaisesRegex(TypeError, "environment variable keys and values must be strings"):
            populate_env([("PATH", 123)], ShellEnvironmentPolicy())  # type: ignore[list-item]


if __name__ == "__main__":
    unittest.main()
