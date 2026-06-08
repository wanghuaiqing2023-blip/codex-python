import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from pycodex.core.tools.handlers.utils import (
    EffectiveAdditionalPermissions,
    apply_granted_turn_permissions,
    implicit_granted_permissions,
    intersect_permission_profiles,
    merge_permission_profiles,
    normalize_and_validate_additional_permissions,
    normalize_request_permissions_response,
    parse_arguments,
    permissions_are_preapproved,
    record_granted_request_permissions,
    resolve_tool_environment,
    resolve_workdir_base_path,
    rewrite_function_string_argument,
    session_strict_auto_review,
    updated_hook_command,
)
from pycodex.core.tools import handlers as handler_package
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import (
    AdditionalPermissionProfile,
    AskForApproval,
    FileSystemAccessMode,
    FileSystemPermissions,
    FileSystemSandboxEntry,
    FileSystemPath,
    FileSystemSpecialPath,
    GranularApprovalConfig,
    NetworkPermissions,
    PermissionGrantScope,
    RequestPermissionProfile,
    RequestPermissionsResponse,
    SandboxPermissions,
)


class HandlerUtilsTests(unittest.TestCase):
    def test_parse_arguments_wraps_json_errors_for_model(self):
        # Rust source: codex-core/src/tools/handlers/mod.rs
        # Rust contract: parse_arguments maps JSON errors to RespondToModel.
        with self.assertRaisesRegex(FunctionCallError, "failed to parse function arguments"):
            parse_arguments("{")

    def test_updated_hook_command_matches_rust_error_surface(self):
        # Rust source: codex-core/src/tools/handlers/mod.rs
        # Rust contract: updated_hook_command requires string field `command`.
        self.assertEqual(updated_hook_command({"command": "pwd"}), "pwd")
        with self.assertRaisesRegex(FunctionCallError, "updatedInput without string field `command`"):
            updated_hook_command({"command": 1})

    def test_rewrite_function_string_argument_requires_object(self):
        # Rust source: codex-core/src/tools/handlers/mod.rs
        # Rust contract: rewrite_function_string_argument rewrites object fields only.
        rewritten = rewrite_function_string_argument('{"cmd":"old","keep":true}', "exec_command", "cmd", "new")
        self.assertEqual(json.loads(rewritten), {"cmd": "new", "keep": True})
        with self.assertRaisesRegex(FunctionCallError, "exec_command arguments must be an object"):
            rewrite_function_string_argument("[]", "exec_command", "cmd", "new")

    def test_handler_package_reexports_shared_mod_helpers(self):
        # Rust source: codex-core/src/tools/handlers/mod.rs
        # Python coordinate: pycodex.core.tools.handlers package exposes this shared mod surface.
        self.assertIs(handler_package.parse_arguments, parse_arguments)
        self.assertIs(handler_package.updated_hook_command, updated_hook_command)
        self.assertIs(handler_package.rewrite_function_string_argument, rewrite_function_string_argument)

    def test_handler_package_reexports_rust_root_handler_names(self):
        # Rust source: codex-core/src/tools/handlers/mod.rs
        # Rust contract: the module root re-exports public handler types.
        from pycodex.core.tools.handlers.shell import ShellCommandHandler
        from pycodex.core.tools.handlers.unified_exec import ExecCommandHandler, WriteStdinHandler
        from pycodex.core.tools.handlers.view_image import ViewImageHandler

        self.assertIs(handler_package.ShellCommandHandler, ShellCommandHandler)
        self.assertIs(handler_package.ExecCommandHandler, ExecCommandHandler)
        self.assertIs(handler_package.WriteStdinHandler, WriteStdinHandler)
        self.assertIs(handler_package.ViewImageHandler, ViewImageHandler)

    def test_shell_and_unified_exec_reuse_shared_updated_hook_command(self):
        # Direct adjacent smoke: concrete handlers should not keep a duplicate
        # implementation of Rust handlers/mod.rs updated_hook_command.
        from pycodex.core.tools.handlers import shell, unified_exec

        self.assertEqual(shell.updated_hook_command({"command": "pwd"}), "pwd")
        self.assertEqual(unified_exec.updated_hook_command({"command": "pwd"}), "pwd")
        with self.assertRaisesRegex(FunctionCallError, "updatedInput without string field `command`"):
            shell.updated_hook_command({"command": 1})
        with self.assertRaisesRegex(FunctionCallError, "updatedInput without string field `command`"):
            unified_exec.updated_hook_command({"command": 1})

    def test_resolve_workdir_base_path_uses_default_for_missing_or_empty(self):
        cwd = Path("/workspace")
        self.assertEqual(resolve_workdir_base_path('{"workdir":""}', cwd), cwd)
        self.assertEqual(resolve_workdir_base_path('{"workdir":"pkg"}', cwd), cwd / "pkg")

    def test_resolve_tool_environment_selects_primary_or_matching_id(self):
        class Env:
            def __init__(self, environment_id):
                self.environment_id = environment_id

        class Envs:
            turn_environments = (Env("one"), Env("two"))

            def primary(self):
                return self.turn_environments[0]

        class Turn:
            environments = Envs()

        self.assertEqual(resolve_tool_environment(Turn(), None).environment_id, "one")
        self.assertEqual(resolve_tool_environment(Turn(), "two").environment_id, "two")
        with self.assertRaisesRegex(FunctionCallError, "unknown turn environment id `missing`"):
            resolve_tool_environment(Turn(), "missing")

    def test_additional_permissions_validation_matches_feature_gates(self):
        # Rust source: codex-core/src/tools/handlers/mod.rs
        # Rust contract: fresh inline additional permissions require the
        # exec-permission-approvals feature and with_additional_permissions mode.
        profile = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        self.assertEqual(
            normalize_and_validate_additional_permissions(
                True,
                AskForApproval.ON_REQUEST,
                SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
                profile,
                False,
                Path("/workspace"),
            ),
            profile,
        )
        with self.assertRaisesRegex(ValueError, "additional permissions are disabled"):
            normalize_and_validate_additional_permissions(
                False,
                AskForApproval.ON_REQUEST,
                SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
                profile,
                False,
                Path("/workspace"),
            )
        with self.assertRaisesRegex(ValueError, "requires `sandbox_permissions`"):
            normalize_and_validate_additional_permissions(
                True,
                AskForApproval.ON_REQUEST,
                SandboxPermissions.USE_DEFAULT,
                profile,
                False,
                Path("/workspace"),
            )

    def test_preapproved_permissions_work_when_exec_permission_approvals_disabled(self):
        # Rust source: codex-core/src/tools/handlers/mod.rs
        # Rust test: preapproved_permissions_work_when_request_permissions_tool_is_enabled_without_exec_permission_approvals_feature
        profile = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        policy = GranularApprovalConfig(
            sandbox_approval=True,
            rules=True,
            skill_approval=True,
            request_permissions=False,
            mcp_elicitations=True,
        )

        normalized = normalize_and_validate_additional_permissions(
            False,
            policy,
            SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
            profile,
            True,
            Path("/workspace"),
        )

        self.assertEqual(normalized, profile)

    def test_additional_permissions_rejects_unapproved_granular_policy_like_rust(self):
        # Rust source: codex-core/src/tools/handlers/mod.rs
        # Rust contract: non-preapproved inline permissions require OnRequest
        # approval policy even when the feature gate is enabled.
        profile = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        policy = GranularApprovalConfig(
            sandbox_approval=True,
            rules=True,
            skill_approval=False,
            request_permissions=True,
            mcp_elicitations=False,
        )
        with self.assertRaisesRegex(ValueError, "unless the approval policy is OnRequest"):
            normalize_and_validate_additional_permissions(
                True,
                policy,
                SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
                profile,
                False,
                Path("/workspace"),
            )
        self.assertEqual(
            normalize_and_validate_additional_permissions(
                True,
                policy,
                SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
                profile,
                True,
                Path("/workspace"),
            ),
            profile,
        )

    def test_implicit_granted_permissions_only_apply_to_default_requests(self):
        # Rust source: codex-core/src/tools/handlers/mod.rs
        # Rust tests: implicit_sticky_grants_bypass_inline_permission_validation
        # and explicit_inline_permissions_do_not_use_implicit_sticky_grant_path
        profile = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        effective = EffectiveAdditionalPermissions(
            SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
            profile,
            False,
        )
        self.assertEqual(implicit_granted_permissions(SandboxPermissions.USE_DEFAULT, None, effective), profile)
        self.assertIsNone(implicit_granted_permissions(SandboxPermissions.REQUIRE_ESCALATED, None, effective))
        self.assertIsNone(implicit_granted_permissions(SandboxPermissions.USE_DEFAULT, profile, effective))

    def test_permissions_are_preapproved_after_relative_path_materialization(self):
        # Rust source: codex-core/src/tools/handlers/mod.rs
        # Rust contract: preapproval compares materialized effective permissions.
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            requested = AdditionalPermissionProfile(
                file_system=FileSystemPermissions(
                    entries=(
                        FileSystemSandboxEntry(
                            FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                            FileSystemAccessMode.WRITE,
                        ),
                    )
                )
            )
            granted = AdditionalPermissionProfile(
                file_system=FileSystemPermissions.from_read_write_roots(None, (cwd,))
            )
            self.assertTrue(permissions_are_preapproved(requested, granted, cwd))

    def test_relative_deny_glob_grants_remain_preapproved_after_materialization(self):
        # Rust source: codex-core/src/tools/handlers/mod.rs
        # Rust test: relative_deny_glob_grants_remain_preapproved_after_materialization
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            requested = AdditionalPermissionProfile(
                file_system=FileSystemPermissions(
                    entries=(
                        FileSystemSandboxEntry(
                            FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                            FileSystemAccessMode.WRITE,
                        ),
                        FileSystemSandboxEntry(
                            FileSystemPath.glob_pattern("**/*.env"),
                            FileSystemAccessMode.DENY,
                        ),
                    )
                )
            )
            stored_grant = intersect_permission_profiles(requested, requested, cwd)
            effective_permissions = merge_permission_profiles(requested, stored_grant)

            self.assertTrue(permissions_are_preapproved(effective_permissions, stored_grant, cwd))

    def test_normalize_request_permissions_response_rejects_strict_session_scope_like_rust(self):
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.SESSION,
            strict_auto_review=True,
        )

        normalized = normalize_request_permissions_response(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            response,
            Path("/workspace"),
        )

        self.assertEqual(normalized, RequestPermissionsResponse(RequestPermissionProfile()))

    def test_normalize_request_permissions_response_intersects_granted_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            requested_child = cwd / "child"
            broader_grant = cwd
            requested = RequestPermissionProfile.from_additional_permission_profile(
                AdditionalPermissionProfile(
                    network=NetworkPermissions(enabled=True),
                    file_system=FileSystemPermissions.from_read_write_roots(None, (requested_child,)),
                )
            )
            response = RequestPermissionsResponse(
                RequestPermissionProfile.from_additional_permission_profile(
                    AdditionalPermissionProfile(
                        network=NetworkPermissions(enabled=True),
                        file_system=FileSystemPermissions.from_read_write_roots(None, (broader_grant,)),
                    )
                ),
                scope=PermissionGrantScope.SESSION,
            )

            normalized = normalize_request_permissions_response(requested, response, cwd)

        self.assertEqual(normalized.scope, PermissionGrantScope.SESSION)
        self.assertEqual(normalized.permissions.network, NetworkPermissions(enabled=True))
        self.assertIsNone(normalized.permissions.file_system)

    def test_apply_granted_turn_permissions_merges_session_and_turn_grants(self):
        class Session:
            async def granted_session_permissions(self):
                return AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))

            def granted_turn_permissions(self):
                return None

        effective = asyncio.run(
            apply_granted_turn_permissions(Session(), Path("/workspace"), SandboxPermissions.USE_DEFAULT, None)
        )
        self.assertEqual(effective.sandbox_permissions, SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS)
        self.assertEqual(effective.additional_permissions.network, NetworkPermissions(enabled=True))

    def test_apply_granted_turn_permissions_merges_explicit_and_sticky_grants_like_rust(self):
        # Rust source: codex-core/src/tools/handlers/mod.rs
        # Rust contract: apply_granted_turn_permissions merges explicit inline
        # permissions with sticky session/turn grants before preapproval checks.
        class Session:
            async def granted_session_permissions(self):
                return AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))

            def granted_turn_permissions(self):
                return None

        explicit = AdditionalPermissionProfile(
            file_system=FileSystemPermissions.from_read_write_roots(None, (Path("/workspace/out"),))
        )

        effective = asyncio.run(
            apply_granted_turn_permissions(
                Session(),
                Path("/workspace"),
                SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
                explicit,
            )
        )

        self.assertEqual(effective.sandbox_permissions, SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS)
        self.assertEqual(effective.additional_permissions.network, NetworkPermissions(enabled=True))
        self.assertEqual(effective.additional_permissions.file_system, explicit.file_system)

    def test_session_strict_auto_review_reads_async_method_or_bool_attribute(self):
        class MethodSession:
            async def strict_auto_review(self):
                return True

        class AttrSession:
            strict_auto_review_enabled = True

        self.assertTrue(asyncio.run(session_strict_auto_review(MethodSession())))
        self.assertTrue(asyncio.run(session_strict_auto_review(AttrSession())))
        self.assertFalse(asyncio.run(session_strict_auto_review(None)))

    def test_record_granted_request_permissions_records_turn_and_strict_auto_review(self):
        class TurnState:
            def __init__(self):
                self.recorded = None
                self.strict = False

            def record_granted_permissions(self, permissions):
                self.recorded = permissions

            def enable_strict_auto_review(self):
                self.strict = True

        turn_state = TurnState()
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.TURN,
            strict_auto_review=True,
        )

        recorded = asyncio.run(
            record_granted_request_permissions(response, turn_state=turn_state)
        )

        self.assertTrue(recorded)
        self.assertEqual(
            turn_state.recorded,
            AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )
        self.assertTrue(turn_state.strict)

    def test_record_granted_request_permissions_ignores_empty_strict_turn_response_like_rust(self):
        class TurnState:
            def __init__(self):
                self.recorded = None
                self.strict = False

            def record_granted_permissions(self, permissions):
                self.recorded = permissions

            def enable_strict_auto_review(self):
                self.strict = True

        turn_state = TurnState()
        response = RequestPermissionsResponse(
            RequestPermissionProfile(),
            scope=PermissionGrantScope.TURN,
            strict_auto_review=True,
        )

        recorded = asyncio.run(record_granted_request_permissions(response, turn_state=turn_state))

        self.assertFalse(recorded)
        self.assertIsNone(turn_state.recorded)
        self.assertFalse(turn_state.strict)

    def test_record_granted_request_permissions_records_session_scope(self):
        class Session:
            def __init__(self):
                self.recorded = None

            async def record_granted_permissions(self, permissions):
                self.recorded = permissions

        session = Session()
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.SESSION,
        )

        recorded = asyncio.run(record_granted_request_permissions(response, session=session))

        self.assertTrue(recorded)
        self.assertEqual(
            session.recorded,
            AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )

    def test_record_granted_request_permissions_fallback_merges_existing_async_grants(self):
        class Session:
            async def granted_permissions(self):
                return AdditionalPermissionProfile(
                    file_system=FileSystemPermissions.from_read_write_roots(("/tmp/read",), None)
                )

        session = Session()
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.SESSION,
        )

        recorded = asyncio.run(record_granted_request_permissions(response, session=session))

        self.assertTrue(recorded)
        self.assertEqual(
            session.granted_permissions,
            AdditionalPermissionProfile(
                network=NetworkPermissions(enabled=True),
                file_system=FileSystemPermissions.from_read_write_roots(("/tmp/read",), None),
            ),
        )

    def test_intersect_permission_profiles_accepts_child_path_granted_for_requested_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            child = cwd / "child"
            requested = AdditionalPermissionProfile(
                file_system=FileSystemPermissions(
                    entries=(
                        FileSystemSandboxEntry(
                            FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                            FileSystemAccessMode.WRITE,
                        ),
                    )
                )
            )
            granted = AdditionalPermissionProfile(
                file_system=FileSystemPermissions.from_read_write_roots(None, (child,))
            )

            intersected = intersect_permission_profiles(requested, granted, cwd)

        self.assertEqual(
            intersected.file_system.entries,
            (
                FileSystemSandboxEntry(
                    FileSystemPath.explicit_path(child),
                    FileSystemAccessMode.WRITE,
                ),
            ),
        )

    def test_intersect_permission_profiles_drops_broader_cwd_grant_for_requested_child_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            child = cwd / "child"
            requested = AdditionalPermissionProfile(
                file_system=FileSystemPermissions.from_read_write_roots(None, (child,))
            )
            granted = AdditionalPermissionProfile(
                file_system=FileSystemPermissions(
                    entries=(
                        FileSystemSandboxEntry(
                            FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                            FileSystemAccessMode.WRITE,
                        ),
                    )
                )
            )

            intersected = intersect_permission_profiles(requested, granted, cwd)

        self.assertIsNone(intersected.file_system)

    def test_intersect_permission_profiles_rejects_grants_matched_by_requested_deny_globs(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            env_file = cwd / "token.env"
            requested = AdditionalPermissionProfile(
                file_system=FileSystemPermissions(
                    entries=(
                        FileSystemSandboxEntry(
                            FileSystemPath.special(FileSystemSpecialPath.root()),
                            FileSystemAccessMode.WRITE,
                        ),
                        FileSystemSandboxEntry(
                            FileSystemPath.glob_pattern("**/*.env"),
                            FileSystemAccessMode.DENY,
                        ),
                    ),
                    glob_scan_max_depth=2,
                )
            )
            granted = AdditionalPermissionProfile(
                file_system=FileSystemPermissions.from_read_write_roots(None, (env_file,))
            )

            intersected = intersect_permission_profiles(requested, granted, cwd)

        self.assertIsNone(intersected.file_system)

    def test_intersect_permission_profiles_materializes_relative_deny_globs_for_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            request_cwd = Path(tmp) / "request-cwd"
            later_cwd = Path(tmp) / "later-cwd"
            cwd_write = FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                FileSystemAccessMode.WRITE,
            )
            deny_env_files = FileSystemSandboxEntry(
                FileSystemPath.glob_pattern("**/*.env"),
                FileSystemAccessMode.DENY,
            )
            permissions = AdditionalPermissionProfile(
                file_system=FileSystemPermissions(
                    entries=(cwd_write, deny_env_files),
                    glob_scan_max_depth=2,
                )
            )

            intersected = intersect_permission_profiles(permissions, permissions, request_cwd)
            later_request = AdditionalPermissionProfile(
                file_system=FileSystemPermissions.from_read_write_roots(None, (later_cwd / "token.env",))
            )
            later_intersected = intersect_permission_profiles(later_request, intersected, later_cwd)

        self.assertEqual(
            intersected.file_system.entries,
            (
                FileSystemSandboxEntry(
                    FileSystemPath.explicit_path(request_cwd),
                    FileSystemAccessMode.WRITE,
                ),
                FileSystemSandboxEntry(
                    FileSystemPath.glob_pattern(str(request_cwd / "**/*.env")),
                    FileSystemAccessMode.DENY,
                ),
            ),
        )
        self.assertEqual(intersected.file_system.glob_scan_max_depth, 2)
        self.assertIsNone(later_intersected.file_system)

    def test_intersect_permission_profiles_uses_granted_bounded_glob_scan_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            root_write = FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.root()),
                FileSystemAccessMode.WRITE,
            )
            deny_env_files = FileSystemSandboxEntry(
                FileSystemPath.glob_pattern("**/*.env"),
                FileSystemAccessMode.DENY,
            )
            requested = AdditionalPermissionProfile(
                file_system=FileSystemPermissions(
                    entries=(root_write, deny_env_files),
                    glob_scan_max_depth=2,
                )
            )
            granted = AdditionalPermissionProfile(
                file_system=FileSystemPermissions(
                    entries=(root_write, deny_env_files),
                    glob_scan_max_depth=4,
                )
            )

            intersected = intersect_permission_profiles(requested, granted, cwd)

        self.assertEqual(intersected.file_system.glob_scan_max_depth, 4)
        self.assertEqual(
            intersected.file_system.entries,
            (
                root_write,
                FileSystemSandboxEntry(
                    FileSystemPath.glob_pattern(str(cwd / "**/*.env")),
                    FileSystemAccessMode.DENY,
                ),
            ),
        )

    def test_intersect_permission_profiles_uses_granted_unbounded_glob_scan_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            root_write = FileSystemSandboxEntry(
                FileSystemPath.special(FileSystemSpecialPath.root()),
                FileSystemAccessMode.WRITE,
            )
            deny_env_files = FileSystemSandboxEntry(
                FileSystemPath.glob_pattern("**/*.env"),
                FileSystemAccessMode.DENY,
            )
            requested = AdditionalPermissionProfile(
                file_system=FileSystemPermissions(
                    entries=(root_write, deny_env_files),
                    glob_scan_max_depth=2,
                )
            )
            granted = AdditionalPermissionProfile(
                file_system=FileSystemPermissions(
                    entries=(root_write, deny_env_files),
                    glob_scan_max_depth=None,
                )
            )

            intersected = intersect_permission_profiles(requested, granted, cwd)

        self.assertIsNone(intersected.file_system.glob_scan_max_depth)
        self.assertEqual(
            intersected.file_system.entries,
            (
                root_write,
                FileSystemSandboxEntry(
                    FileSystemPath.glob_pattern(str(cwd / "**/*.env")),
                    FileSystemAccessMode.DENY,
                ),
            ),
        )

    def test_merge_permission_profiles_merges_glob_scan_depth_like_rust(self):
        base_deny = FileSystemSandboxEntry(
            FileSystemPath.glob_pattern("**/*.secret"),
            FileSystemAccessMode.DENY,
        )
        granted_deny = FileSystemSandboxEntry(
            FileSystemPath.glob_pattern("**/*.env"),
            FileSystemAccessMode.DENY,
        )

        merged = merge_permission_profiles(
            AdditionalPermissionProfile(
                file_system=FileSystemPermissions((base_deny,), glob_scan_max_depth=2)
            ),
            AdditionalPermissionProfile(
                file_system=FileSystemPermissions((granted_deny,), glob_scan_max_depth=4)
            ),
        )

        self.assertIsNotNone(merged)
        self.assertEqual(merged.file_system.glob_scan_max_depth, 4)

    def test_merge_permission_profiles_preserves_unbounded_glob_scan_like_rust(self):
        base_deny = FileSystemSandboxEntry(
            FileSystemPath.glob_pattern("**/*.secret"),
            FileSystemAccessMode.DENY,
        )
        granted_deny = FileSystemSandboxEntry(
            FileSystemPath.glob_pattern("**/*.env"),
            FileSystemAccessMode.DENY,
        )

        merged = merge_permission_profiles(
            AdditionalPermissionProfile(
                file_system=FileSystemPermissions((base_deny,), glob_scan_max_depth=None)
            ),
            AdditionalPermissionProfile(
                file_system=FileSystemPermissions((granted_deny,), glob_scan_max_depth=4)
            ),
        )

        self.assertIsNotNone(merged)
        self.assertIsNone(merged.file_system.glob_scan_max_depth)


if __name__ == "__main__":
    unittest.main()

