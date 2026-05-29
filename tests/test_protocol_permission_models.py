import unittest
from pathlib import Path

from pycodex.protocol import (
    BUILT_IN_PERMISSION_PROFILE_READ_ONLY,
    ActivePermissionProfile,
    AdditionalPermissionProfile,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemPermissions,
    FileSystemSandboxEntry,
    FileSystemSandboxKind,
    FileSystemSandboxPolicy,
    FileSystemSemanticSignature,
    FileSystemSpecialPath,
    ManagedFileSystemPermissions,
    NetworkPermissions,
    NetworkSandboxPolicy,
    PermissionProfile,
    PROTECTED_METADATA_PATH_NAMES,
    ReadDenyMatcher,
    SandboxEnforcement,
    SandboxPermissions,
    SandboxPolicy,
    WritableRoot,
    forbidden_agent_metadata_write,
    is_protected_metadata_directory_name,
    is_protected_metadata_name,
    project_roots_glob_pattern,
)


class ProtocolPermissionModelTests(unittest.TestCase):
    @staticmethod
    def _entry(path: Path | str, access: FileSystemAccessMode) -> FileSystemSandboxEntry:
        return FileSystemSandboxEntry(FileSystemPath.explicit_path(path), access)

    @staticmethod
    def _glob_entry(pattern: str) -> FileSystemSandboxEntry:
        return FileSystemSandboxEntry(FileSystemPath.glob_pattern(pattern), FileSystemAccessMode.DENY)

    @staticmethod
    def _workspace_path(name: str) -> Path:
        return Path(__file__).resolve().parents[1] / "__virtual_tests__" / name

    def test_sandbox_permissions_helpers_match_upstream(self):
        self.assertIs(SandboxPermissions.default(), SandboxPermissions.USE_DEFAULT)
        self.assertFalse(SandboxPermissions.USE_DEFAULT.requests_sandbox_override())
        self.assertTrue(SandboxPermissions.REQUIRE_ESCALATED.requires_escalated_permissions())
        self.assertTrue(SandboxPermissions.REQUIRE_ESCALATED.requests_sandbox_override())
        self.assertFalse(SandboxPermissions.REQUIRE_ESCALATED.uses_additional_permissions())
        self.assertTrue(SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS.uses_additional_permissions())

    def test_network_and_filesystem_access_helpers(self):
        self.assertIs(NetworkSandboxPolicy.default(), NetworkSandboxPolicy.RESTRICTED)
        self.assertFalse(NetworkSandboxPolicy.RESTRICTED.is_enabled())
        self.assertTrue(NetworkSandboxPolicy.ENABLED.is_enabled())
        with self.assertRaisesRegex(TypeError, "network must be a string"):
            NetworkSandboxPolicy.parse(123)
        self.assertIs(FileSystemAccessMode.parse("none"), FileSystemAccessMode.DENY)
        with self.assertRaisesRegex(TypeError, "access must be a string"):
            FileSystemAccessMode.parse(123)
        self.assertTrue(FileSystemAccessMode.READ.can_read())
        self.assertFalse(FileSystemAccessMode.READ.can_write())
        self.assertTrue(FileSystemAccessMode.WRITE.can_write())
        self.assertFalse(FileSystemAccessMode.DENY.can_read())
        self.assertGreater(FileSystemAccessMode.DENY.conflict_precedence(), FileSystemAccessMode.WRITE.conflict_precedence())
        self.assertGreater(FileSystemAccessMode.WRITE.conflict_precedence(), FileSystemAccessMode.READ.conflict_precedence())

    def test_file_system_permissions_legacy_read_write_roots(self):
        permissions = FileSystemPermissions.from_read_write_roots([Path("/read")], [Path("/write")])

        self.assertFalse(permissions.is_empty())
        self.assertEqual(
            permissions.explicit_path_entries(),
            ((Path("/read"), FileSystemAccessMode.READ), (Path("/write"), FileSystemAccessMode.WRITE)),
        )
        self.assertEqual(permissions.legacy_read_write_roots(), ((Path("/read"),), (Path("/write"),)))
        self.assertEqual(permissions.to_mapping(), {"read": [str(Path("/read"))], "write": [str(Path("/write"))]})
        self.assertEqual(FileSystemPermissions.from_mapping(permissions.to_mapping()), permissions)

    def test_file_system_permissions_reject_non_legacy_shapes(self):
        permissions = FileSystemPermissions(
            (
                FileSystemSandboxEntry(
                    FileSystemPath.glob_pattern("/tmp/**/*.env"),
                    FileSystemAccessMode.DENY,
                ),
            )
        )

        self.assertIsNone(permissions.legacy_read_write_roots())

    def test_permission_overlay_empty_helpers(self):
        self.assertTrue(NetworkPermissions().is_empty())
        self.assertFalse(NetworkPermissions(enabled=True).is_empty())
        self.assertEqual(NetworkPermissions.from_mapping({"enabled": True}), NetworkPermissions(enabled=True))
        with self.assertRaisesRegex(TypeError, "enabled must be a bool"):
            NetworkPermissions.from_mapping({"enabled": "true"})
        with self.assertRaisesRegex(TypeError, "enabled must be a bool"):
            NetworkPermissions(enabled="true")
        self.assertTrue(AdditionalPermissionProfile().is_empty())
        self.assertFalse(AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)).is_empty())
        with self.assertRaisesRegex(TypeError, "network must be NetworkPermissions"):
            AdditionalPermissionProfile(network={"enabled": True})
        with self.assertRaisesRegex(TypeError, "file_system must be FileSystemPermissions"):
            AdditionalPermissionProfile(file_system={"read": ["/read"]})

    def test_file_system_sandbox_policy_workspace_write_entries(self):
        policy = FileSystemSandboxPolicy.workspace_write([Path("/extra")])

        expected = (
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), FileSystemAccessMode.READ),
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots()), FileSystemAccessMode.WRITE),
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.slash_tmp()), FileSystemAccessMode.WRITE),
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.tmpdir()), FileSystemAccessMode.WRITE),
            FileSystemSandboxEntry(FileSystemPath.explicit_path(Path("/extra")), FileSystemAccessMode.WRITE),
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots(Path(".git"))), FileSystemAccessMode.READ),
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots(Path(".agents"))), FileSystemAccessMode.READ),
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots(Path(".codex"))), FileSystemAccessMode.READ),
        )
        self.assertEqual(policy.kind, FileSystemSandboxKind.RESTRICTED)
        self.assertEqual(policy.entries, expected)
        self.assertFalse(policy.has_denied_read_restrictions())

    def test_file_system_sandbox_policy_workspace_write_exclusion_knobs(self):
        policy = FileSystemSandboxPolicy.workspace_write(exclude_tmpdir_env_var=True, exclude_slash_tmp=True)

        self.assertNotIn(
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.slash_tmp()), FileSystemAccessMode.WRITE),
            policy.entries,
        )
        self.assertNotIn(
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.tmpdir()), FileSystemAccessMode.WRITE),
            policy.entries,
        )

        with self.assertRaisesRegex(TypeError, "writable_roots must be a list or tuple"):
            FileSystemSandboxPolicy.workspace_write(writable_roots="/tmp")

        with self.assertRaisesRegex(TypeError, "writable_roots entries must be strings or Path"):
            FileSystemSandboxPolicy.workspace_write(writable_roots=(123,))

        with self.assertRaisesRegex(TypeError, "exclude_tmpdir_env_var must be a bool"):
            FileSystemSandboxPolicy.workspace_write(exclude_tmpdir_env_var="false")

        with self.assertRaisesRegex(TypeError, "exclude_slash_tmp must be a bool"):
            FileSystemSandboxPolicy.workspace_write(exclude_slash_tmp="false")

    def test_protected_metadata_helpers_match_upstream(self):
        self.assertEqual(PROTECTED_METADATA_PATH_NAMES, (".git", ".agents", ".codex"))
        self.assertTrue(is_protected_metadata_name(".git"))
        self.assertTrue(is_protected_metadata_directory_name(".agents"))
        self.assertTrue(is_protected_metadata_directory_name(".codex"))
        self.assertFalse(is_protected_metadata_directory_name(".git"))
        self.assertEqual(project_roots_glob_pattern(Path("**/*.env")), "codex-project-roots://**/*.env")

    def test_filesystem_path_mapping_roundtrips_and_accepts_legacy_alias(self):
        self.assertEqual(
            FileSystemSpecialPath.from_mapping({"kind": "current_working_directory"}),
            FileSystemSpecialPath.project_roots(),
        )
        with self.assertRaisesRegex(TypeError, "kind must be a string"):
            FileSystemSpecialPath.from_mapping({"kind": 123})
        with self.assertRaisesRegex(TypeError, "subpath must be a string"):
            FileSystemSpecialPath.from_mapping({"kind": "project_roots", "subpath": 123})
        with self.assertRaisesRegex(TypeError, "path must be a string"):
            FileSystemSpecialPath.from_mapping({"kind": "unknown", "path": 123})
        with self.assertRaisesRegex(TypeError, "subpath must be a string"):
            FileSystemSpecialPath.from_mapping({"kind": ":future_special_path", "subpath": 123})
        self.assertEqual(
            FileSystemSpecialPath.project_roots(Path(".codex")).to_mapping(),
            {"kind": "project_roots", "subpath": ".codex"},
        )
        self.assertEqual(
            FileSystemSpecialPath("project_roots", subpath=".codex"),
            FileSystemSpecialPath.project_roots(Path(".codex")),
        )
        with self.assertRaisesRegex(ValueError, "unknown filesystem special path kind"):
            FileSystemSpecialPath("future")
        with self.assertRaisesRegex(ValueError, "root special path cannot include subpath"):
            FileSystemSpecialPath("root", subpath=Path(".git"))
        with self.assertRaisesRegex(ValueError, "tmpdir special path cannot include path"):
            FileSystemSpecialPath("tmpdir", path=":future")
        with self.assertRaisesRegex(ValueError, "project_roots special path cannot include path"):
            FileSystemSpecialPath("project_roots", path=":future")
        with self.assertRaisesRegex(TypeError, "unknown special path requires path"):
            FileSystemSpecialPath("unknown")
        self.assertEqual(
            FileSystemPath.from_mapping({"type": "path", "path": "/tmp/project"}).to_mapping(),
            {"type": "path", "path": str(Path("/tmp/project"))},
        )
        with self.assertRaisesRegex(TypeError, "type must be a string"):
            FileSystemPath.from_mapping({"type": 123, "path": "/tmp/project"})
        with self.assertRaisesRegex(TypeError, "path must be a string"):
            FileSystemPath.from_mapping({"type": "path", "path": 123})
        with self.assertRaisesRegex(TypeError, "pattern must be a string"):
            FileSystemPath.from_mapping({"type": "glob_pattern", "pattern": 123})
        self.assertEqual(FileSystemPath(type="path", path="/tmp/project"), FileSystemPath.explicit_path("/tmp/project"))
        with self.assertRaisesRegex(ValueError, "unknown filesystem path type"):
            FileSystemPath(type="future")
        with self.assertRaisesRegex(TypeError, "path filesystem path requires path"):
            FileSystemPath(type="path")
        with self.assertRaisesRegex(ValueError, "path filesystem path cannot include pattern"):
            FileSystemPath(type="path", path=Path("/tmp/project"), pattern="*.env")
        with self.assertRaisesRegex(TypeError, "glob_pattern filesystem path requires pattern"):
            FileSystemPath(type="glob_pattern", pattern=123)
        with self.assertRaisesRegex(ValueError, "glob_pattern filesystem path cannot include path"):
            FileSystemPath(type="glob_pattern", path=Path("/tmp/project"), pattern="*.env")
        with self.assertRaisesRegex(TypeError, "special filesystem path requires FileSystemSpecialPath"):
            FileSystemPath(type="special", value="root")
        with self.assertRaisesRegex(ValueError, "special filesystem path cannot include pattern"):
            FileSystemPath(type="special", pattern="*.env", value=FileSystemSpecialPath.root())
        self.assertEqual(
            FileSystemSandboxEntry.from_mapping(
                {
                    "path": {"type": "special", "value": {"kind": "root"}},
                    "access": "none",
                }
            ),
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), FileSystemAccessMode.DENY),
        )
        with self.assertRaisesRegex(TypeError, "access must be a string"):
            FileSystemSandboxEntry.from_mapping(
                {
                    "path": {"type": "special", "value": {"kind": "root"}},
                    "access": 123,
                }
            )
        with self.assertRaisesRegex(TypeError, "path must be FileSystemPath"):
            FileSystemSandboxEntry({"type": "special"}, FileSystemAccessMode.READ)
        with self.assertRaisesRegex(TypeError, "access must be FileSystemAccessMode"):
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), "read")

    def test_filesystem_permissions_mapping_uses_canonical_entries_shape(self):
        entry = self._entry(Path("/tmp/allowed"), FileSystemAccessMode.READ)
        permissions = FileSystemPermissions((entry,), glob_scan_max_depth=2)

        self.assertEqual(
            permissions.to_mapping(),
            {"entries": [entry.to_mapping()], "glob_scan_max_depth": 2},
        )
        self.assertEqual(FileSystemPermissions.from_mapping(permissions.to_mapping()), permissions)
        self.assertEqual(
            FileSystemPermissions.from_mapping({"read": ["/read"], "write": ["/write"]}),
            FileSystemPermissions.from_read_write_roots((Path("/read"),), (Path("/write"),)),
        )
        with self.assertRaisesRegex(ValueError, "unknown field"):
            FileSystemPermissions.from_mapping({"read": ["/read"], "unexpected": True})
        with self.assertRaisesRegex(ValueError, "unknown field"):
            FileSystemPermissions.from_mapping({"entries": [], "read": ["/read"]})
        with self.assertRaisesRegex(ValueError, "glob_scan_max_depth"):
            FileSystemPermissions.from_mapping({"entries": [], "glob_scan_max_depth": 0})
        with self.assertRaisesRegex(TypeError, "glob_scan_max_depth"):
            FileSystemPermissions.from_mapping({"entries": [], "glob_scan_max_depth": "2"})
        with self.assertRaisesRegex(ValueError, "glob_scan_max_depth"):
            FileSystemPermissions(glob_scan_max_depth=0)
        with self.assertRaisesRegex(TypeError, "glob_scan_max_depth"):
            FileSystemPermissions(glob_scan_max_depth="2")
        with self.assertRaisesRegex(TypeError, "entries must contain FileSystemSandboxEntry"):
            FileSystemPermissions(entries=("not-an-entry",))

    def test_sandbox_and_filesystem_policy_mapping_roundtrips(self):
        sandbox = SandboxPolicy.workspace_write(
            [Path("/extra")],
            network_access=True,
            exclude_tmpdir_env_var=True,
            exclude_slash_tmp=True,
        )
        self.assertEqual(SandboxPolicy.from_mapping(sandbox.to_mapping()), sandbox)
        self.assertEqual(
            SandboxPolicy.external_sandbox(NetworkSandboxPolicy.ENABLED).to_mapping(),
            {"type": "external-sandbox", "network_access": "enabled"},
        )
        with self.assertRaisesRegex(TypeError, "type must be a string"):
            SandboxPolicy.from_mapping({"type": 123})
        with self.assertRaisesRegex(ValueError, "unknown field"):
            SandboxPolicy.from_mapping({"type": "danger-full-access", "network_access": True})
        with self.assertRaisesRegex(ValueError, "unknown field"):
            SandboxPolicy.from_mapping({"type": "read-only", "writable_roots": []})
        with self.assertRaisesRegex(TypeError, "network_access must be a bool"):
            SandboxPolicy.from_mapping({"type": "read-only", "network_access": "true"})
        with self.assertRaisesRegex(ValueError, "unknown field"):
            SandboxPolicy.from_mapping({"type": "external-sandbox", "writable_roots": []})
        with self.assertRaisesRegex(TypeError, "network must be a string"):
            SandboxPolicy.from_mapping({"type": "external-sandbox", "network_access": 123})
        with self.assertRaisesRegex(ValueError, "unknown field"):
            SandboxPolicy.from_mapping({"type": "workspace-write", "unexpected": True})
        with self.assertRaisesRegex(TypeError, "writable_roots must be a list"):
            SandboxPolicy.from_mapping({"type": "workspace-write", "writable_roots": "/tmp"})
        with self.assertRaisesRegex(TypeError, "writable_roots entries must be strings"):
            SandboxPolicy.from_mapping({"type": "workspace-write", "writable_roots": [123]})
        with self.assertRaisesRegex(TypeError, "exclude_tmpdir_env_var must be a bool"):
            SandboxPolicy.from_mapping({"type": "workspace-write", "exclude_tmpdir_env_var": "false"})
        with self.assertRaisesRegex(TypeError, "exclude_slash_tmp must be a bool"):
            SandboxPolicy.from_mapping({"type": "workspace-write", "exclude_slash_tmp": "false"})

        policy = FileSystemSandboxPolicy.restricted(
            (
                FileSystemSandboxEntry(
                    FileSystemPath.glob_pattern("/tmp/private/**/*.txt"),
                    FileSystemAccessMode.DENY,
                ),
            )
        )
        self.assertEqual(
            FileSystemSandboxPolicy.from_mapping(policy.to_mapping()),
            policy,
        )
        self.assertEqual(
            FileSystemSandboxPolicy.from_mapping({"kind": "restricted", "glob_scan_max_depth": 0}),
            FileSystemSandboxPolicy(glob_scan_max_depth=0),
        )
        with self.assertRaisesRegex(TypeError, "kind must be a string"):
            FileSystemSandboxPolicy.from_mapping({"kind": 123})
        with self.assertRaisesRegex(TypeError, "glob_scan_max_depth must be an integer"):
            FileSystemSandboxPolicy.from_mapping({"kind": "restricted", "glob_scan_max_depth": "2"})
        with self.assertRaisesRegex(ValueError, "glob_scan_max_depth must be non-negative"):
            FileSystemSandboxPolicy(glob_scan_max_depth=-1)
        with self.assertRaisesRegex(TypeError, "kind must be FileSystemSandboxKind"):
            FileSystemSandboxPolicy(kind="restricted")
        with self.assertRaisesRegex(TypeError, "entries must contain FileSystemSandboxEntry"):
            FileSystemSandboxPolicy(entries=("not-an-entry",))
        with self.assertRaisesRegex(TypeError, "entries must be a list"):
            FileSystemSandboxPolicy.from_mapping({"kind": "restricted", "entries": "not-a-list"})

    def test_full_disk_write_detects_real_narrowing_entries(self):
        cwd = self._workspace_path("full-disk")
        root_path = Path(cwd.anchor) if cwd.anchor else Path("/")
        docs = cwd / "docs"

        full = FileSystemSandboxPolicy.restricted(
            (FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), FileSystemAccessMode.WRITE),)
        )
        self.assertTrue(FileSystemSandboxPolicy.unrestricted().has_full_disk_write_access())
        self.assertTrue(FileSystemSandboxPolicy.external_sandbox().has_full_disk_write_access())
        self.assertTrue(full.has_full_disk_read_access())
        self.assertTrue(full.has_full_disk_write_access())

        narrowed = FileSystemSandboxPolicy.restricted(
            (
                FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), FileSystemAccessMode.WRITE),
                self._entry(docs, FileSystemAccessMode.READ),
            )
        )
        self.assertFalse(narrowed.has_full_disk_write_access())
        self.assertEqual(narrowed.resolve_access_with_cwd(docs, cwd), FileSystemAccessMode.READ)

        shadowed = FileSystemSandboxPolicy.restricted(
            (
                FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), FileSystemAccessMode.WRITE),
                self._entry(docs, FileSystemAccessMode.READ),
                self._entry(docs, FileSystemAccessMode.WRITE),
            )
        )
        self.assertTrue(shadowed.has_full_disk_write_access())
        self.assertEqual(shadowed.resolve_access_with_cwd(docs, cwd), FileSystemAccessMode.WRITE)

        denied_root = FileSystemSandboxPolicy.restricted(
            (
                FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), FileSystemAccessMode.WRITE),
                FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), FileSystemAccessMode.DENY),
            )
        )
        self.assertFalse(denied_root.has_full_disk_write_access())
        self.assertEqual(denied_root.resolve_access_with_cwd(root_path, cwd), FileSystemAccessMode.DENY)

    def test_workspace_metadata_writes_are_directly_blocked_by_default(self):
        cwd = self._workspace_path("workspace-metadata")
        policy = FileSystemSandboxPolicy.workspace_write(exclude_tmpdir_env_var=True, exclude_slash_tmp=True)

        self.assertFalse(policy.can_write_path_with_cwd(Path(".git/config"), cwd))
        self.assertFalse(policy.can_write_path_with_cwd(Path(".agents/skills/example/SKILL.md"), cwd))
        self.assertFalse(policy.can_write_path_with_cwd(Path(".codex/config.toml"), cwd))
        self.assertEqual(forbidden_agent_metadata_write(Path(".git/config"), cwd, policy), ".git")

        explicit_git = FileSystemSandboxPolicy.restricted(
            (
                FileSystemSandboxEntry(
                    FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                    FileSystemAccessMode.WRITE,
                ),
                FileSystemSandboxEntry(
                    FileSystemPath.special(FileSystemSpecialPath.project_roots(Path(".git"))),
                    FileSystemAccessMode.WRITE,
                ),
            )
        )
        self.assertTrue(explicit_git.can_write_path_with_cwd(Path(".git/config"), cwd))
        self.assertIsNone(forbidden_agent_metadata_write(Path(".git/config"), cwd, explicit_git))

    def test_writable_roots_include_metadata_name_protections(self):
        cwd = self._workspace_path("writable-roots")
        policy = FileSystemSandboxPolicy.restricted((self._entry(cwd, FileSystemAccessMode.WRITE),))

        writable_roots = policy.get_writable_roots_with_cwd(cwd)
        self.assertEqual(len(writable_roots), 1)
        self.assertIsInstance(writable_roots[0], WritableRoot)
        self.assertEqual(writable_roots[0].root, cwd.resolve())
        self.assertEqual(writable_roots[0].protected_metadata_names, (".git", ".agents", ".codex"))
        self.assertFalse(writable_roots[0].is_path_writable(cwd / ".git" / "config"))
        self.assertFalse(writable_roots[0].is_path_writable(cwd / ".agents" / "skills" / "example" / "SKILL.md"))
        self.assertFalse(writable_roots[0].is_path_writable(cwd / ".codex" / "config.toml"))
        self.assertTrue(writable_roots[0].is_path_writable(cwd / "src" / "main.py"))

    def test_readable_unreadable_roots_resolve_with_cwd(self):
        cwd = self._workspace_path("readable-roots")
        docs = cwd / "docs"
        policy = FileSystemSandboxPolicy.restricted(
            (
                FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), FileSystemAccessMode.DENY),
                self._entry(docs, FileSystemAccessMode.READ),
            )
        )

        self.assertEqual(policy.resolve_access_with_cwd(docs, cwd), FileSystemAccessMode.READ)
        self.assertEqual(policy.get_readable_roots_with_cwd(cwd), (docs.resolve(),))
        self.assertEqual(policy.get_unreadable_roots_with_cwd(cwd), ())

    def test_read_deny_matcher_exact_roots_and_globs(self):
        cwd = self._workspace_path("read-deny")
        denied_dir = cwd / "denied"
        nested = denied_dir / "nested.txt"

        exact = FileSystemSandboxPolicy.restricted((self._entry(denied_dir, FileSystemAccessMode.DENY),))
        exact_matcher = ReadDenyMatcher.new(exact, cwd)
        self.assertIsNotNone(exact_matcher)
        assert exact_matcher is not None
        self.assertTrue(exact_matcher.is_read_denied(denied_dir))
        self.assertTrue(exact_matcher.is_read_denied(nested))
        self.assertFalse(exact_matcher.is_read_denied(cwd / "other.txt"))

        glob_policy = FileSystemSandboxPolicy.default()
        glob_policy = FileSystemSandboxPolicy.restricted(
            glob_policy.entries
            + (
                self._glob_entry(str(cwd / "private" / "secret?.txt")),
                self._glob_entry(str(cwd / "**" / "*.env")),
                self._glob_entry(str(cwd / "[")),
            )
        )
        glob_matcher = ReadDenyMatcher.new(glob_policy, cwd)
        self.assertIsNotNone(glob_matcher)
        assert glob_matcher is not None
        self.assertTrue(glob_matcher.is_read_denied(cwd / "private" / "secret1.txt"))
        self.assertFalse(glob_matcher.is_read_denied(cwd / "private" / "secret10.txt"))
        self.assertTrue(glob_matcher.is_read_denied(cwd / ".env"))
        self.assertTrue(glob_matcher.is_read_denied(cwd / "app" / ".env"))
        self.assertTrue(glob_matcher.is_read_denied(cwd / "["))
        self.assertFalse(glob_matcher.is_read_denied(cwd / "app" / "notes.txt"))

    def test_read_deny_matcher_resolves_project_root_globs(self):
        cwd = self._workspace_path("project-root-glob")
        policy = FileSystemSandboxPolicy.restricted(
            (
                FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), FileSystemAccessMode.READ),
                self._glob_entry(project_roots_glob_pattern(Path("**/*.env"))),
            )
        )
        matcher = ReadDenyMatcher.new(policy, cwd)
        self.assertIsNotNone(matcher)
        assert matcher is not None
        self.assertTrue(matcher.is_read_denied(cwd / ".env"))
        self.assertTrue(matcher.is_read_denied(cwd / "app" / ".env"))
        self.assertFalse(matcher.is_read_denied(cwd / "app" / "notes.txt"))

    def test_materialize_project_roots_with_workspace_roots_expands_symbolic_entries(self):
        first = self._workspace_path("first-root")
        second = self._workspace_path("second-root")
        literal = self._workspace_path("literal")
        policy = FileSystemSandboxPolicy.restricted(
            (
                FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots()), FileSystemAccessMode.WRITE),
                FileSystemSandboxEntry(
                    FileSystemPath.special(FileSystemSpecialPath.project_roots(Path(".git"))),
                    FileSystemAccessMode.READ,
                ),
                self._glob_entry(project_roots_glob_pattern(Path("**/*.env"))),
                self._entry(literal, FileSystemAccessMode.READ),
            )
        )

        actual = policy.materialize_project_roots_with_workspace_roots([first, second])

        self.assertEqual(
            actual,
            FileSystemSandboxPolicy.restricted(
                (
                    self._entry(first, FileSystemAccessMode.WRITE),
                    self._entry(second, FileSystemAccessMode.WRITE),
                    self._entry(first / ".git", FileSystemAccessMode.READ),
                    self._entry(second / ".git", FileSystemAccessMode.READ),
                    self._glob_entry(str(first / "**" / "*.env")),
                    self._glob_entry(str(second / "**" / "*.env")),
                    self._entry(literal, FileSystemAccessMode.READ),
                )
            ),
        )

    def test_materialize_project_roots_with_cwd_keeps_relative_cwd_symbolic(self):
        cwd = self._workspace_path("cwd-root")
        policy = FileSystemSandboxPolicy.restricted(
            (
                FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots()), FileSystemAccessMode.WRITE),
                FileSystemSandboxEntry(
                    FileSystemPath.special(FileSystemSpecialPath.project_roots(Path(".codex"))),
                    FileSystemAccessMode.READ,
                ),
                self._glob_entry(project_roots_glob_pattern(Path("**/*.env"))),
            )
        )

        self.assertEqual(
            policy.materialize_project_roots_with_cwd(cwd),
            FileSystemSandboxPolicy.restricted(
                (
                    self._entry(cwd, FileSystemAccessMode.WRITE),
                    self._entry(cwd / ".codex", FileSystemAccessMode.READ),
                    self._glob_entry(str(cwd / "**" / "*.env")),
                )
            ),
        )
        self.assertEqual(policy.materialize_project_roots_with_cwd(Path("relative-cwd")), policy)

    def test_with_materialized_project_roots_preserves_symbolic_entries(self):
        workspace_root = self._workspace_path("preserve-symbolic")
        policy = FileSystemSandboxPolicy.restricted(
            (
                FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots()), FileSystemAccessMode.WRITE),
                self._entry(workspace_root, FileSystemAccessMode.WRITE),
            )
        )

        actual = policy.with_materialized_project_roots_for_workspace_roots([workspace_root])

        self.assertEqual(
            actual.entries,
            (
                FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots()), FileSystemAccessMode.WRITE),
                self._entry(workspace_root, FileSystemAccessMode.WRITE),
            ),
        )

    def test_with_additional_roots_skips_existing_effective_access(self):
        cwd = self._workspace_path("additional-roots")
        extra = self._workspace_path("extra-root")
        read_policy = FileSystemSandboxPolicy.restricted(
            (FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots()), FileSystemAccessMode.READ),)
        )
        write_policy = FileSystemSandboxPolicy.restricted(
            (FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots()), FileSystemAccessMode.WRITE),)
        )

        self.assertEqual(read_policy.with_additional_readable_roots(cwd, [cwd, extra]).entries[-1], self._entry(extra, FileSystemAccessMode.READ))
        self.assertNotIn(self._entry(cwd, FileSystemAccessMode.READ), read_policy.with_additional_readable_roots(cwd, [cwd, extra]).entries)
        self.assertEqual(write_policy.with_additional_writable_roots(cwd, [cwd, extra]).entries[-1], self._entry(extra, FileSystemAccessMode.WRITE))
        self.assertNotIn(self._entry(cwd, FileSystemAccessMode.WRITE), write_policy.with_additional_writable_roots(cwd, [cwd, extra]).entries)

    def test_with_additional_legacy_workspace_writable_roots_adds_exact_root(self):
        cwd = self._workspace_path("legacy-root")
        policy = FileSystemSandboxPolicy.restricted(
            (FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots()), FileSystemAccessMode.WRITE),)
        )

        actual = policy.with_additional_legacy_workspace_writable_roots([cwd])
        again = actual.with_additional_legacy_workspace_writable_roots([cwd])

        explicit = self._entry(cwd, FileSystemAccessMode.WRITE)
        self.assertIn(explicit, actual.entries)
        self.assertEqual(sum(1 for entry in again.entries if entry == explicit), 1)
        self.assertEqual(FileSystemSandboxPolicy.unrestricted().with_additional_legacy_workspace_writable_roots([cwd]), FileSystemSandboxPolicy.unrestricted())

    def test_preserve_deny_read_restrictions_from_existing_policy(self):
        denied_glob = self._glob_entry(str(self._workspace_path("secrets") / "**" / "*.env"))
        existing = FileSystemSandboxPolicy(
            kind=FileSystemSandboxKind.RESTRICTED,
            entries=(denied_glob,),
            glob_scan_max_depth=4,
        )

        preserved = FileSystemSandboxPolicy.unrestricted().preserve_deny_read_restrictions_from(existing)

        self.assertEqual(preserved.kind, FileSystemSandboxKind.RESTRICTED)
        self.assertEqual(
            preserved.entries,
            (
                FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), FileSystemAccessMode.WRITE),
                denied_glob,
            ),
        )
        self.assertEqual(preserved.glob_scan_max_depth, 4)

    def test_semantic_signature_ignores_entry_order(self):
        cwd = self._workspace_path("semantic-order")
        docs = cwd / "docs"
        app = cwd / "app"
        env_glob = self._glob_entry(project_roots_glob_pattern(Path("**/*.env")))
        entries = (
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots()), FileSystemAccessMode.WRITE),
            self._entry(docs, FileSystemAccessMode.READ),
            self._entry(app, FileSystemAccessMode.WRITE),
            env_glob,
        )
        policy = FileSystemSandboxPolicy.restricted(entries)
        reordered = FileSystemSandboxPolicy.restricted(tuple(reversed(entries)))

        self.assertTrue(policy.is_semantically_equivalent_to(reordered, cwd))
        self.assertEqual(policy.semantic_signature(cwd), reordered.semantic_signature(cwd))

    def test_semantic_signature_sorts_roots_and_globs(self):
        cwd = self._workspace_path("semantic-sorting")
        alpha = cwd / "alpha"
        beta = cwd / "beta"
        policy = FileSystemSandboxPolicy.restricted(
            (
                self._entry(beta, FileSystemAccessMode.WRITE),
                self._entry(alpha, FileSystemAccessMode.WRITE),
                self._glob_entry(str(cwd / "z" / "*.env")),
                self._glob_entry(str(cwd / "a" / "*.env")),
                self._glob_entry(str(cwd / "a" / "*.env")),
            )
        )

        signature = policy.semantic_signature(cwd)

        self.assertIsInstance(signature, FileSystemSemanticSignature)
        self.assertEqual(tuple(root.root for root in signature.writable_roots), (alpha.resolve(), beta.resolve()))
        self.assertEqual(signature.unreadable_globs, (str(cwd / "a" / "*.env"), str(cwd / "z" / "*.env")))

    def test_semantic_signature_normalizes_writable_root_details(self):
        cwd = self._workspace_path("semantic-writable-root")
        policy = FileSystemSandboxPolicy.restricted(
            (
                self._entry(cwd, FileSystemAccessMode.WRITE),
                self._entry(cwd / "z", FileSystemAccessMode.READ),
                self._entry(cwd / "a", FileSystemAccessMode.READ),
            )
        )

        signature = policy.semantic_signature(cwd)

        self.assertEqual(
            signature.writable_roots[0].read_only_subpaths,
            ((cwd / ".codex").resolve(), (cwd / "a").resolve(), (cwd / "z").resolve()),
        )
        self.assertEqual(
            signature.writable_roots[0].protected_metadata_names,
            (".agents", ".codex", ".git"),
        )

    def test_semantic_signature_tracks_platform_defaults_flag(self):
        policy = FileSystemSandboxPolicy.restricted(
            (
                FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.minimal()), FileSystemAccessMode.READ),
                FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots()), FileSystemAccessMode.WRITE),
            )
        )

        self.assertTrue(policy.semantic_signature(self._workspace_path("semantic-minimal")).include_platform_defaults)

    def test_legacy_sandbox_policy_helpers(self):
        self.assertTrue(SandboxPolicy.danger_full_access().has_full_disk_write_access())
        self.assertTrue(SandboxPolicy.danger_full_access().has_full_network_access())
        self.assertFalse(SandboxPolicy.read_only().has_full_disk_write_access())
        self.assertFalse(SandboxPolicy.read_only().has_full_network_access())
        self.assertTrue(SandboxPolicy.read_only(network_access=True).has_full_network_access())
        self.assertTrue(SandboxPolicy.external_sandbox(NetworkSandboxPolicy.ENABLED).has_full_network_access())
        self.assertEqual(SandboxPolicy.new_read_only_policy(), SandboxPolicy.read_only())
        self.assertEqual(SandboxPolicy.new_workspace_write_policy(), SandboxPolicy.workspace_write())
        with self.assertRaisesRegex(ValueError, "unknown sandbox policy type"):
            SandboxPolicy("future")
        with self.assertRaisesRegex(TypeError, "danger-full-access network_access must be a bool"):
            SandboxPolicy("danger-full-access", network_access=NetworkSandboxPolicy.ENABLED)
        with self.assertRaisesRegex(ValueError, "danger-full-access policy cannot include network_access"):
            SandboxPolicy("danger-full-access", network_access=True)
        with self.assertRaisesRegex(ValueError, "danger-full-access policy cannot include writable_roots"):
            SandboxPolicy("danger-full-access", writable_roots=(Path("/tmp"),))
        with self.assertRaisesRegex(ValueError, "read-only policy cannot include exclude_slash_tmp"):
            SandboxPolicy("read-only", exclude_slash_tmp=True)
        with self.assertRaisesRegex(TypeError, "external-sandbox network_access must be NetworkSandboxPolicy"):
            SandboxPolicy("external-sandbox", network_access=True)
        with self.assertRaisesRegex(ValueError, "external-sandbox policy cannot include writable_roots"):
            SandboxPolicy("external-sandbox", writable_roots=(Path("/tmp"),), network_access=NetworkSandboxPolicy.RESTRICTED)
        with self.assertRaisesRegex(TypeError, "exclude_tmpdir_env_var must be a bool"):
            SandboxPolicy("workspace-write", exclude_tmpdir_env_var="false")
        with self.assertRaisesRegex(TypeError, "writable_roots must be a list"):
            SandboxPolicy("workspace-write", writable_roots="/tmp")
        with self.assertRaisesRegex(TypeError, "writable_roots entries must be strings or Path"):
            SandboxPolicy("workspace-write", writable_roots=(123,))
        with self.assertRaisesRegex(TypeError, "read-only network_access must be a bool"):
            SandboxPolicy.read_only(network_access="true")
        with self.assertRaisesRegex(TypeError, "external-sandbox network_access must be NetworkSandboxPolicy"):
            SandboxPolicy.external_sandbox(network_access="enabled")
        with self.assertRaisesRegex(TypeError, "workspace-write network_access must be a bool"):
            SandboxPolicy.workspace_write(network_access="true")
        with self.assertRaisesRegex(TypeError, "exclude_slash_tmp must be a bool"):
            SandboxPolicy.workspace_write(exclude_slash_tmp="false")
        with self.assertRaisesRegex(TypeError, "writable_roots must be a list"):
            SandboxPolicy.workspace_write(writable_roots="/tmp")
        with self.assertRaisesRegex(TypeError, "writable_roots entries must be strings or Path"):
            SandboxPolicy.workspace_write(writable_roots=(123,))

    def test_sandbox_enforcement_from_legacy_policy(self):
        self.assertIs(SandboxEnforcement.from_legacy_sandbox_policy(SandboxPolicy.danger_full_access()), SandboxEnforcement.DISABLED)
        self.assertIs(
            SandboxEnforcement.from_legacy_sandbox_policy(SandboxPolicy.external_sandbox(NetworkSandboxPolicy.RESTRICTED)),
            SandboxEnforcement.EXTERNAL,
        )
        self.assertIs(SandboxEnforcement.from_legacy_sandbox_policy(SandboxPolicy.read_only()), SandboxEnforcement.MANAGED)
        self.assertIs(SandboxEnforcement.from_legacy_sandbox_policy(SandboxPolicy.workspace_write()), SandboxEnforcement.MANAGED)

    def test_legacy_workspace_projection_preserves_symbolic_project_root(self):
        legacy = SandboxPolicy.workspace_write(exclude_tmpdir_env_var=True, exclude_slash_tmp=True)

        self.assertEqual(
            FileSystemSandboxPolicy.from_legacy_sandbox_policy(legacy),
            FileSystemSandboxPolicy.workspace_write(exclude_tmpdir_env_var=True, exclude_slash_tmp=True),
        )

    def test_legacy_policy_roundtrips_through_split_policy(self):
        cwd = self._workspace_path("legacy-roundtrip")
        writable_root = cwd / "extra"
        policies = (
            SandboxPolicy.danger_full_access(),
            SandboxPolicy.external_sandbox(NetworkSandboxPolicy.RESTRICTED),
            SandboxPolicy.external_sandbox(NetworkSandboxPolicy.ENABLED),
            SandboxPolicy.read_only(network_access=False),
            SandboxPolicy.read_only(network_access=True),
            SandboxPolicy.workspace_write(exclude_tmpdir_env_var=True, exclude_slash_tmp=True),
            SandboxPolicy.workspace_write([writable_root], network_access=True, exclude_tmpdir_env_var=False, exclude_slash_tmp=True),
        )

        for expected in policies:
            actual = FileSystemSandboxPolicy.from_legacy_sandbox_policy_for_cwd(expected, cwd).to_legacy_sandbox_policy(
                expected.network_sandbox_policy(),
                cwd,
            )
            self.assertEqual(actual.type, expected.type)
            self.assertEqual(actual.has_full_disk_write_access(), expected.has_full_disk_write_access())
            self.assertEqual(actual.has_full_network_access(), expected.has_full_network_access())
            if expected.type == "workspace-write":
                self.assertEqual(actual.writable_roots, expected.writable_roots)
                self.assertEqual(actual.exclude_tmpdir_env_var, expected.exclude_tmpdir_env_var)
                self.assertEqual(actual.exclude_slash_tmp, expected.exclude_slash_tmp)

    def test_unknown_special_paths_are_ignored_by_legacy_bridge(self):
        policy = FileSystemSandboxPolicy.restricted(
            (
                FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), FileSystemAccessMode.READ),
                FileSystemSandboxEntry(
                    FileSystemPath.special(FileSystemSpecialPath.unknown(":future_special_path")),
                    FileSystemAccessMode.WRITE,
                ),
            )
        )

        self.assertEqual(
            policy.to_legacy_sandbox_policy(NetworkSandboxPolicy.RESTRICTED, self._workspace_path("legacy-unknown")),
            SandboxPolicy.read_only(network_access=False),
        )

    def test_to_legacy_rejects_non_workspace_write_roots(self):
        cwd = self._workspace_path("legacy-reject")
        policy = FileSystemSandboxPolicy.restricted((self._entry(cwd.parent / "outside", FileSystemAccessMode.WRITE),))

        with self.assertRaisesRegex(ValueError, "filesystem writes outside the workspace root"):
            policy.to_legacy_sandbox_policy(NetworkSandboxPolicy.RESTRICTED, cwd)

    def test_from_legacy_preserving_deny_entries(self):
        cwd = self._workspace_path("legacy-preserve-deny")
        deny_entry = self._glob_entry(project_roots_glob_pattern(Path("**/*.env")))
        existing = FileSystemSandboxPolicy(
            kind=FileSystemSandboxKind.RESTRICTED,
            entries=(deny_entry,),
            glob_scan_max_depth=7,
        )

        rebuilt = FileSystemSandboxPolicy.from_legacy_sandbox_policy_preserving_deny_entries(
            SandboxPolicy.workspace_write(exclude_tmpdir_env_var=True, exclude_slash_tmp=True),
            cwd,
            existing,
        )

        self.assertIn(deny_entry, rebuilt.entries)
        self.assertEqual(rebuilt.glob_scan_max_depth, 7)

    def test_permission_profile_from_legacy_sandbox_policy(self):
        cwd = self._workspace_path("profile-legacy")

        self.assertEqual(
            PermissionProfile.from_legacy_sandbox_policy(SandboxPolicy.danger_full_access()),
            PermissionProfile.disabled(),
        )
        self.assertEqual(
            PermissionProfile.from_legacy_sandbox_policy(SandboxPolicy.external_sandbox(NetworkSandboxPolicy.ENABLED)),
            PermissionProfile.external(NetworkSandboxPolicy.ENABLED),
        )
        self.assertEqual(
            PermissionProfile.from_legacy_sandbox_policy(SandboxPolicy.read_only(network_access=True)),
            PermissionProfile.managed(
                ManagedFileSystemPermissions.from_sandbox_policy(FileSystemSandboxPolicy.from_legacy_sandbox_policy(SandboxPolicy.read_only())),
                NetworkSandboxPolicy.ENABLED,
            ),
        )

        workspace = SandboxPolicy.workspace_write([cwd / "extra"], network_access=True, exclude_tmpdir_env_var=True, exclude_slash_tmp=True)
        profile = PermissionProfile.from_legacy_sandbox_policy_for_cwd(workspace, cwd)

        self.assertIs(profile.enforcement(), SandboxEnforcement.MANAGED)
        self.assertEqual(profile.network_sandbox_policy(), NetworkSandboxPolicy.ENABLED)
        self.assertEqual(profile.to_legacy_sandbox_policy(cwd), workspace)

    def test_permission_profile_materializes_project_roots(self):
        first = self._workspace_path("profile-first")
        second = self._workspace_path("profile-second")
        profile = PermissionProfile.workspace_write(exclude_tmpdir_env_var=True, exclude_slash_tmp=True)

        materialized = profile.materialize_project_roots_with_workspace_roots([first, second])
        policy = materialized.file_system_sandbox_policy()

        self.assertIn(self._entry(first, FileSystemAccessMode.WRITE), policy.entries)
        self.assertIn(self._entry(second, FileSystemAccessMode.WRITE), policy.entries)
        self.assertNotIn(
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots()), FileSystemAccessMode.WRITE),
            policy.entries,
        )
        self.assertEqual(PermissionProfile.disabled().materialize_project_roots_with_workspace_roots([first]), PermissionProfile.disabled())
        self.assertEqual(
            PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED).materialize_project_roots_with_workspace_roots([first]),
            PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED),
        )

    def test_permission_profile_to_legacy_sandbox_policy(self):
        cwd = self._workspace_path("profile-to-legacy")

        self.assertEqual(PermissionProfile.disabled().to_legacy_sandbox_policy(cwd), SandboxPolicy.danger_full_access())
        self.assertEqual(
            PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED).to_legacy_sandbox_policy(cwd),
            SandboxPolicy.external_sandbox(NetworkSandboxPolicy.RESTRICTED),
        )
        self.assertEqual(PermissionProfile.read_only().to_legacy_sandbox_policy(cwd), SandboxPolicy.read_only(network_access=False))

        workspace = PermissionProfile.workspace_write(network=NetworkSandboxPolicy.ENABLED, exclude_tmpdir_env_var=True, exclude_slash_tmp=True)
        self.assertEqual(
            workspace.to_legacy_sandbox_policy(cwd),
            SandboxPolicy.workspace_write(network_access=True, exclude_tmpdir_env_var=True, exclude_slash_tmp=True),
        )

    def test_permission_profile_mapping_roundtrips_canonical_shapes(self):
        managed = PermissionProfile.workspace_write(network=NetworkSandboxPolicy.ENABLED, exclude_tmpdir_env_var=True, exclude_slash_tmp=True)
        disabled = PermissionProfile.disabled()
        external = PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED)

        self.assertEqual(PermissionProfile.from_mapping(managed.to_mapping()), managed)
        self.assertEqual(PermissionProfile.from_mapping(disabled.to_mapping()), disabled)
        self.assertEqual(PermissionProfile.from_mapping(external.to_mapping()), external)
        with self.assertRaisesRegex(TypeError, "network must be a string"):
            PermissionProfile.from_mapping(
                {
                    "type": "managed",
                    "file_system": {"type": "unrestricted"},
                    "network": 123,
                }
            )
        with self.assertRaisesRegex(TypeError, "network must be a string"):
            PermissionProfile.from_mapping({"type": "external", "network": 123})
        with self.assertRaisesRegex(ValueError, "unknown field"):
            PermissionProfile.from_mapping(
                {
                    "type": "managed",
                    "file_system": {"type": "unrestricted"},
                    "network": "restricted",
                    "unexpected": True,
                }
            )
        with self.assertRaisesRegex(ValueError, "unknown field"):
            PermissionProfile.from_mapping({"type": "disabled", "network": "restricted"})
        with self.assertRaisesRegex(ValueError, "unknown field"):
            PermissionProfile.from_mapping({"type": "external", "network": "restricted", "file_system": {"type": "unrestricted"}})
        self.assertEqual(ManagedFileSystemPermissions.from_mapping({"type": "unrestricted"}), ManagedFileSystemPermissions.unrestricted())
        with self.assertRaisesRegex(TypeError, "type must be a string"):
            ManagedFileSystemPermissions.from_mapping({"type": 123})
        with self.assertRaisesRegex(ValueError, "unknown field"):
            ManagedFileSystemPermissions.from_mapping({"type": "unrestricted", "entries": []})
        with self.assertRaisesRegex(ValueError, "unknown field"):
            ManagedFileSystemPermissions.from_mapping({"type": "restricted", "entries": [], "unexpected": True})
        with self.assertRaisesRegex(ValueError, "glob_scan_max_depth"):
            ManagedFileSystemPermissions.from_mapping({"type": "restricted", "entries": [], "glob_scan_max_depth": 0})
        with self.assertRaisesRegex(TypeError, "glob_scan_max_depth"):
            ManagedFileSystemPermissions.from_mapping({"type": "restricted", "entries": [], "glob_scan_max_depth": "2"})
        with self.assertRaisesRegex(ValueError, "glob_scan_max_depth"):
            ManagedFileSystemPermissions.restricted((), glob_scan_max_depth=0)
        with self.assertRaisesRegex(TypeError, "glob_scan_max_depth"):
            ManagedFileSystemPermissions.restricted((), glob_scan_max_depth="2")
        with self.assertRaisesRegex(ValueError, "unknown managed filesystem permission type"):
            ManagedFileSystemPermissions("future")
        with self.assertRaisesRegex(ValueError, "unrestricted managed filesystem permissions cannot include entries"):
            ManagedFileSystemPermissions("unrestricted", entries=(self._entry(Path("/tmp"), FileSystemAccessMode.READ),))
        with self.assertRaisesRegex(ValueError, "unrestricted managed filesystem permissions cannot include glob_scan_max_depth"):
            ManagedFileSystemPermissions("unrestricted", glob_scan_max_depth=1)
        with self.assertRaisesRegex(ValueError, "unknown permission profile type"):
            PermissionProfile("future")
        with self.assertRaisesRegex(TypeError, "type must be a string"):
            PermissionProfile.from_mapping({"type": 123})
        with self.assertRaisesRegex(TypeError, "managed permission profile requires ManagedFileSystemPermissions"):
            PermissionProfile("managed", network=NetworkSandboxPolicy.RESTRICTED)
        with self.assertRaisesRegex(TypeError, "managed permission profile requires NetworkSandboxPolicy"):
            PermissionProfile("managed", file_system=ManagedFileSystemPermissions.unrestricted())
        with self.assertRaisesRegex(ValueError, "disabled permission profile cannot include file_system"):
            PermissionProfile("disabled", file_system=ManagedFileSystemPermissions.unrestricted())
        with self.assertRaisesRegex(ValueError, "disabled permission profile cannot include network"):
            PermissionProfile("disabled", network=NetworkSandboxPolicy.RESTRICTED)
        with self.assertRaisesRegex(ValueError, "external permission profile cannot include file_system"):
            PermissionProfile("external", file_system=ManagedFileSystemPermissions.unrestricted(), network=NetworkSandboxPolicy.RESTRICTED)
        with self.assertRaisesRegex(TypeError, "external permission profile requires NetworkSandboxPolicy"):
            PermissionProfile("external")

    def test_permission_profile_deserializes_legacy_rollout_shape(self):
        legacy = {
            "network": {"enabled": True},
            "file_system": {
                "entries": [
                    {
                        "path": {
                            "type": "special",
                            "value": {"kind": "root"},
                        },
                        "access": "write",
                    }
                ],
                "glob_scan_max_depth": 2,
            },
        }

        permission_profile = PermissionProfile.from_mapping(legacy)

        self.assertEqual(
            permission_profile,
            PermissionProfile.managed(
                ManagedFileSystemPermissions.restricted(
                    (
                        FileSystemSandboxEntry(
                            FileSystemPath.special(FileSystemSpecialPath.root()),
                            FileSystemAccessMode.WRITE,
                        ),
                    ),
                    glob_scan_max_depth=2,
                ),
                NetworkSandboxPolicy.ENABLED,
            ),
        )

    def test_additional_permission_profile_mapping_roundtrips(self):
        additional = AdditionalPermissionProfile(
            network=NetworkPermissions(enabled=True),
            file_system=FileSystemPermissions.from_read_write_roots((Path("/read"),), (Path("/write"),)),
        )

        self.assertEqual(AdditionalPermissionProfile.from_mapping(additional.to_mapping()), additional)
        with self.assertRaisesRegex(TypeError, "network permissions must be a mapping"):
            AdditionalPermissionProfile.from_mapping({"network": "enabled"})
        with self.assertRaisesRegex(TypeError, "filesystem permissions must be a mapping"):
            AdditionalPermissionProfile.from_mapping({"file_system": "read"})

    def test_direct_runtime_enforcement_detects_unbridgeable_and_metadata_cases(self):
        cwd = self._workspace_path("direct-enforcement")
        unbridgeable = FileSystemSandboxPolicy.restricted((self._entry(cwd.parent / "outside", FileSystemAccessMode.WRITE),))
        self.assertTrue(unbridgeable.needs_direct_runtime_enforcement(NetworkSandboxPolicy.RESTRICTED, cwd))

        legacy_workspace = FileSystemSandboxPolicy.from_legacy_sandbox_policy_for_cwd(
            SandboxPolicy.workspace_write(exclude_tmpdir_env_var=True, exclude_slash_tmp=True),
            cwd,
        )
        self.assertTrue(legacy_workspace.needs_direct_runtime_enforcement(NetworkSandboxPolicy.RESTRICTED, cwd))

        read_only = FileSystemSandboxPolicy.from_legacy_sandbox_policy(SandboxPolicy.read_only())
        self.assertFalse(read_only.needs_direct_runtime_enforcement(NetworkSandboxPolicy.RESTRICTED, cwd))

    def test_managed_file_system_permissions_roundtrip_runtime_policy(self):
        policy = FileSystemSandboxPolicy.restricted(
            (FileSystemSandboxEntry(FileSystemPath.explicit_path("/tmp/project"), FileSystemAccessMode.WRITE),)
        )
        managed = ManagedFileSystemPermissions.from_sandbox_policy(policy)

        self.assertEqual(managed.to_sandbox_policy(), policy)
        self.assertEqual(ManagedFileSystemPermissions.from_sandbox_policy(FileSystemSandboxPolicy.unrestricted()), ManagedFileSystemPermissions.unrestricted())
        with self.assertRaisesRegex(ValueError, "external filesystem policies"):
            ManagedFileSystemPermissions.from_sandbox_policy(FileSystemSandboxPolicy.external_sandbox())

    def test_permission_profile_builtin_constructors_and_enforcement(self):
        read_only = PermissionProfile.read_only()
        workspace = PermissionProfile.workspace_write()
        disabled = PermissionProfile.disabled()
        external = PermissionProfile.external(NetworkSandboxPolicy.ENABLED)

        self.assertIs(read_only.enforcement(), SandboxEnforcement.MANAGED)
        self.assertEqual(read_only.network_sandbox_policy(), NetworkSandboxPolicy.RESTRICTED)
        self.assertEqual(read_only.file_system_sandbox_policy().entries[0].access, FileSystemAccessMode.READ)
        self.assertIs(workspace.enforcement(), SandboxEnforcement.MANAGED)
        self.assertEqual(workspace.file_system_sandbox_policy(), FileSystemSandboxPolicy.workspace_write())
        self.assertIs(disabled.enforcement(), SandboxEnforcement.DISABLED)
        self.assertEqual(disabled.file_system_sandbox_policy(), FileSystemSandboxPolicy.unrestricted())
        self.assertEqual(disabled.network_sandbox_policy(), NetworkSandboxPolicy.ENABLED)
        self.assertIs(external.enforcement(), SandboxEnforcement.EXTERNAL)
        self.assertEqual(external.file_system_sandbox_policy(), FileSystemSandboxPolicy.external_sandbox())
        self.assertEqual(external.network_sandbox_policy(), NetworkSandboxPolicy.ENABLED)

    def test_permission_profile_from_runtime_permissions(self):
        unrestricted = FileSystemSandboxPolicy.unrestricted()
        external_fs = FileSystemSandboxPolicy.external_sandbox()
        restricted = FileSystemSandboxPolicy.restricted(())

        self.assertEqual(
            PermissionProfile.from_runtime_permissions_with_enforcement(
                SandboxEnforcement.DISABLED,
                unrestricted,
                NetworkSandboxPolicy.RESTRICTED,
            ),
            PermissionProfile.disabled(),
        )
        self.assertEqual(
            PermissionProfile.from_runtime_permissions(external_fs, NetworkSandboxPolicy.ENABLED),
            PermissionProfile.external(NetworkSandboxPolicy.ENABLED),
        )
        self.assertEqual(
            PermissionProfile.from_runtime_permissions(restricted, NetworkSandboxPolicy.RESTRICTED),
            PermissionProfile.managed(ManagedFileSystemPermissions.restricted(()), NetworkSandboxPolicy.RESTRICTED),
        )

    def test_active_permission_profile_read_only_identity(self):
        self.assertEqual(ActivePermissionProfile.read_only(), ActivePermissionProfile(BUILT_IN_PERMISSION_PROFILE_READ_ONLY))
        self.assertEqual(ActivePermissionProfile.new("dev"), ActivePermissionProfile("dev"))
        self.assertEqual(ActivePermissionProfile.from_mapping({"id": "dev", "extends": ":workspace"}), ActivePermissionProfile("dev", ":workspace"))
        self.assertEqual(ActivePermissionProfile("dev").to_mapping(), {"id": "dev"})
        with self.assertRaisesRegex(TypeError, "id must be a string"):
            ActivePermissionProfile(123)
        with self.assertRaisesRegex(TypeError, "extends must be a string"):
            ActivePermissionProfile("dev", 123)
        with self.assertRaisesRegex(TypeError, "id must be a string"):
            ActivePermissionProfile.from_mapping({"id": 123})
        with self.assertRaisesRegex(TypeError, "extends must be a string"):
            ActivePermissionProfile.from_mapping({"id": "dev", "extends": 123})


if __name__ == "__main__":
    unittest.main()
