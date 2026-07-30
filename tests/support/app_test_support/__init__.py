from __future__ import annotations

from .analytics_server import AnalyticsEventsServer, start_analytics_events_server
from .auth_fixtures import (
    ChatGptAuthFixture,
    ChatGptIdTokenClaims,
    encode_id_token,
    write_chatgpt_auth,
)
from .config import (
    write_mock_responses_config_toml,
    write_mock_responses_config_toml_with_chatgpt_base_url,
)
from .mcp_process import (
    DEFAULT_CLIENT_NAME,
    DISABLE_PLUGIN_STARTUP_TASKS_ARG,
    McpProcess,
)
from .mock_model_server import (
    MockResponsesServer,
    create_mock_responses_server_repeating_assistant,
    create_mock_responses_server_sequence,
    create_mock_responses_server_sequence_unchecked,
)
from .models_cache import write_models_cache, write_models_cache_with_models
from .responses import (
    create_apply_patch_sse_response,
    create_exec_command_sse_response,
    create_final_assistant_message_sse_response,
    create_request_permissions_sse_response,
    create_request_user_input_sse_response,
    create_shell_command_sse_response,
)
from .rollout import (
    create_fake_rollout,
    create_fake_rollout_with_source,
    create_fake_rollout_with_text_elements,
    create_fake_rollout_with_token_usage,
    rollout_path,
)


def to_response(response: dict[str, object]) -> object:
    return response.get("result")


__all__ = [
    "AnalyticsEventsServer",
    "ChatGptAuthFixture",
    "ChatGptIdTokenClaims",
    "DEFAULT_CLIENT_NAME",
    "DISABLE_PLUGIN_STARTUP_TASKS_ARG",
    "McpProcess",
    "MockResponsesServer",
    "create_apply_patch_sse_response",
    "create_exec_command_sse_response",
    "create_fake_rollout",
    "create_fake_rollout_with_source",
    "create_fake_rollout_with_text_elements",
    "create_fake_rollout_with_token_usage",
    "create_final_assistant_message_sse_response",
    "create_mock_responses_server_repeating_assistant",
    "create_mock_responses_server_sequence",
    "create_mock_responses_server_sequence_unchecked",
    "create_request_permissions_sse_response",
    "create_request_user_input_sse_response",
    "create_shell_command_sse_response",
    "encode_id_token",
    "rollout_path",
    "start_analytics_events_server",
    "to_response",
    "write_chatgpt_auth",
    "write_mock_responses_config_toml",
    "write_mock_responses_config_toml_with_chatgpt_base_url",
    "write_models_cache",
    "write_models_cache_with_models",
]
