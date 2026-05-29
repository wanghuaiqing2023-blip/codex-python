import json
import unittest
from pathlib import Path

from pycodex.core import (
    REQUEST_PERMISSIONS_TOOL_NAME,
    FunctionCallError,
    RequestPermissionsHandler,
    ToolPayload,
    create_request_permissions_tool,
    normalize_request_permission_paths,
    parse_request_permissions_arguments,
    request_profile_with_file_system,
    request_permissions_tool_description,
    request_profile_with_network,
)
from pycodex.protocol import (
    PermissionGrantScope,
    RequestPermissionProfile,
    RequestPermissionsArgs,
    RequestPermissionsResponse,
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
        description = request_permissions_tool_description()
        spec = create_request_permissions_tool(description)

        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], REQUEST_PERMISSIONS_TOOL_NAME)
        self.assertEqual(spec["description"], description)
        self.assertFalse(spec["strict"])
        self.assertEqual(spec["parameters"]["required"], ["permissions"])
        self.assertFalse(spec["parameters"]["additionalProperties"])
        permissions = spec["parameters"]["properties"]["permissions"]
        self.assertIn("network", permissions["properties"])
        self.assertIn("file_system", permissions["properties"])

    def test_parse_request_permissions_arguments(self) -> None:
        args = parse_request_permissions_arguments(network_args_json())

        self.assertEqual(args.reason, "Need network")
        self.assertEqual(args.permissions, request_profile_with_network())

    def test_parse_request_permissions_arguments_resolves_relative_paths_from_cwd(self) -> None:
        args = parse_request_permissions_arguments(
            json.dumps(
                {
                    "permissions": {
                        "file_system": {
                            "read": ["relative/input.txt", "/already/absolute"],
                            "write": ["out"],
                        }
                    }
                }
            ),
            cwd=Path("/workspace"),
        )

        self.assertEqual(
            args.permissions,
            request_profile_with_file_system(
                read=(Path("/workspace/relative/input.txt"), Path("/already/absolute")),
                write=(Path("/workspace/out"),),
            ),
        )

        with self.assertRaisesRegex(FunctionCallError, "cwd must be an absolute path"):
            parse_request_permissions_arguments(
                json.dumps({"permissions": {"file_system": {"read": ["relative"]}}}),
                cwd=Path("workspace"),
            )

    def test_handler_requests_permissions_and_serializes_response(self) -> None:
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
        self.assertEqual(captured["call_id"], "call-1")
        self.assertEqual(captured["args"].permissions, request_profile_with_network())
        self.assertEqual(
            json.loads(output.into_text()),
            {
                "permissions": {"network": {"enabled": True}},
                "scope": "session",
            },
        )

    def test_handler_rejects_empty_cancelled_and_bad_payloads(self) -> None:
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
        from pycodex.core import normalize_request_permissions_args

        args = RequestPermissionsArgs(RequestPermissionProfile())

        self.assertIs(normalize_request_permissions_args(args), args)
        self.assertIs(normalize_request_permission_paths(args), args)
        with self.assertRaises(TypeError):
            normalize_request_permissions_args({})
        with self.assertRaises(TypeError):
            normalize_request_permission_paths({})


if __name__ == "__main__":
    unittest.main()
