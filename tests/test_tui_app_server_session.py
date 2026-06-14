import asyncio
from dataclasses import dataclass
from pathlib import Path

from pycodex.tui.app_server_session import (
    JSONRPC_INVALID_REQUEST,
    JSONRPC_METHOD_NOT_FOUND,
    THREAD_SETTINGS_UPDATE_METHOD,
    AppServerSession,
    ThreadParamsMode,
    TurnPermissionsOverride,
    config_request_overrides_from_config,
    is_thread_settings_update_unsupported,
    model_preset_from_api_model,
    permissions_selection_from_config,
    sandbox_mode_from_permission_profile,
    status_account_display_from_auth_mode,
    thread_cwd_from_config,
    thread_fork_params_from_config,
    thread_resume_params_from_config,
    thread_start_params_from_config,
    turn_permissions_overrides,
)


@dataclass
class Config:
    cwd: Path = Path("/repo")
    model_provider_id: str = "openai"
    permission_profile: object = "workspace_write"
    active_profile: object = "default"
    model_reasoning_effort: str | None = None
    model_reasoning_summary: str | None = None
    model_verbosity: str | None = None
    personality: str | None = None
    web_search: bool | None = None
    model_service_tier: str | None = None
    bypass_hook_trust: bool = False


class Client:
    def __init__(self):
        self.requests = []
        self._events = ["event"]

    def server_version(self):
        return "1.2.3"

    def request_handle(self):
        return self

    async def request_typed(self, request):
        self.requests.append(request)
        return {"ok": request["type"]}

    async def next_event(self):
        return self._events.pop(0)


def test_thread_settings_update_unsupported_matches_jsonrpc_compatibility_cases():
    assert is_thread_settings_update_unsupported({"code": JSONRPC_METHOD_NOT_FOUND, "message": "missing"})
    assert is_thread_settings_update_unsupported(
        {
            "error": {
                "code": JSONRPC_INVALID_REQUEST,
                "message": f"unknown method {THREAD_SETTINGS_UPDATE_METHOD}",
            }
        }
    )
    assert not is_thread_settings_update_unsupported({"code": JSONRPC_INVALID_REQUEST, "message": "other"})


def test_session_request_facade_uses_incrementing_request_ids_and_delegates_events():
    async def run():
        client = Client()
        session = AppServerSession.new(client, ThreadParamsMode.Remote).with_remote_cwd_override("/remote")

        assert session.uses_remote_workspace()
        assert session.remote_cwd_override() == "/remote"
        assert session.server_version() == "1.2.3"
        assert await session.read_account() == {"ok": "GetAccount"}
        assert await session.external_agent_config_detect({"scan": True}) == {"ok": "ExternalAgentConfigDetect"}
        assert await session.external_agent_config_import(["item"]) == {"ok": "ExternalAgentConfigImport"}
        assert await session.next_event() == "event"

        assert [request["request_id"] for request in client.requests] == [1, 2, 3]
        assert client.requests[0]["params"] == {"refresh_token": False}
        assert client.requests[1]["params"] == {"params": {"scan": True}}
        assert client.requests[2]["params"] == {"migration_items": ["item"]}

    asyncio.run(run())


def test_status_account_display_remaps_plan_labels():
    assert status_account_display_from_auth_mode("ApiKey") == "ApiKey"
    assert status_account_display_from_auth_mode("ChatGPT", "EnterpriseCbpUsageBased") == "Enterprise"
    assert status_account_display_from_auth_mode("ChatGPT", "SelfServeBusinessUsageBased") == "Business"
    assert status_account_display_from_auth_mode("ChatGPT", "Pro") == "Pro"


def test_model_preset_from_api_model_copies_semantic_model_fields():
    preset = model_preset_from_api_model(
        {
            "id": "gpt-5",
            "display_name": "GPT-5",
            "is_default": True,
            "service_tier": "auto",
        }
    )
    assert preset == {
        "model": "gpt-5",
        "name": "GPT-5",
        "is_default": True,
        "service_tier": "auto",
    }


def test_config_request_overrides_preserve_implicit_personality_default():
    assert "personality" not in config_request_overrides_from_config(Config())
    overrides = config_request_overrides_from_config(
        Config(
            model_reasoning_effort="high",
            model_reasoning_summary="auto",
            model_verbosity="low",
            personality="none",
            web_search=True,
            bypass_hook_trust=True,
        )
    )
    assert overrides == {
        "model_reasoning_effort": "high",
        "model_reasoning_summary": "auto",
        "model_verbosity": "low",
        "personality": "none",
        "web_search": True,
        "bypass_hook_trust": True,
    }


def test_thread_lifecycle_params_include_cwd_for_embedded_and_omit_remote_without_override():
    embedded = thread_start_params_from_config(
        Config(model_service_tier="flex"),
        ThreadParamsMode.Embedded,
        session_start_source="clear",
    )
    assert embedded.cwd == "/repo"
    assert embedded.model_provider == "openai"
    assert embedded.sandbox == "WorkspaceWrite"
    assert embedded.permissions == {"active_profile_id": "default"}
    assert embedded.service_tier == "flex"
    assert embedded.thread_source == "clear"

    remote = thread_start_params_from_config(Config(), ThreadParamsMode.Remote)
    assert remote.cwd is None
    assert remote.model_provider is None
    assert remote.permissions is None

    remote_with_override = thread_start_params_from_config(Config(), ThreadParamsMode.Remote, "/workspace")
    assert remote_with_override.cwd == "/workspace"


def test_resume_and_fork_params_forward_ids_and_instruction_overrides():
    resumed = thread_resume_params_from_config(Config(), "thread-1", ThreadParamsMode.Embedded)
    assert resumed.thread_id == "thread-1"

    forked = thread_fork_params_from_config(
        Config(),
        "source-thread",
        ThreadParamsMode.Remote,
        "/remote",
        base_instructions="base",
        developer_instructions="dev",
    )
    assert forked.source_thread_id == "source-thread"
    assert forked.cwd == "/remote"
    assert forked.base_instructions == "base"
    assert forked.developer_instructions == "dev"


def test_permissions_and_sandbox_projection_semantics():
    assert sandbox_mode_from_permission_profile("read_only", "/repo") == "ReadOnly"
    assert sandbox_mode_from_permission_profile("danger_full_access", "/repo") == "DangerFullAccess"
    assert sandbox_mode_from_permission_profile({"writable_roots": ["/repo"]}, "/repo") == "WorkspaceWrite"
    assert sandbox_mode_from_permission_profile({"writable_roots": ["/other"]}, "/repo") == "ReadOnly"

    assert turn_permissions_overrides(Config(), ThreadParamsMode.Embedded) == TurnPermissionsOverride.ActiveProfile("default")
    assert turn_permissions_overrides(Config(), ThreadParamsMode.Remote) == TurnPermissionsOverride.Preserve()
    assert permissions_selection_from_config(Config(), ThreadParamsMode.Embedded) == {"active_profile_id": "default"}
    assert permissions_selection_from_config(Config(), ThreadParamsMode.Remote) is None


def test_thread_cwd_from_config_matches_remote_workspace_rules():
    assert thread_cwd_from_config(Config(), ThreadParamsMode.Embedded) == "/repo"
    assert thread_cwd_from_config(Config(), ThreadParamsMode.Remote) is None
    assert thread_cwd_from_config(Config(), ThreadParamsMode.Remote, "/remote") == "/remote"
