from pathlib import Path
import sys
import unittest

from pycodex.core.config.permissions import (
    BUILT_IN_DANGER_FULL_ACCESS_PROFILE,
    BUILT_IN_READ_ONLY_PROFILE,
    BUILT_IN_WORKSPACE_PROFILE,
    ProjectTrust,
    SandboxWorkspaceWrite,
    apply_network_proxy_feature_config,
    builtin_permission_profile,
    compile_filesystem_access_path,
    compile_filesystem_path,
    compile_filesystem_permission,
    compile_network_sandbox_policy,
    compile_permission_profile,
    compile_read_write_glob_path,
    compile_permission_profile_selection,
    compile_permission_profile_workspace_roots,
    compile_scoped_filesystem_path,
    compile_scoped_filesystem_pattern,
    compile_workspace_roots,
    contains_glob_chars_for_platform,
    default_builtin_permission_profile_name,
    get_readable_roots_required_for_codex_runtime,
    is_builtin_permission_profile_name,
    normalize_absolute_path_for_platform,
    network_proxy_config_from_profile_network,
    parse_absolute_path_for_platform,
    parse_relative_subpath,
    parse_special_path,
    reject_unknown_builtin_permission_profile,
    resolve_permission_profile,
    unbounded_unreadable_globstar_paths,
    unsupported_read_write_glob_paths,
    validate_glob_scan_max_depth,
)
from pycodex.network_proxy import NetworkMode, NetworkProxyConfig
from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxKind,
    FileSystemSandboxEntry,
    FileSystemSpecialPath,
    NetworkSandboxPolicy,
    PermissionProfile,
    project_roots_glob_pattern,
    WindowsSandboxLevel,
)


class CoreConfigPermissionsTests(unittest.TestCase):
    def test_builtin_permission_profile_names_and_selection(self) -> None:
        # Rust source: codex-rs/core/src/config/permissions.rs
        # Rust functions: is_builtin_permission_profile_name, reject_unknown_builtin_permission_profile.
        self.assertEqual(BUILT_IN_READ_ONLY_PROFILE, ":read-only")
        self.assertEqual(BUILT_IN_WORKSPACE_PROFILE, ":workspace")
        self.assertEqual(BUILT_IN_DANGER_FULL_ACCESS_PROFILE, ":danger-full-access")

        self.assertTrue(is_builtin_permission_profile_name(":read-only"))
        self.assertTrue(is_builtin_permission_profile_name(":workspace"))
        self.assertTrue(is_builtin_permission_profile_name(":danger-full-access"))
        self.assertFalse(is_builtin_permission_profile_name("workspace"))

        reject_unknown_builtin_permission_profile("workspace")
        with self.assertRaisesRegex(
            ValueError,
            "default_permissions refers to unknown built-in profile `:unknown`",
        ):
            reject_unknown_builtin_permission_profile(":unknown")

    def test_default_builtin_permission_profile_name_matches_trust_rules(self) -> None:
        # Rust source: codex-rs/core/src/config/permissions.rs
        # Rust function: default_builtin_permission_profile_name.
        self.assertEqual(
            default_builtin_permission_profile_name(
                ProjectTrust(trusted=True),
                WindowsSandboxLevel.DISABLED,
            ),
            ":read-only" if sys.platform == "win32" else ":workspace",
        )
        self.assertEqual(
            default_builtin_permission_profile_name(
                ProjectTrust(untrusted=True),
                WindowsSandboxLevel.RESTRICTED_TOKEN,
            ),
            ":workspace",
        )
        self.assertEqual(
            default_builtin_permission_profile_name(
                ProjectTrust(),
                WindowsSandboxLevel.RESTRICTED_TOKEN,
            ),
            ":read-only",
        )

    def test_builtin_permission_profile_runtime_policies(self) -> None:
        # Rust source: codex-rs/core/src/config/permissions.rs
        # Rust function: builtin_permission_profile.
        self.assertEqual(builtin_permission_profile(":read-only"), PermissionProfile.read_only())
        self.assertEqual(builtin_permission_profile(":danger-full-access"), PermissionProfile.disabled())
        self.assertIsNone(builtin_permission_profile("workspace"))

        workspace = builtin_permission_profile(":workspace")
        self.assertIsNotNone(workspace)
        filesystem, network = workspace.to_runtime_permissions()
        self.assertEqual(filesystem.kind, FileSystemSandboxKind.RESTRICTED)
        self.assertEqual(network, NetworkSandboxPolicy.RESTRICTED)
        self.assertTrue(
            any(entry.access is FileSystemAccessMode.WRITE for entry in filesystem.entries),
            "workspace built-in should include writable project-root/tmp entries",
        )

        network_workspace = builtin_permission_profile(
            ":workspace",
            SandboxWorkspaceWrite(network_access=True, exclude_slash_tmp=True, exclude_tmpdir_env_var=True),
        )
        filesystem, network = network_workspace.to_runtime_permissions()
        self.assertEqual(network, NetworkSandboxPolicy.ENABLED)
        self.assertFalse(
            any(
                entry.path.type == "special"
                and entry.path.value is not None
                and entry.path.value.kind in {"tmpdir", "slash_tmp"}
                and entry.access is FileSystemAccessMode.WRITE
                for entry in filesystem.entries
            )
        )

    def test_compile_permission_profile_selection_builtin_fast_path(self) -> None:
        # Rust source: codex-rs/core/src/config/permissions.rs
        # Rust function: compile_permission_profile_selection.
        read_only = compile_permission_profile_selection(None, ":read-only")
        self.assertEqual(read_only, PermissionProfile.read_only().to_runtime_permissions())

        with self.assertRaisesRegex(ValueError, "default_permissions requires a `\\[permissions\\]` table"):
            compile_permission_profile_selection(None, "custom")
        with self.assertRaisesRegex(ValueError, "unknown built-in profile `:custom`"):
            compile_permission_profile_selection(None, ":custom")

    def test_permissions_profiles_resolve_extends_parent_first_with_child_overrides(self) -> None:
        # Rust test: permissions_profiles_resolve_extends_parent_first_with_child_overrides.
        permissions = {
            "base": {
                "description": "Base profile",
                "filesystem": {
                    "glob_scan_max_depth": 1,
                    "/tmp/base": "read",
                    "/tmp/shared": "read",
                    ":workspace_roots": {"**/*.env": "deny", "docs": "read"},
                },
                "network": {
                    "enabled": True,
                    "domains": {
                        "base.example.com": "allow",
                        "SHARED.EXAMPLE.COM.": "deny",
                    },
                    "unix_sockets": {"/tmp/base.sock": "allow"},
                },
            },
            "child": {
                "extends": "base",
                "filesystem": {
                    "glob_scan_max_depth": 3,
                    "/tmp/shared": "write",
                    ":workspace_roots": {"docs": "write", "src": "read"},
                },
                "network": {
                    "enabled": False,
                    "allow_local_binding": True,
                    "domains": {
                        "child.example.com": "allow",
                        "shared.example.com": "allow",
                    },
                    "unix_sockets": {"/tmp/child.sock": "allow"},
                },
            },
        }

        resolved, inherited = resolve_permission_profile(permissions, "child")

        self.assertEqual(inherited, ("base",))
        self.assertEqual(resolved["extends"], "base")
        self.assertEqual(
            resolved["filesystem"],
            {
                "glob_scan_max_depth": 3,
                "entries": {
                    "/tmp/base": "read",
                    "/tmp/shared": "write",
                    ":workspace_roots": {
                        "**/*.env": "deny",
                        "docs": "write",
                        "src": "read",
                    },
                },
            },
        )
        self.assertEqual(
            resolved["network"]["domains"],
            {
                "base.example.com": "allow",
                "SHARED.EXAMPLE.COM.": "deny",
                "child.example.com": "allow",
                "shared.example.com": "allow",
            },
        )

    def test_permissions_profiles_reject_bad_extends(self) -> None:
        # Rust tests: permissions_profiles_reject_undefined_extends_parent,
        # permissions_profiles_reject_unsupported_builtin_extends_parent,
        # permissions_profiles_reject_extends_cycles.
        with self.assertRaisesRegex(
            ValueError,
            "permissions profile `child` extends undefined profile `base`",
        ):
            resolve_permission_profile({"child": {"extends": "base"}}, "child")
        with self.assertRaisesRegex(
            ValueError,
            "permissions profile `child` cannot extend unsupported built-in profile `:danger-full-access`",
        ):
            resolve_permission_profile({"child": {"extends": ":danger-full-access"}}, "child")
        with self.assertRaisesRegex(
            ValueError,
            "permissions profile inheritance cycle detected: alpha -> beta -> alpha",
        ):
            resolve_permission_profile(
                {"alpha": {"extends": "beta"}, "beta": {"extends": "alpha"}},
                "alpha",
            )

    def test_compile_permission_profile_custom_runtime_policies(self) -> None:
        # Rust source: permissions.rs::compile_permission_profile and compile_network_sandbox_policy.
        cwd = Path("C:/workspace") if sys.platform == "win32" else Path("/workspace")
        permissions = {
            "workspace": {
                "extends": ":workspace",
                "filesystem": {
                    "glob_scan_max_depth": 2,
                    ":workspace_roots": {"docs/**": "read", "**/*.env": "deny"},
                },
                "network": {"enabled": False},
            }
        }
        warnings: list[str] = []

        filesystem, network = compile_permission_profile(permissions, "workspace", cwd, warnings)

        self.assertEqual(network, NetworkSandboxPolicy.RESTRICTED)
        self.assertEqual(filesystem.glob_scan_max_depth, 2)
        self.assertTrue(
            any(
                entry.path == FileSystemPath.special(FileSystemSpecialPath.project_roots())
                and entry.access is FileSystemAccessMode.WRITE
                for entry in filesystem.entries
            ),
            "extending :workspace should preserve built-in workspace write base entries",
        )
        self.assertIn(
            FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.project_roots(Path("docs"))),
                FileSystemAccessMode.READ,
            ),
            filesystem.entries,
        )
        self.assertIn(
            FileSystemSandboxEntry(
                FileSystemPath.glob_pattern(project_roots_glob_pattern("**/*.env")),
                FileSystemAccessMode.DENY,
            ),
            filesystem.entries,
        )
        self.assertFalse(
            any("Filesystem deny-read glob `:workspace_roots/**/*.env`" in warning for warning in warnings),
            "configured glob_scan_max_depth should suppress the unbounded deny-read globstar warning",
        )

        self.assertEqual(
            compile_permission_profile_selection(permissions, "workspace", policy_cwd=cwd)[1],
            NetworkSandboxPolicy.RESTRICTED,
        )
        self.assertEqual(
            compile_network_sandbox_policy(None, NetworkSandboxPolicy.ENABLED),
            NetworkSandboxPolicy.ENABLED,
        )
        self.assertEqual(
            compile_network_sandbox_policy({"enabled": True}, NetworkSandboxPolicy.RESTRICTED),
            NetworkSandboxPolicy.ENABLED,
        )

    def test_compile_permission_profile_warns_when_filesystem_entries_missing(self) -> None:
        # Rust source: permissions.rs::missing_filesystem_entries_warning through compile_permission_profile.
        warnings: list[str] = []
        filesystem, network = compile_permission_profile(
            {"empty": {"filesystem": {}}},
            "empty",
            Path("C:/workspace") if sys.platform == "win32" else Path("/workspace"),
            warnings,
        )

        self.assertEqual(filesystem.entries, ())
        self.assertEqual(network, NetworkSandboxPolicy.RESTRICTED)
        self.assertEqual(
            warnings,
            [
                "Permissions profile `empty` does not define any recognized filesystem entries for this version of Codex. Filesystem access will remain restricted. Upgrade Codex if this profile expects filesystem permissions."
            ],
        )

    def test_compile_permission_profile_workspace_roots(self) -> None:
        # Rust test: compile_permission_profile_workspace_roots_resolves_enabled_entries.
        cwd = Path("C:/workspace") if sys.platform == "win32" else Path("/workspace")
        self.assertEqual(
            compile_permission_profile_workspace_roots(None, ":workspace", cwd),
            (),
        )
        self.assertEqual(
            compile_workspace_roots({"backend": True, "disabled": False}, cwd),
            (cwd / "backend",),
        )
        self.assertEqual(
            compile_permission_profile_workspace_roots(
                {"workspace": {"workspace_roots": {"entries": {"backend": True, "disabled": False}}}},
                "workspace",
                cwd,
            ),
            (cwd / "backend",),
        )
        with self.assertRaisesRegex(ValueError, "default_permissions requires a `\\[permissions\\]` table"):
            compile_permission_profile_workspace_roots(None, "workspace", cwd)

    def test_profile_network_proxy_config_keeps_proxy_disabled(self) -> None:
        # Rust tests: profile_network_proxy_config_keeps_proxy_disabled_for_bare_network_access,
        # profile_network_proxy_config_keeps_proxy_disabled_for_proxy_policy.
        bare = network_proxy_config_from_profile_network({"enabled": True})
        self.assertFalse(bare.network.enabled)

        config = network_proxy_config_from_profile_network(
            {
                "enabled": True,
                "proxy_url": "http://127.0.0.1:43128",
                "enable_socks5": False,
                "domains": {"openai.com": "allow"},
            }
        )
        self.assertFalse(config.network.enabled)
        self.assertEqual(config.network.proxy_url, "http://127.0.0.1:43128")
        self.assertFalse(config.network.enable_socks5)
        self.assertEqual(config.network.allowed_domains(), ["openai.com"])
        self.assertIsNone(config.network.denied_domains())

    def test_network_proxy_feature_config_overlay_preserves_enabled(self) -> None:
        # Rust source: permissions.rs::apply_network_proxy_feature_config.
        config = NetworkProxyConfig()

        apply_network_proxy_feature_config(
            config,
            {
                "enabled": True,
                "mode": "full",
                "allow_upstream_proxy": True,
                "dangerously_allow_non_loopback_proxy": True,
                "dangerously_allow_all_unix_sockets": True,
                "domains": {"openai.com": "allow", "blocked.example.com": "deny"},
                "unix_sockets": {"/tmp/base.sock": "allow", "/tmp/ignored.sock": "none"},
                "allow_local_binding": True,
                "enable_socks5": True,
                "socks_url": "http://127.0.0.1:19090",
                "enable_socks5_udp": True,
            },
        )

        self.assertTrue(config.network.enabled)
        self.assertEqual(config.network.mode, NetworkMode.FULL)
        self.assertTrue(config.network.allow_upstream_proxy)
        self.assertTrue(config.network.dangerously_allow_non_loopback_proxy)
        self.assertTrue(config.network.dangerously_allow_all_unix_sockets)
        self.assertEqual(config.network.allowed_domains(), ["openai.com"])
        self.assertEqual(config.network.denied_domains(), ["blocked.example.com"])
        self.assertEqual(config.network.allow_unix_sockets, ["/tmp/base.sock"])
        self.assertTrue(config.network.allow_local_binding)
        self.assertTrue(config.network.enable_socks5)
        self.assertEqual(config.network.socks_url, "http://127.0.0.1:19090")
        self.assertTrue(config.network.enable_socks5_udp)

    def test_readable_roots_required_for_codex_runtime(self) -> None:
        # Rust source: codex-rs/core/src/config/permissions.rs
        # Rust test: restricted_read_implicitly_allows_helper_executables.
        codex_home = Path("C:/tmp/.codex") if sys.platform == "win32" else Path("/tmp/.codex")
        zsh_path = codex_home.parent / "runtime" / "zsh"
        wrapper = codex_home / "tmp" / "arg0" / "codex-arg0-session" / "codex-execve-wrapper"
        outside_wrapper = codex_home.parent / "bin" / "codex-execve-wrapper"

        self.assertEqual(
            get_readable_roots_required_for_codex_runtime(codex_home, zsh_path, wrapper),
            (zsh_path, wrapper.parent),
        )
        self.assertEqual(
            get_readable_roots_required_for_codex_runtime(codex_home, None, outside_wrapper),
            (outside_wrapper,),
        )

    def test_windows_verbatim_paths_and_glob_detection(self) -> None:
        # Rust tests: normalize_absolute_path_for_platform_simplifies_windows_verbatim_paths,
        # windows_verbatim_path_prefix_does_not_count_as_glob_syntax.
        self.assertEqual(
            str(normalize_absolute_path_for_platform(r"\\?\D:\c\x\worktrees\2508\swift-base", True)),
            str(Path(r"D:\c\x\worktrees\2508\swift-base")),
        )
        self.assertFalse(
            contains_glob_chars_for_platform(
                r"\\?\D:\c\x\worktrees\2508\swift-base",
                True,
            )
        )
        self.assertTrue(
            contains_glob_chars_for_platform(
                r"\\?\D:\c\x\worktrees\2508\**\*.env",
                True,
            )
        )

    def test_glob_scan_depth_and_read_write_glob_path_helpers(self) -> None:
        # Rust tests: glob_scan_max_depth_must_be_positive,
        # read_write_trailing_glob_suffix_compiles_as_subpath,
        # read_write_glob_patterns_still_reject_non_subpath_globs.
        with self.assertRaisesRegex(ValueError, "glob_scan_max_depth must be at least 1"):
            validate_glob_scan_max_depth(0)
        self.assertEqual(validate_glob_scan_max_depth(2), 2)
        self.assertIsNone(validate_glob_scan_max_depth(None))

        self.assertEqual(
            compile_read_write_glob_path("docs/**", FileSystemAccessMode.READ),
            "docs",
        )
        with self.assertRaisesRegex(
            ValueError,
            "filesystem glob path `src/\\*\\*/\\*.rs` only supports `deny` access",
        ):
            compile_read_write_glob_path("src/**/*.rs", FileSystemAccessMode.READ)

    def test_filesystem_glob_warning_helper_lists(self) -> None:
        # Rust tests: read_write_glob_warnings_skip_supported_deny_read_globs_and_trailing_subpaths,
        # unreadable_globstar_warning_is_suppressed_when_scan_depth_is_configured.
        filesystem = {
            "glob_scan_max_depth": None,
            "entries": {
                "/tmp/**/*.log": "read",
                "/tmp/cache/**": "write",
                ":workspace_roots": {
                    "**/*.env": "deny",
                    "docs/**": "read",
                    "src/**/*.rs": "write",
                },
            },
        }
        self.assertEqual(
            unsupported_read_write_glob_paths(filesystem),
            ("/tmp/**/*.log", ":workspace_roots/src/**/*.rs"),
        )
        self.assertEqual(
            unbounded_unreadable_globstar_paths(
                {
                    "glob_scan_max_depth": None,
                    "entries": {":workspace_roots": {"**/*.env": "deny", "*.pem": "deny"}},
                }
            ),
            (":workspace_roots/**/*.env",),
        )
        self.assertEqual(
            unbounded_unreadable_globstar_paths(
                {
                    "glob_scan_max_depth": 2,
                    "entries": {":workspace_roots": {"**/*.env": "deny", "*.pem": "deny"}},
                }
            ),
            (),
        )

    def test_parse_relative_subpath_rejects_non_descendants(self) -> None:
        # Rust source: codex-rs/core/src/config/permissions.rs::parse_relative_subpath.
        self.assertEqual(parse_relative_subpath("docs/reference"), Path("docs/reference"))
        for subpath in ("", ".", "../secrets", "docs/../secrets"):
            with self.subTest(subpath=subpath):
                with self.assertRaisesRegex(ValueError, "must be a descendant path"):
                    parse_relative_subpath(subpath)

    def test_special_path_and_absolute_path_helpers(self) -> None:
        # Rust source: permissions.rs::parse_special_path,
        # compile_filesystem_path, parse_absolute_path_for_platform.
        self.assertEqual(parse_special_path(":root"), FileSystemSpecialPath.root())
        self.assertEqual(parse_special_path(":minimal"), FileSystemSpecialPath.minimal())
        self.assertEqual(parse_special_path(":workspace_roots"), FileSystemSpecialPath.project_roots())
        self.assertEqual(parse_special_path(":tmpdir"), FileSystemSpecialPath.tmpdir())
        self.assertEqual(parse_special_path(":future"), FileSystemSpecialPath.unknown(":future"))
        self.assertIsNone(parse_special_path("/tmp/work"))

        warnings: list[str] = []
        self.assertEqual(
            compile_filesystem_path(":workspace_roots", warnings),
            FileSystemPath.special(FileSystemSpecialPath.project_roots()),
        )
        self.assertEqual(
            compile_filesystem_path(":future", warnings),
            FileSystemPath.special(FileSystemSpecialPath.unknown(":future")),
        )
        self.assertEqual(
            warnings,
            [
                "Configured filesystem path `:future` is not recognized by this version of Codex "
                "and will be ignored. Upgrade Codex if this path is required."
            ],
        )

        with self.assertRaisesRegex(ValueError, "must be absolute"):
            parse_absolute_path_for_platform("relative/path", False)
        self.assertEqual(parse_absolute_path_for_platform("~/project", False), Path("~/project"))

    def test_scoped_filesystem_path_and_pattern_helpers(self) -> None:
        # Rust source: permissions.rs::compile_scoped_filesystem_path and
        # compile_scoped_filesystem_pattern.
        warnings: list[str] = []
        self.assertEqual(
            compile_scoped_filesystem_path(":workspace_roots", "docs", warnings),
            FileSystemPath.special(FileSystemSpecialPath.project_roots(Path("docs"))),
        )
        self.assertEqual(warnings, [])
        self.assertEqual(
            compile_scoped_filesystem_pattern(":workspace_roots", "**/*.env", FileSystemAccessMode.DENY),
            project_roots_glob_pattern("**/*.env"),
        )

        unknown_warnings: list[str] = []
        self.assertEqual(
            compile_scoped_filesystem_path(":future", "docs", unknown_warnings),
            FileSystemPath.special(FileSystemSpecialPath.unknown(":future", Path("docs"))),
        )
        self.assertEqual(
            unknown_warnings,
            [
                "Configured filesystem path `:future` with nested entry `docs` is not recognized by this version of Codex "
                "and will be ignored. Upgrade Codex if this path is required."
            ],
        )

        with self.assertRaisesRegex(ValueError, "does not support nested entries"):
            compile_scoped_filesystem_path(":tmpdir", "docs")
        with self.assertRaisesRegex(ValueError, "only supports `deny` access"):
            compile_scoped_filesystem_pattern(":workspace_roots", "*.rs", FileSystemAccessMode.READ)

    def test_filesystem_permission_compilation_for_access_and_scoped_entries(self) -> None:
        # Rust source: permissions.rs::compile_filesystem_permission and compile_filesystem_access_path.
        base = Path("C:/base") if sys.platform == "win32" else Path("/base")
        entries = compile_filesystem_permission(
            str(base),
            {"docs/**": "read", "**/*.env": "deny"},
        )
        self.assertEqual(
            entries,
            (
                FileSystemSandboxEntry(
                    FileSystemPath.explicit_path(base / "docs"),
                    FileSystemAccessMode.READ,
                ),
                FileSystemSandboxEntry(
                    FileSystemPath.glob_pattern(str(base / "**/*.env")),
                    FileSystemAccessMode.DENY,
                ),
            ),
        )

        self.assertEqual(
            compile_filesystem_access_path(str(base / "**/*.env"), FileSystemAccessMode.DENY),
            FileSystemPath.glob_pattern(str(base / "**/*.env")),
        )


if __name__ == "__main__":
    unittest.main()
