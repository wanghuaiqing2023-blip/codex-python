import sys
import unittest

from pycodex.protocol import (
    CODEX_THREAD_ID_ENV_VAR,
    WINDOWS_DEFAULT_PATHEXT,
    ShellEnvironmentPolicy,
    ShellEnvironmentPolicyInherit,
    ThreadId,
    create_env_from_vars,
    populate_env,
)


def make_vars(pairs):
    return [(key, value) for key, value in pairs]


class ProtocolShellEnvironmentTests(unittest.TestCase):
    def test_inherit_defaults_keep_sensitive_vars(self):
        vars = make_vars(
            [
                ("PATH", "/usr/bin"),
                ("HOME", "/home/user"),
                ("API_KEY", "secret"),
                ("SECRET_TOKEN", "t"),
            ]
        )
        thread_id = str(ThreadId.new())

        result = populate_env(vars, ShellEnvironmentPolicy.default(), thread_id)

        self.assertEqual(
            result,
            {
                "PATH": "/usr/bin",
                "HOME": "/home/user",
                "API_KEY": "secret",
                "SECRET_TOKEN": "t",
                CODEX_THREAD_ID_ENV_VAR: thread_id,
            },
        )

    def test_inherit_with_default_excludes_enabled(self):
        vars = make_vars(
            [
                ("PATH", "/usr/bin"),
                ("HOME", "/home/user"),
                ("API_KEY", "secret"),
                ("SECRET_TOKEN", "t"),
            ]
        )
        policy = ShellEnvironmentPolicy(ignore_default_excludes=False)
        thread_id = str(ThreadId.new())

        result = populate_env(vars, policy, thread_id)

        self.assertEqual(result, {"PATH": "/usr/bin", "HOME": "/home/user", CODEX_THREAD_ID_ENV_VAR: thread_id})

    def test_include_only(self):
        policy = ShellEnvironmentPolicy(ignore_default_excludes=True, include_only=("*PATH",))
        thread_id = str(ThreadId.new())

        result = populate_env(make_vars([("PATH", "/usr/bin"), ("FOO", "bar")]), policy, thread_id)

        self.assertEqual(result, {"PATH": "/usr/bin", CODEX_THREAD_ID_ENV_VAR: thread_id})

    def test_set_overrides(self):
        policy = ShellEnvironmentPolicy(ignore_default_excludes=True, set_values={"NEW_VAR": "42"})
        thread_id = str(ThreadId.new())

        result = populate_env(make_vars([("PATH", "/usr/bin")]), policy, thread_id)

        self.assertEqual(result, {"PATH": "/usr/bin", "NEW_VAR": "42", CODEX_THREAD_ID_ENV_VAR: thread_id})

    def test_populate_env_omits_thread_id_when_missing(self):
        result = populate_env(make_vars([("PATH", "/usr/bin")]), ShellEnvironmentPolicy.default())

        self.assertEqual(result, {"PATH": "/usr/bin"})

    def test_inherit_none_still_applies_set_and_thread_id(self):
        policy = ShellEnvironmentPolicy(
            inherit=ShellEnvironmentPolicyInherit.NONE,
            ignore_default_excludes=True,
            set_values={"ONLY_VAR": "yes"},
        )
        thread_id = str(ThreadId.new())

        result = populate_env(make_vars([("PATH", "/usr/bin"), ("HOME", "/home")]), policy, thread_id)

        self.assertEqual(result, {"ONLY_VAR": "yes", CODEX_THREAD_ID_ENV_VAR: thread_id})

    def test_custom_exclude_patterns_are_case_insensitive(self):
        policy = ShellEnvironmentPolicy(ignore_default_excludes=True, exclude=("*secret*",))

        result = populate_env(make_vars([("Path", "/bin"), ("MY_SECRET", "x"), ("secret_lower", "y")]), policy)

        self.assertEqual(result, {"Path": "/bin"})

    def test_core_inherit_preserves_platform_core_vars_case_insensitively(self):
        if sys.platform == "win32":
            vars = make_vars(
                [
                    ("Shell", "C:\\Program Files\\Git\\bin\\bash.exe"),
                    ("SystemRoot", "C:\\Windows"),
                    ("AppData", "C:\\Users\\codex\\AppData\\Roaming"),
                    ("TmpDir", "C:\\Temp\\custom"),
                    ("OPENAI_API_KEY", "secret"),
                ]
            )
            expected = {
                "Shell": "C:\\Program Files\\Git\\bin\\bash.exe",
                "SystemRoot": "C:\\Windows",
                "AppData": "C:\\Users\\codex\\AppData\\Roaming",
                "TmpDir": "C:\\Temp\\custom",
            }
        else:
            vars = make_vars(
                [
                    ("path", "/usr/bin"),
                    ("home", "/home/codex"),
                    ("TmpDir", "/tmp/custom"),
                    ("OPENAI_API_KEY", "secret"),
                ]
            )
            expected = {"path": "/usr/bin", "home": "/home/codex", "TmpDir": "/tmp/custom"}
        policy = ShellEnvironmentPolicy(inherit=ShellEnvironmentPolicyInherit.CORE, ignore_default_excludes=True)

        result = populate_env(vars, policy)

        self.assertEqual(result, expected)

    @unittest.skipUnless(sys.platform == "win32", "Windows PATHEXT fallback is Windows-only")
    def test_create_env_inserts_pathext_on_windows_when_missing(self):
        policy = ShellEnvironmentPolicy(inherit=ShellEnvironmentPolicyInherit.NONE, ignore_default_excludes=True)

        result = create_env_from_vars([], policy)

        self.assertEqual(result, {"PATHEXT": WINDOWS_DEFAULT_PATHEXT})

    @unittest.skipUnless(sys.platform == "win32", "Windows PATHEXT fallback is Windows-only")
    def test_create_env_preserves_existing_pathext_case_insensitively_on_windows(self):
        policy = ShellEnvironmentPolicy(inherit=ShellEnvironmentPolicyInherit.CORE, ignore_default_excludes=True)

        result = create_env_from_vars(make_vars([("PathExt", ".COM;.EXE;.BAT;.CMD;.PS1")]), policy)
        pathext_vars = [(key, value) for key, value in result.items() if key.lower() == "pathext"]

        self.assertEqual(pathext_vars, [("PathExt", ".COM;.EXE;.BAT;.CMD;.PS1")])


if __name__ == "__main__":
    unittest.main()
