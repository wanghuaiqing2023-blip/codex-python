import asyncio
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path

from pycodex.core import (
    FunctionCallError,
    ToolCallSource,
    ToolCall,
    ToolInvocation,
    ToolPayload,
    ToolRegistry,
    ToolRouter,
)
from pycodex.core.tools.handlers.request_permissions import (
    REQUEST_PERMISSIONS_TOOL_NAME,
    RequestPermissionsHandler,
    create_request_permissions_tool,
    normalize_request_permission_paths,
    parse_request_permissions_arguments,
    request_permissions_tool_description,
    request_profile_with_file_system,
    request_profile_with_network,
)
from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPermissions,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSpecialPath,
    NetworkPermissions,
    PermissionGrantScope,
    RequestPermissionProfile,
    RequestPermissionsArgs,
    RequestPermissionsResponse,
    SearchToolCallParams,
    ToolName,
)


def network_args_json() -> str:
    return json.dumps(
        {
            "permissions": {"network": {"enabled": True}},
            "reason": "Need network",
        }
    )


class RequestPermissionsHandlerTests(unittest.TestCase):
    def test_request_permissions_tool_schema_matches_upstream_shape(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/shell_spec.rs::create_request_permissions_tool
        # Rust test: shell_spec_tests.rs::request_permissions_tool_includes_full_permission_schema
        description = request_permissions_tool_description()
        spec = create_request_permissions_tool(description)

        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], REQUEST_PERMISSIONS_TOOL_NAME)
        self.assertEqual(spec["description"], description)
        self.assertFalse(spec["strict"])
        self.assertIsNone(spec["defer_loading"])
        self.assertIsNone(spec["output_schema"])
        self.assertEqual(spec["parameters"]["required"], ["permissions"])
        self.assertFalse(spec["parameters"]["additionalProperties"])
        self.assertEqual(
            spec["parameters"]["properties"]["reason"],
            {
                "type": "string",
                "description": "Optional short explanation for why additional permissions are needed.",
            },
        )
        permissions = spec["parameters"]["properties"]["permissions"]
        self.assertEqual(permissions["type"], "object")
        self.assertFalse(permissions["additionalProperties"])
        self.assertEqual(
            permissions["properties"]["network"],
            {
                "type": "object",
                "properties": {
                    "enabled": {
                        "type": "boolean",
                        "description": "Set to true to request network access.",
                    },
                },
                "additionalProperties": False,
            },
        )
        self.assertEqual(
            permissions["properties"]["file_system"],
            {
                "type": "object",
                "properties": {
                    "read": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Absolute paths to grant read access to.",
                    },
                    "write": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Absolute paths to grant write access to.",
                    },
                },
                "additionalProperties": False,
            },
        )

    def test_parse_request_permissions_arguments(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/request_permissions.rs
        # Rust contract: handler parses RequestPermissionsArgs and normalizes additional permissions.
        args = parse_request_permissions_arguments(network_args_json())

        self.assertEqual(args.reason, "Need network")
        self.assertEqual(args.permissions, request_profile_with_network())

    def test_parse_request_permissions_arguments_resolves_relative_paths_from_cwd(self) -> None:
        cwd = Path.cwd()
        absolute_input = cwd / "already" / "absolute"
        args = parse_request_permissions_arguments(
            json.dumps(
                {
                    "permissions": {
                        "file_system": {
                            "read": ["relative/input.txt", str(absolute_input)],
                            "write": ["out"],
                        }
                    }
                }
            ),
            cwd=cwd,
        )

        self.assertEqual(
            args.permissions,
            request_profile_with_file_system(
                read=(cwd / "relative" / "input.txt", absolute_input),
                write=(cwd / "out",),
            ),
        )

        with self.assertRaisesRegex(FunctionCallError, "cwd must be an absolute path"):
            parse_request_permissions_arguments(
                json.dumps({"permissions": {"file_system": {"read": ["relative"]}}}),
                cwd=Path("workspace"),
            )

    def test_handler_requests_permissions_and_serializes_response(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/request_permissions.rs::RequestPermissionsHandler::handle
        # Rust contract: granted client response is serialized as successful FunctionToolOutput text.
        captured = {}

        def callback(call_id, args):
            captured["call_id"] = call_id
            captured["args"] = args
            return RequestPermissionsResponse(
                permissions=args.permissions,
                scope=PermissionGrantScope.SESSION,
            )

        handler = RequestPermissionsHandler(callback)
        output = handler.handle(ToolPayload.function(network_args_json()), call_id="call-1")

        self.assertEqual(handler.tool_name(), ToolName.plain("request_permissions"))
        self.assertFalse(handler.supports_parallel_tool_calls())
        self.assertTrue(handler.matches_kind(ToolPayload.function("{}")))
        self.assertFalse(handler.matches_kind(ToolPayload.custom("raw")))
        self.assertFalse(handler.matches_kind(ToolPayload.tool_search(SearchToolCallParams("repo"))))
        self.assertEqual(captured["call_id"], "call-1")
        self.assertEqual(captured["args"].permissions, request_profile_with_network())
        self.assertEqual(
            json.loads(output.into_text()),
            {
                "permissions": {"network": {"enabled": True}},
                "scope": "session",
            },
        )

    def test_handler_uses_invocation_call_id_and_turn_cwd_like_rust(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/request_permissions.rs
        # Rust contract: function payload arguments are parsed relative to the turn cwd.
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            captured = {}

            def callback(call_id, args):
                captured["call_id"] = call_id
                captured["args"] = args
                return RequestPermissionsResponse(
                    permissions=args.permissions,
                    scope=PermissionGrantScope.TURN,
                )

            invocation = ToolInvocation(
                session=None,
                turn=SimpleNamespace(cwd=cwd),
                cancellation_token=None,
                tracker=None,
                call_id="call-from-invocation",
                tool_name=REQUEST_PERMISSIONS_TOOL_NAME,
                source=ToolCallSource.direct(),
                payload=ToolPayload.function(
                    json.dumps({"permissions": {"file_system": {"read": ["relative.txt"]}}})
                ),
            )
            output = RequestPermissionsHandler(callback).handle(invocation)

        self.assertEqual(captured["call_id"], "call-from-invocation")
        self.assertEqual(
            captured["args"].permissions,
            request_profile_with_file_system(read=(cwd / "relative.txt",)),
        )
        self.assertEqual(
            json.loads(output.into_text()),
            {
                "permissions": {
                    "file_system": {
                        "read": [str(cwd / "relative.txt")],
                    }
                },
                "scope": "turn",
            },
        )

    def test_handler_prefers_rust_style_session_request_permissions_entrypoint(self) -> None:
        # Rust behavior source:
        # codex/codex-rs/core/src/tools/handlers/request_permissions.rs
        # RequestPermissionsHandler::handle calls session.request_permissions(&turn, call_id, args, cancellation_token).
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            captured = {}

            class Session:
                async def request_permissions(self, parent_ctx, call_id, args, cancel_token):
                    captured["entrypoint"] = "request_permissions"
                    captured["parent_ctx"] = parent_ctx
                    captured["call_id"] = call_id
                    captured["args"] = args
                    captured["cancel_token"] = cancel_token
                    return RequestPermissionsResponse(
                        permissions=args.permissions,
                        scope=PermissionGrantScope.TURN,
                    )

                async def request_permissions_for_cwd(self, parent_ctx, call_id, args, request_cwd, cancel_token):
                    captured["entrypoint"] = "request_permissions_for_cwd"
                    return RequestPermissionsResponse(
                        permissions=args.permissions,
                        scope=PermissionGrantScope.SESSION,
                    )

            turn = SimpleNamespace(cwd=cwd)
            cancel_token = object()
            invocation = ToolInvocation(
                session=Session(),
                turn=turn,
                cancellation_token=cancel_token,
                tracker=None,
                call_id="call-rust-session",
                tool_name=REQUEST_PERMISSIONS_TOOL_NAME,
                source=ToolCallSource.direct(),
                payload=ToolPayload.function(network_args_json()),
            )
            output = asyncio.run(RequestPermissionsHandler().handle(invocation))

        self.assertEqual(captured["entrypoint"], "request_permissions")
        self.assertIs(captured["parent_ctx"], turn)
        self.assertEqual(captured["call_id"], "call-rust-session")
        self.assertEqual(captured["args"].permissions, request_profile_with_network())
        self.assertIs(captured["cancel_token"], cancel_token)
        self.assertEqual(
            json.loads(output.into_text()),
            {
                "permissions": {"network": {"enabled": True}},
                "scope": "turn",
            },
        )

    def test_handler_uses_invocation_session_when_callback_missing_like_rust(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            captured = {}

            class Session:
                async def request_permissions_for_cwd(self, parent_ctx, call_id, args, request_cwd, cancel_token):
                    captured["parent_ctx"] = parent_ctx
                    captured["call_id"] = call_id
                    captured["args"] = args
                    captured["cwd"] = request_cwd
                    captured["cancel_token"] = cancel_token
                    return RequestPermissionsResponse(
                        permissions=args.permissions,
                        scope=PermissionGrantScope.SESSION,
                    )

            turn = SimpleNamespace(cwd=cwd)
            cancel_token = object()
            invocation = ToolInvocation(
                session=Session(),
                turn=turn,
                cancellation_token=cancel_token,
                tracker=None,
                call_id="call-from-session",
                tool_name=REQUEST_PERMISSIONS_TOOL_NAME,
                source=ToolCallSource.direct(),
                payload=ToolPayload.function(network_args_json()),
            )
            output = asyncio.run(RequestPermissionsHandler().handle(invocation))

        self.assertIs(captured["parent_ctx"], turn)
        self.assertEqual(captured["call_id"], "call-from-session")
        self.assertEqual(captured["args"].permissions, request_profile_with_network())
        self.assertEqual(captured["cwd"], cwd)
        self.assertIs(captured["cancel_token"], cancel_token)
        self.assertEqual(
            json.loads(output.into_text()),
            {
                "permissions": {"network": {"enabled": True}},
                "scope": "session",
            },
        )

    def test_router_passes_session_turn_and_cancellation_to_request_permissions_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            captured = {}

            class Session:
                async def request_permissions_for_cwd(self, parent_ctx, call_id, args, request_cwd, cancel_token):
                    captured["parent_ctx"] = parent_ctx
                    captured["call_id"] = call_id
                    captured["args"] = args
                    captured["cwd"] = request_cwd
                    captured["cancel_token"] = cancel_token
                    return RequestPermissionsResponse(
                        permissions=args.permissions,
                        scope=PermissionGrantScope.TURN,
                    )

            turn = SimpleNamespace(cwd=cwd)
            cancel_token = object()
            router = ToolRouter.from_parts(ToolRegistry.with_handler_for_test(RequestPermissionsHandler()))
            result = asyncio.run(
                router.dispatch_tool_call_with_terminal_outcome(
                    ToolCall(
                        tool_name=ToolName.plain(REQUEST_PERMISSIONS_TOOL_NAME),
                        call_id="call-router",
                        payload=ToolPayload.function(network_args_json()),
                    ),
                    session=Session(),
                    turn=turn,
                    cancellation_token=cancel_token,
                )
            )

        self.assertIs(captured["parent_ctx"], turn)
        self.assertEqual(captured["call_id"], "call-router")
        self.assertEqual(captured["args"].permissions, request_profile_with_network())
        self.assertEqual(captured["cwd"], cwd)
        self.assertIs(captured["cancel_token"], cancel_token)
        self.assertEqual(
            json.loads(result.result.into_text()),
            {
                "permissions": {"network": {"enabled": True}},
                "scope": "turn",
            },
        )

    def test_handler_maps_async_session_none_response_to_cancelled_error_like_rust(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)

            class Session:
                async def request_permissions_for_cwd(self, parent_ctx, call_id, args, request_cwd, cancel_token):
                    return None

            invocation = ToolInvocation(
                session=Session(),
                turn=SimpleNamespace(cwd=cwd),
                cancellation_token=None,
                tracker=None,
                call_id="call-cancelled",
                tool_name=REQUEST_PERMISSIONS_TOOL_NAME,
                source=ToolCallSource.direct(),
                payload=ToolPayload.function(network_args_json()),
            )

            with self.assertRaisesRegex(
                FunctionCallError,
                "request_permissions was cancelled before receiving a response",
            ):
                asyncio.run(RequestPermissionsHandler().handle(invocation))

    def test_handler_normalizes_response_to_requested_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            requested_child = cwd / "child"

            def callback(call_id, args):
                return RequestPermissionsResponse(
                    permissions=RequestPermissionProfile(
                        network=NetworkPermissions(enabled=True),
                        file_system=FileSystemPermissions.from_read_write_roots(None, (cwd,)),
                    ),
                    scope=PermissionGrantScope.SESSION,
                )

            handler = RequestPermissionsHandler(callback)
            output = handler.handle(
                ToolPayload.function(
                    json.dumps(
                        {
                            "permissions": {
                                "network": {"enabled": True},
                                "file_system": {"write": [str(requested_child)]},
                            }
                        }
                    )
                ),
                call_id="call-1",
                cwd=cwd,
            )

        self.assertEqual(
            json.loads(output.into_text()),
            {
                "permissions": {"network": {"enabled": True}},
                "scope": "session",
            },
        )

    def test_handler_rejects_strict_auto_review_session_scope_response(self) -> None:
        def callback(call_id, args):
            return RequestPermissionsResponse(
                permissions=args.permissions,
                scope=PermissionGrantScope.SESSION,
                strict_auto_review=True,
            )

        handler = RequestPermissionsHandler(callback)
        output = handler.handle(ToolPayload.function(network_args_json()), call_id="call-1")

        self.assertEqual(
            json.loads(output.into_text()),
            {
                "permissions": {},
                "scope": "turn",
            },
        )

    def test_handler_rejects_empty_cancelled_and_bad_payloads(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/request_permissions.rs
        # Rust contract: unsupported payloads, empty permission requests, bad JSON, and cancelled responses are model-visible errors.
        handler = RequestPermissionsHandler()

        with self.assertRaises(FunctionCallError):
            handler.handle(ToolPayload.custom("raw"))
        with self.assertRaises(FunctionCallError):
            handler.handle(ToolPayload.function("{not json"))
        with self.assertRaises(FunctionCallError):
            handler.handle(
                ToolPayload.function(
                    json.dumps({"permissions": {}, "reason": "empty"})
                )
            )
        with self.assertRaises(FunctionCallError):
            handler.handle(ToolPayload.function(network_args_json()))
        with self.assertRaises(TypeError):
            handler.matches_kind(object())
        with self.assertRaises(TypeError):
            RequestPermissionsHandler(request_callback=object())
        with self.assertRaises(TypeError):
            parse_request_permissions_arguments({})
        with self.assertRaises(TypeError):
            create_request_permissions_tool(1)

    def test_normalize_boundary_requires_args(self) -> None:
        from pycodex.core.tools.handlers.request_permissions import normalize_request_permissions_args

        args = RequestPermissionsArgs(RequestPermissionProfile())

        self.assertIs(normalize_request_permissions_args(args), args)
        self.assertIs(normalize_request_permission_paths(args), args)
        with self.assertRaises(TypeError):
            normalize_request_permissions_args({})
        with self.assertRaises(TypeError):
            normalize_request_permission_paths({})

    def test_normalize_request_permissions_args_matches_rust_empty_and_entry_rules(self) -> None:
        from pycodex.core.tools.handlers.request_permissions import normalize_request_permissions_args

        duplicate = FileSystemSandboxEntry(
            FileSystemPath.explicit_path(Path.cwd() / "out"),
            FileSystemAccessMode.WRITE,
        )
        args = RequestPermissionsArgs(
            RequestPermissionProfile(
                network=NetworkPermissions(),
                file_system=FileSystemPermissions(entries=(duplicate, duplicate)),
            ),
            reason="Need output",
        )

        normalized = normalize_request_permissions_args(args)

        self.assertIsNone(normalized.permissions.network)
        self.assertEqual(normalized.permissions.file_system.entries, (duplicate,))
        self.assertEqual(normalized.reason, "Need output")

        empty = normalize_request_permissions_args(
            RequestPermissionsArgs(
                RequestPermissionProfile(
                    network=NetworkPermissions(),
                    file_system=FileSystemPermissions(),
                )
            )
        )
        self.assertTrue(empty.permissions.is_empty())

        with self.assertRaisesRegex(FunctionCallError, "glob file system permissions only support deny-read entries"):
            normalize_request_permissions_args(
                RequestPermissionsArgs(
                    RequestPermissionProfile(
                        file_system=FileSystemPermissions(
                            entries=(
                                FileSystemSandboxEntry(
                                    FileSystemPath.glob_pattern("src/**/*.py"),
                                    FileSystemAccessMode.READ,
                                ),
                            )
                        )
                    )
                )
            )

    def test_normalize_request_permissions_args_preserves_deny_globs_and_special_paths(self) -> None:
        from pycodex.core.tools.handlers.request_permissions import normalize_request_permissions_args

        glob_entry = FileSystemSandboxEntry(
            FileSystemPath.glob_pattern("src/**/*.secret"),
            FileSystemAccessMode.DENY,
        )
        special_entry = FileSystemSandboxEntry(
            FileSystemPath.special(FileSystemSpecialPath.project_roots(Path(".codex"))),
            FileSystemAccessMode.READ,
        )
        args = RequestPermissionsArgs(
            RequestPermissionProfile(
                file_system=FileSystemPermissions(entries=(glob_entry, special_entry))
            )
        )

        normalized = normalize_request_permissions_args(args)

        self.assertEqual(
            normalized.permissions.file_system.entries,
            (glob_entry, special_entry),
        )

    def test_normalize_request_permissions_args_canonicalizes_plain_paths(self) -> None:
        from pycodex.core.tools.handlers.request_permissions import normalize_request_permissions_args

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            target = base / "target"
            target.mkdir()
            logical = base / "target" / ".." / "target"
            args = RequestPermissionsArgs(
                RequestPermissionProfile(
                    file_system=FileSystemPermissions(
                        entries=(
                            FileSystemSandboxEntry(
                                FileSystemPath.explicit_path(logical),
                                FileSystemAccessMode.WRITE,
                            ),
                        )
                    )
                )
            )

            normalized = normalize_request_permissions_args(args)

            self.assertEqual(
                normalized.permissions.file_system.entries,
                (
                    FileSystemSandboxEntry(
                        FileSystemPath.explicit_path(target.resolve(strict=False)),
                        FileSystemAccessMode.WRITE,
                    ),
                ),
            )

    def test_normalize_request_permissions_args_deduplicates_after_canonicalization(self) -> None:
        from pycodex.core.tools.handlers.request_permissions import normalize_request_permissions_args

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            target = base / "target"
            target.mkdir()
            logical = base / "target" / ".." / "target"
            args = RequestPermissionsArgs(
                RequestPermissionProfile(
                    file_system=FileSystemPermissions(
                        entries=(
                            FileSystemSandboxEntry(
                                FileSystemPath.explicit_path(target),
                                FileSystemAccessMode.WRITE,
                            ),
                            FileSystemSandboxEntry(
                                FileSystemPath.explicit_path(logical),
                                FileSystemAccessMode.WRITE,
                            ),
                        )
                    )
                )
            )

            normalized = normalize_request_permissions_args(args)

            self.assertEqual(
                normalized.permissions.file_system.entries,
                (
                    FileSystemSandboxEntry(
                        FileSystemPath.explicit_path(target.resolve(strict=False)),
                        FileSystemAccessMode.WRITE,
                    ),
                ),
            )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support is required")
    def test_normalize_request_permissions_args_preserves_nested_symlink_logical_path(self) -> None:
        from pycodex.core.tools.handlers.request_permissions import normalize_request_permissions_args

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            real = base / "real"
            real.mkdir()
            link = base / "link"
            try:
                os.symlink(real, link, target_is_directory=True)
            except (OSError, NotImplementedError) as err:
                self.skipTest(f"symlink creation unavailable: {err}")
            logical_missing_child = link / "missing.txt"
            args = RequestPermissionsArgs(
                RequestPermissionProfile(
                    file_system=FileSystemPermissions(
                        entries=(
                            FileSystemSandboxEntry(
                                FileSystemPath.explicit_path(logical_missing_child),
                                FileSystemAccessMode.READ,
                            ),
                        )
                    )
                )
            )

            normalized = normalize_request_permissions_args(args)

            self.assertEqual(
                normalized.permissions.file_system.entries,
                (
                    FileSystemSandboxEntry(
                        FileSystemPath.explicit_path(logical_missing_child),
                        FileSystemAccessMode.READ,
                    ),
                ),
            )


if __name__ == "__main__":
    unittest.main()
