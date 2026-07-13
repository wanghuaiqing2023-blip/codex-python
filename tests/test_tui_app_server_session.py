import asyncio
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from pycodex.config.types import History
from pycodex.message_history import HistoryConfig, append_entry
from pycodex.tui.app_server_session import (
    JSONRPC_INVALID_REQUEST,
    JSONRPC_METHOD_NOT_FOUND,
    THREAD_SETTINGS_UPDATE_METHOD,
    AppServerSession,
    app_server_rate_limit_snapshots,
    display_permission_profile_from_thread_response,
    rate_limit_snapshot,
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
    thread_session_state_from_thread_response,
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
        if request["type"] == "GetAccount":
            return {"account": {"kind": "ChatGPT", "email": "dev@openai.com", "plan_type": "EnterpriseCbpUsageBased"}, "requires_openai_auth": True}
        if request["type"] == "ModelList":
            return {"data": [{"id": "gpt-5", "display_name": "GPT-5", "is_default": True}]}
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
        assert await session.read_account() == {
            "account": {"kind": "ChatGPT", "email": "dev@openai.com", "plan_type": "EnterpriseCbpUsageBased"},
            "requires_openai_auth": True,
        }
        assert await session.external_agent_config_detect({"scan": True}) == {"ok": "ExternalAgentConfigDetect"}
        assert await session.external_agent_config_import(["item"]) == {"ok": "ExternalAgentConfigImport"}
        assert await session.next_event() == "event"

        assert [request["request_id"] for request in client.requests] == [1, 2, 3]
        assert client.requests[0]["params"] == {"refresh_token": False}
        assert client.requests[1]["params"] == {"params": {"scan": True}}
        assert client.requests[2]["params"] == {"migration_items": ["item"]}

    asyncio.run(run())


def test_bootstrap_reads_account_and_models_into_bootstrap_state():
    async def run():
        session = AppServerSession.new(Client(), ThreadParamsMode.Embedded)
        bootstrap = await session.bootstrap(Config())
        assert bootstrap.account_email == "dev@openai.com"
        assert bootstrap.status_account_display == "Enterprise"
        assert bootstrap.requires_openai_auth is True
        assert bootstrap.feedback_audience == "OpenAiEmployee"
        assert bootstrap.default_model == "gpt-5"
        assert bootstrap.available_models == [{"model": "gpt-5", "name": "GPT-5", "is_default": True}]

    asyncio.run(run())


def test_remaining_rpc_facade_methods_send_typed_requests():
    async def run():
        client = Client()
        session = AppServerSession.new(client, ThreadParamsMode.Embedded)

        await session.thread_list({"limit": 2})
        await session.thread_read("thread-1")
        await session.thread_metadata_update_branch({"thread_id": "thread-1", "git": {"branch": "main"}})
        await session.thread_settings_update({"thread_id": "thread-1", "model": "gpt-5"})
        await session.thread_inject_items({"thread_id": "thread-1", "items": []})
        await session.turn_start({"thread_id": "thread-1", "input": []})
        await session.turn_interrupt({"thread_id": "thread-1", "turn_id": "turn-1"})
        await session.startup_interrupt({"thread_id": "thread-1"})
        await session.turn_steer({"thread_id": "thread-1", "turn_id": "turn-1", "input": []})
        await session.thread_set_name({"thread_id": "thread-1", "name": "demo"})
        await session.thread_memory_mode_set({"thread_id": "thread-1", "mode": "auto"})
        await session.memory_reset({})
        await session.thread_goal_get({"thread_id": "thread-1"})
        await session.thread_goal_set({"thread_id": "thread-1", "goal": "ship"})
        await session.thread_goal_clear({"thread_id": "thread-1"})
        await session.logout_account({})
        await session.thread_unsubscribe("thread-1")
        await session.thread_compact_start({"thread_id": "thread-1"})
        await session.thread_shell_command({"thread_id": "thread-1", "command": "ls"})
        await session.thread_approve_guardian_denied_action({"thread_id": "thread-1"})
        await session.thread_background_terminals_clean({"thread_id": "thread-1"})
        await session.thread_rollback({"thread_id": "thread-1", "turn_id": "turn-1"})
        await session.review_start({"target": "diff"})
        await session.skills_list({})
        await session.reload_user_config({})
        await session.thread_realtime_start({"thread_id": "thread-1"})
        await session.thread_realtime_audio({"thread_id": "thread-1", "chunk": "abc"})
        await session.thread_realtime_stop({"thread_id": "thread-1"})

        request_types = [request["type"] for request in client.requests]
        assert request_types == [
            "ThreadList",
            "ThreadRead",
            "ThreadMetadataUpdate",
            "ThreadSettingsUpdate",
            "ThreadInjectItems",
            "TurnStart",
            "TurnInterrupt",
            "TurnInterrupt",
            "TurnSteer",
            "ThreadSetName",
            "ThreadMemoryModeSet",
            "MemoryReset",
            "ThreadGoalGet",
            "ThreadGoalSet",
            "ThreadGoalClear",
            "LogoutAccount",
            "ThreadUnsubscribe",
            "ThreadCompactStart",
            "ThreadShellCommand",
            "ThreadApproveGuardianDeniedAction",
            "ThreadBackgroundTerminalsClean",
            "ThreadRollback",
            "ReviewStart",
            "SkillsList",
            "ConfigReload",
            "ThreadRealtimeStart",
            "ThreadRealtimeAppendAudio",
            "ThreadRealtimeStop",
        ]
        assert client.requests[1]["params"] == {"thread_id": "thread-1"}
        assert client.requests[16]["params"] == {"thread_id": "thread-1"}

    asyncio.run(run())


def test_thread_response_and_rate_limit_helpers_are_semantic_mappings():
    session_state = asyncio.run(
        thread_session_state_from_thread_response(
            {
                "id": "thread-1",
                "session_id": "session-1",
                "forked_from_id": "parent",
                "name": "demo",
                "cwd": "/repo",
                "sandbox": "workspace_write",
                "runtime_workspace_roots": ["/repo"],
                "instruction_sources": ["/repo/AGENTS.md"],
            },
            config=Config(permission_profile="read_only"),
            mode=ThreadParamsMode.Remote,
        )
    )
    assert session_state["thread_id"] == "thread-1"
    assert session_state["permission_profile"] == "WorkspaceWrite"
    assert session_state["runtime_workspace_roots"] == ["/repo"]

    assert display_permission_profile_from_thread_response("danger_full_access", "/repo", Config(permission_profile="read_only"), ThreadParamsMode.Embedded) == "read_only"
    assert rate_limit_snapshot(limit=1) == {"limit": 1}
    # Rust owner/test:
    # codex-tui::app_server_session::tests::
    # app_server_rate_limit_snapshots_deduplicates_top_level_limit_from_map.
    assert app_server_rate_limit_snapshots(
        {
            "rate_limits": {"limit_id": "codex", "used": 1},
            "rate_limits_by_limit_id": {
                "codex": {"limit_id": "codex", "used": 1},
                "other": {"limit_id": "other", "used": 2},
            },
        }
    ) == [
        {"limit_id": "codex", "used": 1},
        {"limit_id": "other", "used": 2},
    ]


def test_thread_response_populates_history_metadata_from_config(tmp_path):
    # Rust test:
    # codex-tui::app_server_session::tests::session_configured_populates_history_metadata.
    config = SimpleNamespace(
        codex_home=tmp_path,
        history=History(),
        cwd=tmp_path,
        permission_profile="read_only",
    )
    history_config = HistoryConfig.new(tmp_path, config.history)
    asyncio.run(append_entry("older", "thread-1", history_config))
    asyncio.run(append_entry("newer", "thread-1", history_config))

    session_state = asyncio.run(
        thread_session_state_from_thread_response(
            {
                "id": "thread-1",
                "cwd": str(tmp_path),
                "sandbox": "read_only",
            },
            config=config,
            mode=ThreadParamsMode.Embedded,
        )
    )

    metadata = session_state["message_history"]
    assert metadata["log_id"] != 0
    assert metadata["entry_count"] == 2


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
