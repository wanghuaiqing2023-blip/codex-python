from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from pycodex.protocol import McpInvocation
from pycodex.rmcp_client import (
    DEFAULT_MCP_SERVER_ENVIRONMENT_ID,
    MCP_SANDBOX_STATE_META_CAPABILITY,
    REMOTE_MCP_ENVIRONMENT,
    TEXT_ONLY_IMAGE_OMISSION_TEXT,
    StoredOAuthTokens,
    WrappedOAuthTokenResponse,
    delete_oauth_tokens,
    determine_streamable_http_auth_status,
    echo_tool_result,
    image_result_from_data_url,
    load_oauth_tokens,
    mcp_call_begin_event,
    mcp_call_end_event,
    mcp_namespace,
    read_fallback_oauth_tokens,
    remote_aware_environment_id,
    resolved_env_value,
    responses_output_from_mcp_result,
    sandbox_state_meta,
    save_oauth_tokens,
    select_stdio_cwd,
    should_run_mcp_tool_calls_concurrently,
    streamable_http_metadata_url,
    sync_tool_result,
    unwrap_mcp_output,
    wrap_mcp_output,
    write_fallback_oauth_tokens,
)


OPENAI_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
)


class RmcpClientSuiteParityTests(unittest.TestCase):
    def test_stdio_server_round_trip(self) -> None:
        # Rust source: core/tests/suite/rmcp_client.rs::stdio_server_round_trip
        namespace = mcp_namespace("rmcp")
        begin = mcp_call_begin_event("call-123", "rmcp", "echo", {"message": "ping"})
        result = echo_tool_result("ping", "propagated-env")
        end = mcp_call_end_event("call-123", "rmcp", "echo", result, {"message": "ping"})

        self.assertEqual(namespace, "mcp__rmcp")
        self.assertEqual(begin.invocation, McpInvocation("rmcp", "echo", {"message": "ping"}))
        self.assertFalse(end.result.is_error)
        self.assertEqual(end.result.content, ())
        self.assertEqual(end.result.structured_content, {"echo": "ECHOING: ping", "env": "propagated-env"})
        self.assertEqual(unwrap_mcp_output(wrap_mcp_output(end.result.structured_content)), end.result.structured_content)

    def test_stdio_server_uses_configured_cwd_before_runtime_fallback(self) -> None:
        # Rust source: core/tests/suite/rmcp_client.rs::stdio_server_uses_configured_cwd_before_runtime_fallback
        self.assertEqual(select_stdio_cwd("C:/repo/mcp-configured-cwd", "C:/repo"), Path("C:/repo/mcp-configured-cwd"))

    def test_local_stdio_server_uses_runtime_fallback_cwd_when_config_omits_cwd(self) -> None:
        # Rust source: core/tests/suite/rmcp_client.rs::local_stdio_server_uses_runtime_fallback_cwd_when_config_omits_cwd
        self.assertEqual(select_stdio_cwd(None, "C:/repo"), Path("C:/repo"))

    def test_stdio_mcp_tool_call_includes_sandbox_state_meta(self) -> None:
        # Rust source: core/tests/suite/rmcp_client.rs::stdio_mcp_tool_call_includes_sandbox_state_meta
        meta = sandbox_state_meta({"mode": "read-only"}, "C:/repo")

        self.assertEqual(
            meta[MCP_SANDBOX_STATE_META_CAPABILITY],
            {"sandboxPolicy": {"mode": "read-only"}, "sandboxCwd": "C:/repo", "useLegacyLandlock": False},
        )

    def test_stdio_mcp_parallel_tool_calls_default_false_runs_serially(self) -> None:
        # Rust source: core/tests/suite/rmcp_client.rs::stdio_mcp_parallel_tool_calls_default_false_runs_serially
        self.assertFalse(should_run_mcp_tool_calls_concurrently(supports_parallel_tool_calls=False, tool_read_only=False))
        self.assertEqual(sync_tool_result().structured_content, {"result": "ok"})

    def test_stdio_mcp_read_only_tool_calls_run_concurrently_without_server_opt_in(self) -> None:
        # Rust source: core/tests/suite/rmcp_client.rs::stdio_mcp_read_only_tool_calls_run_concurrently_without_server_opt_in
        self.assertTrue(should_run_mcp_tool_calls_concurrently(supports_parallel_tool_calls=False, tool_read_only=True))

    def test_stdio_mcp_parallel_tool_calls_opt_in_runs_concurrently(self) -> None:
        # Rust source: core/tests/suite/rmcp_client.rs::stdio_mcp_parallel_tool_calls_opt_in_runs_concurrently
        self.assertTrue(should_run_mcp_tool_calls_concurrently(supports_parallel_tool_calls=True, tool_read_only=False))

    def test_stdio_image_responses_round_trip(self) -> None:
        # Rust source: core/tests/suite/rmcp_client.rs::stdio_image_responses_round_trip
        result = image_result_from_data_url(OPENAI_PNG)
        output = responses_output_from_mcp_result(result)

        self.assertFalse(result.is_error)
        self.assertEqual(result.content[0]["type"], "image")
        self.assertEqual(result.content[0]["mimeType"], "image/png")
        self.assertEqual(output[0]["type"], "input_text")
        self.assertEqual(output[1], {"type": "input_image", "image_url": OPENAI_PNG, "detail": "high"})

    def test_stdio_image_responses_preserve_original_detail_metadata(self) -> None:
        # Rust source: core/tests/suite/rmcp_client.rs::stdio_image_responses_preserve_original_detail_metadata
        result = image_result_from_data_url(OPENAI_PNG)
        output = responses_output_from_mcp_result(result, detail="original")

        self.assertEqual(output[1]["detail"], "original")

    def test_stdio_image_responses_are_sanitized_for_text_only_model(self) -> None:
        # Rust source: core/tests/suite/rmcp_client.rs::stdio_image_responses_are_sanitized_for_text_only_model
        result = image_result_from_data_url(OPENAI_PNG)
        output = responses_output_from_mcp_result(result, model_supports_images=False)

        self.assertEqual(unwrap_mcp_output(output), [{"type": "text", "text": TEXT_ONLY_IMAGE_OMISSION_TEXT}])

    def test_stdio_server_propagates_whitelisted_env_vars(self) -> None:
        # Rust source: core/tests/suite/rmcp_client.rs::stdio_server_propagates_whitelisted_env_vars
        value = resolved_env_value(
            "MCP_TEST_VALUE",
            env_vars=("MCP_TEST_VALUE",),
            local_env={"MCP_TEST_VALUE": "propagated-env-from-whitelist"},
        )

        self.assertEqual(value, "propagated-env-from-whitelist")

    def test_stdio_server_propagates_explicit_local_env_var_source(self) -> None:
        # Rust source: core/tests/suite/rmcp_client.rs::stdio_server_propagates_explicit_local_env_var_source
        value = resolved_env_value(
            "MCP_TEST_LOCAL_SOURCE",
            env_vars=({"name": "MCP_TEST_LOCAL_SOURCE", "source": "local"},),
            local_env={"MCP_TEST_LOCAL_SOURCE": "propagated-explicit-local-source"},
            remote_env=True,
        )

        self.assertEqual(value, "propagated-explicit-local-source")

    def test_remote_stdio_env_var_source_does_not_copy_local_env(self) -> None:
        # Rust source: core/tests/suite/rmcp_client.rs::remote_stdio_env_var_source_does_not_copy_local_env
        value = resolved_env_value(
            "MCP_TEST_REMOTE_SOURCE_ONLY",
            env_vars=({"name": "MCP_TEST_REMOTE_SOURCE_ONLY", "source": "remote"},),
            local_env={"MCP_TEST_REMOTE_SOURCE_ONLY": "local-value-should-not-cross"},
            remote_env=True,
        )

        self.assertIsNone(value)
        self.assertEqual(remote_aware_environment_id({}), DEFAULT_MCP_SERVER_ENVIRONMENT_ID)
        self.assertEqual(remote_aware_environment_id({"CODEX_TEST_REMOTE_ENV": "container"}), REMOTE_MCP_ENVIRONMENT)

    def test_streamable_http_tool_call_round_trip(self) -> None:
        # Rust source: core/tests/suite/rmcp_client.rs::streamable_http_tool_call_round_trip
        server_url = "http://127.0.0.1:8080/mcp"
        result = echo_tool_result("ping", "propagated-env-http")

        self.assertEqual(streamable_http_metadata_url(server_url), "http://127.0.0.1:8080/.well-known/oauth-authorization-server/mcp")
        self.assertEqual(result.structured_content["echo"], "ECHOING: ping")
        self.assertEqual(result.structured_content["env"], "propagated-env-http")

    def test_streamable_http_with_oauth_round_trip(self) -> None:
        # Rust source: core/tests/suite/rmcp_client.rs::streamable_http_with_oauth_round_trip
        server_name = "rmcp_http_oauth"
        server_url = "http://127.0.0.1:8080/mcp"
        delete_oauth_tokens(server_name, server_url)

        self.assertEqual(
            asyncio.run(determine_streamable_http_auth_status(server_name, server_url)).value,
            "unauthenticated",
        )
        save_oauth_tokens(server_name, server_url, WrappedOAuthTokenResponse(StoredOAuthTokens("initial-access-token", "initial-refresh-token")))
        self.assertEqual(load_oauth_tokens(server_name, server_url).access_token, "initial-access-token")
        self.assertEqual(
            asyncio.run(determine_streamable_http_auth_status(server_name, server_url)).value,
            "authenticated",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            write_fallback_oauth_tokens(tmpdir, server_name, server_url, "test-client-id", "initial-access-token", "initial-refresh-token")
            loaded = read_fallback_oauth_tokens(tmpdir, server_name, server_url)
        self.assertEqual(loaded, StoredOAuthTokens("initial-access-token", "initial-refresh-token"))


if __name__ == "__main__":
    unittest.main()
