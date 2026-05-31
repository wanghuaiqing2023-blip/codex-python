import tempfile
import unittest
from pathlib import Path
import sys

from pycodex.core.windows_sandbox_read_grants import (
    WindowsSandboxReadGrantError,
    grant_read_root_non_elevated,
)
from pycodex.protocol.models import PermissionProfile


def permission_profile() -> PermissionProfile:
    return PermissionProfile.workspace_write()


class WindowsSandboxReadGrantsTests(unittest.TestCase):
    def test_rejects_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with self.assertRaisesRegex(WindowsSandboxReadGrantError, "path must be absolute"):
                grant_read_root_non_elevated(
                    permission_profile(),
                    tmp_path,
                    tmp_path,
                    {},
                    tmp_path,
                    Path("relative"),
                )

    def test_rejects_missing_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            missing = tmp_path / "does-not-exist"
            with self.assertRaisesRegex(WindowsSandboxReadGrantError, "path does not exist"):
                grant_read_root_non_elevated(
                    permission_profile(),
                    tmp_path,
                    tmp_path,
                    {},
                    tmp_path,
                    missing,
                )

    def test_rejects_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            file_path = tmp_path / "file.txt"
            file_path.write_text("hello", encoding="utf-8")
            with self.assertRaisesRegex(WindowsSandboxReadGrantError, "path must be a directory"):
                grant_read_root_non_elevated(
                    permission_profile(),
                    tmp_path,
                    tmp_path,
                    {},
                    tmp_path,
                    file_path,
                )

    def test_canonicalizes_and_calls_setup_refresher(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            calls = []

            def refresher(
                received_profile,
                received_profile_cwd,
                received_command_cwd,
                received_env,
                received_home,
                received_roots,
            ) -> None:
                calls.append(
                    (
                        received_profile,
                        received_profile_cwd,
                        received_command_cwd,
                        received_env,
                        received_home,
                        tuple(received_roots),
                    )
                )

            result = grant_read_root_non_elevated(
                permission_profile(),
                tmp_path,
                tmp_path,
                {"A": "B"},
                tmp_path,
                tmp_path,
                setup_refresher=refresher,
            )

            self.assertEqual(result, tmp_path.resolve())
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1], tmp_path)
            self.assertEqual(calls[0][2], tmp_path)
            self.assertEqual(calls[0][3], {"A": "B"})
            self.assertEqual(calls[0][4], tmp_path)
            self.assertEqual(calls[0][5], (tmp_path.resolve(),))

    def test_default_success_path_requires_real_setup_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            if sys.platform == "win32":
                with self.assertRaisesRegex(NotImplementedError, "not implemented"):
                    grant_read_root_non_elevated(
                        permission_profile(),
                        tmp_path,
                        tmp_path,
                        {},
                        tmp_path,
                        tmp_path,
                    )
            else:
                self.assertEqual(
                    grant_read_root_non_elevated(
                        permission_profile(),
                        tmp_path,
                        tmp_path,
                        {},
                        tmp_path,
                        tmp_path,
                    ),
                    tmp_path.resolve(),
                )

    def test_rejects_non_permission_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with self.assertRaisesRegex(TypeError, "permission_profile must be a PermissionProfile"):
                grant_read_root_non_elevated(
                    object(),  # type: ignore[arg-type]
                    tmp_path,
                    tmp_path,
                    {},
                    tmp_path,
                    tmp_path,
                )

    def test_rejects_non_string_path_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with self.assertRaisesRegex(TypeError, "permission_profile_cwd must be a path"):
                grant_read_root_non_elevated(
                    permission_profile(),
                    123,  # type: ignore[arg-type]
                    tmp_path,
                    {},
                    tmp_path,
                    tmp_path,
                )
            with self.assertRaisesRegex(TypeError, "command_cwd must be a path"):
                grant_read_root_non_elevated(
                    permission_profile(),
                    tmp_path,
                    123,  # type: ignore[arg-type]
                    {},
                    tmp_path,
                    tmp_path,
                )
            with self.assertRaisesRegex(TypeError, "codex_home must be a path"):
                grant_read_root_non_elevated(
                    permission_profile(),
                    tmp_path,
                    tmp_path,
                    {},
                    123,  # type: ignore[arg-type]
                    tmp_path,
                )
            with self.assertRaisesRegex(TypeError, "read_root must be a path"):
                grant_read_root_non_elevated(
                    permission_profile(),
                    tmp_path,
                    tmp_path,
                    {},
                    tmp_path,
                    123,  # type: ignore[arg-type]
                )

    def test_rejects_non_string_env_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with self.assertRaisesRegex(TypeError, "env_map must map strings to strings"):
                grant_read_root_non_elevated(
                    permission_profile(),
                    tmp_path,
                    tmp_path,
                    {"A": 1},  # type: ignore[dict-item]
                    tmp_path,
                    tmp_path,
                )


if __name__ == "__main__":
    unittest.main()
