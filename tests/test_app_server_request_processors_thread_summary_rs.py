from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pycodex.app_server.request_processors_thread_summary import (
    extract_conversation_summary,
    summary_to_thread,
    thread_response_active_permission_profile,
    thread_response_sandbox_policy,
    thread_settings_from_config_snapshot,
    thread_settings_from_core_snapshot,
    thread_started_notification,
    with_thread_spawn_agent_metadata,
)
from pycodex.app_server_protocol import SandboxPolicy as ApiSandboxPolicy
from pycodex.app_server_protocol import Thread
from pycodex.app_server_protocol import ThreadStatus
from pycodex.protocol import (
    ActivePermissionProfile,
    AgentPath,
    AskForApproval,
    CollaborationMode,
    GranularApprovalConfig,
    ModeKind,
    NetworkSandboxPolicy,
    PermissionProfile,
    SandboxPolicy,
    SessionSource,
    Settings,
    SubAgentSource,
    ThreadId,
    ThreadSettingsSnapshot,
    USER_MESSAGE_BEGIN,
)


def test_extract_conversation_summary_prefers_plain_user_messages() -> None:
    # Rust source: codex-rs/app-server/src/request_processors/thread_summary_tests.rs
    conversation_id = "3f941c35-29b3-493b-b0a4-e25800d9aeb0"
    timestamp = "2025-09-05T16:53:11.850Z"
    head = [
        {
            "id": conversation_id,
            "timestamp": timestamp,
            "cwd": "/",
            "originator": "codex",
            "cli_version": "0.0.0",
            "model_provider": "test-provider",
        },
        {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "# AGENTS.md instructions for project\n\n<INSTRUCTIONS>\n...\n</INSTRUCTIONS>",
                }
            ],
        },
        {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": f"<prior context> {USER_MESSAGE_BEGIN}Count to 5",
                }
            ],
        },
    ]

    summary = extract_conversation_summary(
        Path("rollout.jsonl"),
        head,
        head[0],
        None,
        "fallback-provider",
        timestamp,
    )

    assert summary is not None
    assert str(summary.conversation_id) == conversation_id
    assert summary.timestamp == timestamp
    assert summary.updated_at == timestamp
    assert summary.preview == "Count to 5"
    assert summary.model_provider == "test-provider"
    assert summary.cwd == Path("/")
    assert summary.cli_version == "0.0.0"
    assert summary.source == SessionSource.vscode()
    assert summary.git_info is None


def test_with_thread_spawn_agent_metadata_only_overlays_thread_spawn() -> None:
    # Rust source: thread_summary.rs::with_thread_spawn_agent_metadata.
    parent = ThreadId.from_string("3f941c35-29b3-493b-b0a4-e25800d9aeb0")
    source = SessionSource.subagent(
        SubAgentSource.thread_spawn(
            parent_thread_id=parent,
            depth=2,
            agent_path=AgentPath.from_string("/root/agents/reviewer"),
            agent_nickname=None,
            agent_role="existing-role",
        )
    )

    updated = with_thread_spawn_agent_metadata(source, "Ada", None)

    assert updated.subagent_source is not None
    assert updated.subagent_source.agent_nickname == "Ada"
    assert updated.subagent_source.agent_role == "existing-role"
    assert updated.subagent_source.agent_path == AgentPath.from_string("/root/agents/reviewer")
    assert with_thread_spawn_agent_metadata(source, None, None) is source
    assert with_thread_spawn_agent_metadata(SessionSource.cli(), "Ada", "reviewer") == SessionSource.cli()


def test_permission_profile_projection_maps_active_and_sandbox_policy() -> None:
    # Rust source: thread_summary.rs::{thread_response_active_permission_profile,thread_response_sandbox_policy}.
    active = ActivePermissionProfile.new(":workspace-write")
    profile = PermissionProfile.workspace_write(network=NetworkSandboxPolicy.ENABLED)

    api_active = thread_response_active_permission_profile(active)
    api_sandbox = thread_response_sandbox_policy(profile, Path("/work/project"))

    assert api_active is not None
    assert api_active.to_mapping() == {"id": ":workspace-write"}
    assert isinstance(api_sandbox, ApiSandboxPolicy)
    assert api_sandbox.type == "workspaceWrite"
    assert api_sandbox.network_access is True


@dataclass(frozen=True)
class _ConfigSnapshot:
    cwd: Path
    approval_policy: object
    approvals_reviewer: object
    permission_profile: PermissionProfile
    active_permission_profile: ActivePermissionProfile | None
    model: str
    model_provider_id: str
    service_tier: str | None
    reasoning_effort: str | None
    reasoning_summary: str | None
    collaboration_mode: object
    personality: str | None


def test_thread_settings_from_config_snapshot_projects_rust_fields() -> None:
    # Rust source: thread_summary.rs::thread_settings_from_config_snapshot.
    snapshot = _ConfigSnapshot(
        cwd=Path("/work/project"),
        approval_policy=AskForApproval.NEVER,
        approvals_reviewer="codex",
        permission_profile=PermissionProfile.from_legacy_sandbox_policy(
            SandboxPolicy.read_only(network_access=True)
        ),
        active_permission_profile=ActivePermissionProfile.read_only(),
        model="gpt-5",
        model_provider_id="openai",
        service_tier="default",
        reasoning_effort="medium",
        reasoning_summary="auto",
        collaboration_mode=CollaborationMode(mode=ModeKind.default(), settings=Settings(model="gpt-5")),
        personality="balanced",
    )

    settings = thread_settings_from_config_snapshot(snapshot).to_mapping()

    assert settings["cwd"] == str(Path("/work/project"))
    assert settings["approval_policy"] == "never"
    assert settings["approvals_reviewer"] == "codex"
    assert settings["sandbox_policy"]["type"] == "readOnly"
    assert settings["sandbox_policy"]["network_access"] is True
    assert settings["active_permission_profile"] == {"id": ":read-only"}
    assert settings["model"] == "gpt-5"
    assert settings["model_provider"] == "openai"
    assert settings["service_tier"] == "default"
    assert settings["effort"] == "medium"
    assert settings["summary"] == "auto"
    assert settings["collaboration_mode"] == {
        "mode": "default",
        "settings": {
            "model": "gpt-5",
            "reasoning_effort": None,
            "developer_instructions": None,
        },
    }
    assert settings["personality"] == "balanced"


def test_thread_settings_from_core_snapshot_matches_config_projection() -> None:
    # Rust source: thread_summary.rs::thread_settings_from_core_snapshot.
    snapshot = ThreadSettingsSnapshot(
        model="gpt-5",
        model_provider_id="openai",
        approval_policy=GranularApprovalConfig(
            sandbox_approval=True,
            rules=False,
            mcp_elicitations=True,
        ),
        approvals_reviewer="codex",
        permission_profile=PermissionProfile.read_only(),
        active_permission_profile=None,
        cwd=Path("/work/project"),
        collaboration_mode=CollaborationMode(mode=ModeKind.default(), settings=Settings(model="gpt-5")),
        service_tier=None,
        reasoning_effort=None,
        reasoning_summary=None,
        personality=None,
    )

    settings = thread_settings_from_core_snapshot(snapshot).to_mapping()

    assert settings["model"] == "gpt-5"
    assert settings["model_provider"] == "openai"
    assert settings["approval_policy"] == {
        "sandbox_approval": True,
        "rules": False,
        "skill_approval": False,
        "request_permissions": False,
        "mcp_elicitations": True,
    }
    assert settings["sandbox_policy"]["type"] == "readOnly"
    assert settings["active_permission_profile"] is None


def test_thread_started_notification_clears_turns() -> None:
    # Rust source: thread_summary.rs::thread_started_notification.
    thread = Thread(
        id="t1",
        session_id="t1",
        forked_from_id=None,
        preview="preview",
        ephemeral=False,
        model_provider="openai",
        created_at=1,
        updated_at=2,
        status=ThreadStatus.not_loaded(),
        path=None,
        cwd="/work/project",
        cli_version="0.0.0",
        turns=({"id": "turn-1", "items": [], "status": {"type": "completed"}},),
    )

    notification = thread_started_notification(thread)

    assert notification.thread.turns == ()
    assert thread.turns != ()


def test_summary_to_thread_materializes_not_loaded_thread_without_turns() -> None:
    # Rust source: thread_summary.rs::summary_to_thread.
    parent = ThreadId.from_string("3f941c35-29b3-493b-b0a4-e25800d9aeb0")
    source = SessionSource.subagent(
        SubAgentSource.thread_spawn(parent_thread_id=parent, depth=1, agent_nickname="Ada", agent_role="reviewer")
    )
    summary = extract_conversation_summary(
        Path("rollout.jsonl"),
        [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Review this patch"}],
            }
        ],
        {
            "id": parent.to_json(),
            "timestamp": "2025-09-05T16:53:11.850Z",
            "cwd": "/work/project",
            "cli_version": "0.0.0",
            "model_provider": "openai",
            "source": source,
        },
        {"commit_hash": "abc123", "branch": "main", "repository_url": "https://example/repo"},
        "fallback",
        None,
    )

    assert summary is not None
    thread = summary_to_thread(summary, Path("/fallback"))

    assert thread.id == parent.to_json()
    assert thread.session_id == parent.to_json()
    assert thread.preview == "Review this patch"
    assert thread.status.type == "notLoaded"
    assert thread.agent_nickname == "Ada"
    assert thread.agent_role == "reviewer"
    assert thread.source.variant == "subAgent"
    assert thread.git_info is not None
    assert thread.git_info.sha == "abc123"
    assert thread.turns == ()
