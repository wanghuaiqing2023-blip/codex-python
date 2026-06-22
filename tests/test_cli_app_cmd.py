import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pycodex.cli import (
    AppCommand,
    CODEX_DMG_URL_ARM64,
    CODEX_DMG_URL_X64,
    candidate_applications_dirs,
    candidate_codex_app_paths,
    default_mac_dmg_url,
    display_windows_workspace_path,
    find_codex_app_in_mount,
    mac_app_install_plan,
    mac_copy_app_bundle_command,
    mac_detach_dmg_command,
    mac_download_dmg_command,
    mac_mount_dmg_command,
    mac_open_app_command,
    parse_hdiutil_attach_mount_point,
    workspace_for_app_command,
)


class CliAppCommandTests(unittest.TestCase):
    def test_workspace_for_app_command_canonicalizes_existing_path(self) -> None:
        # Rust parity: codex-cli/src/app_cmd.rs run_app canonicalizes cmd.path.
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()

            self.assertEqual(workspace_for_app_command(workspace), workspace.resolve())

    def test_workspace_for_app_command_preserves_missing_path(self) -> None:
        # Rust parity: codex-cli/src/app_cmd.rs canonicalize(...).unwrap_or(cmd.path).
        missing = Path("missing-workspace-for-codex-app")

        self.assertEqual(workspace_for_app_command(missing), missing)

    def test_app_command_defaults_match_rust_cli_struct(self) -> None:
        command = AppCommand()

        self.assertEqual(command.path, Path("."))
        self.assertIsNone(command.download_url_override)

    def test_display_windows_workspace_path_matches_rust_extended_prefix_handling(self) -> None:
        # Rust parity: codex-cli/src/desktop_app/windows.rs display_workspace_path.
        self.assertEqual(
            display_windows_workspace_path(r"\\?\C:\Users\fcoury\code\codex"),
            r"C:\Users\fcoury\code\codex",
        )
        self.assertEqual(
            display_windows_workspace_path(r"\\?\UNC\server\share\codex"),
            r"\\server\share\codex",
        )
        self.assertEqual(
            display_windows_workspace_path(r"C:\Users\fcoury\code\codex"),
            r"C:\Users\fcoury\code\codex",
        )

    def test_parse_hdiutil_attach_mount_point_matches_rust(self) -> None:
        # Rust parity: codex-cli/src/desktop_app/mac.rs parse_hdiutil_attach_mount_point.
        self.assertEqual(
            parse_hdiutil_attach_mount_point("/dev/disk2s1\tApple_HFS\tCodex\t/Volumes/Codex\n"),
            "/Volumes/Codex",
        )
        self.assertEqual(
            parse_hdiutil_attach_mount_point(
                "/dev/disk2s1\tApple_HFS\tCodex Installer\t/Volumes/Codex Installer\n"
            ),
            "/Volumes/Codex Installer",
        )
        self.assertIsNone(parse_hdiutil_attach_mount_point("/dev/disk2s1\tApple_HFS\tCodex\n"))

    def test_mac_app_command_shapes_match_rust(self) -> None:
        # Rust parity: codex-cli/src/desktop_app/mac.rs command and path helpers.
        self.assertEqual(
            candidate_codex_app_paths("/Users/alice"),
            (Path("/Applications/Codex.app"), Path("/Users/alice/Applications/Codex.app")),
        )
        self.assertEqual(
            candidate_applications_dirs("/Users/alice"),
            (Path("/Applications"), Path("/Users/alice/Applications")),
        )
        self.assertEqual(default_mac_dmg_url("aarch64"), CODEX_DMG_URL_ARM64)
        self.assertEqual(default_mac_dmg_url("x86_64"), CODEX_DMG_URL_X64)
        self.assertEqual(default_mac_dmg_url("x86_64", translated=True), CODEX_DMG_URL_ARM64)
        self.assertEqual(
            mac_open_app_command("/Applications/Codex.app", "/repo"),
            ("open", "-a", "/Applications/Codex.app", "/repo"),
        )
        self.assertEqual(
            mac_download_dmg_command("https://example.test/Codex.dmg", "/tmp/Codex.dmg"),
            (
                "curl",
                "-fL",
                "--retry",
                "3",
                "--retry-delay",
                "1",
                "-o",
                "/tmp/Codex.dmg",
                "https://example.test/Codex.dmg",
            ),
        )
        self.assertEqual(
            mac_mount_dmg_command("/tmp/Codex.dmg"),
            ("hdiutil", "attach", "-nobrowse", "-readonly", "/tmp/Codex.dmg"),
        )
        self.assertEqual(mac_detach_dmg_command("/Volumes/Codex"), ("hdiutil", "detach", "/Volumes/Codex"))
        self.assertEqual(
            mac_copy_app_bundle_command("/Volumes/Codex/Codex.app", "/Users/alice/Applications/Codex.app"),
            ("ditto", "/Volumes/Codex/Codex.app", "/Users/alice/Applications/Codex.app"),
        )
        plan = mac_app_install_plan("https://example.test/Codex.dmg")
        self.assertEqual(plan.temp_dir_prefix, "codex-app-installer-")
        self.assertEqual(plan.dmg_filename, "Codex.dmg")

    def test_find_codex_app_in_mount_matches_rust_priority(self) -> None:
        # Rust parity: codex-cli/src/desktop_app/mac.rs find_codex_app_in_mount.
        with TemporaryDirectory() as tmp:
            mount = Path(tmp)
            direct = mount / "Codex.app"
            other = mount / "Other.app"
            direct.mkdir()
            other.mkdir()
            self.assertEqual(find_codex_app_in_mount(mount), direct)

        with TemporaryDirectory() as tmp:
            mount = Path(tmp)
            other = mount / "Other.app"
            other.mkdir()
            self.assertEqual(find_codex_app_in_mount(mount), other)


if __name__ == "__main__":
    unittest.main()
