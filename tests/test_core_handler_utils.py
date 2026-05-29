import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from pycodex.core.handler_utils import (
    EffectiveAdditionalPermissions,
    apply_granted_turn_permissions,
    implicit_granted_permissions,
    normalize_and_validate_additional_permissions,
    parse_arguments,
    permissions_are_preapproved,
    resolve_tool_environment,
    resolve_workdir_base_path,
    rewrite_function_string_argument,
    updated_hook_command,
)
from pycodex.core.tool_router import FunctionCallError
from pycodex.protocol import (
    AdditionalPermissionProfile,
    AskForApproval,
    FileSystemAccessMode,
    FileSystemPermissions,
    FileSystemSandboxEntry,
    FileSystemPath,
    FileSystemSpecialPath,
    NetworkPermissions,
    SandboxPermissions,
)


class HandlerUtilsTests(unittest.TestCase):
    def test_parse_arguments_wraps_json_errors_for_model(self):
        with self.assertRaisesRegex(FunctionCallError, "failed to parse function arguments"):
            parse_arguments("{")

    def test_updated_hook_command_matches_rust_error_surface(self):
        self.assertEqual(updated_hook_command({"command": "pwd"}), "pwd")
        with self.assertRaisesRegex(FunctionCallError, "updatedInput without string field `command`"):
            updated_hook_command({"command": 1})

    def test_rewrite_function_string_argument_requires_object(self):
        rewritten = rewrite_function_string_argument('{"cmd":"old","keep":true}', "exec_command", "cmd", "new")
        self.assertEqual(json.loads(rewritten), {"cmd": "new", "keep": True})
        with self.assertRaisesRegex(FunctionCallError, "exec_command arguments must be an object"):
            rewrite_function_string_argument("[]", "exec_command", "cmd", "new")

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

    def test_implicit_granted_permissions_only_apply_to_default_requests(self):
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


if __name__ == "__main__":
    unittest.main()
