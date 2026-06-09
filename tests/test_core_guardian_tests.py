from types import SimpleNamespace

import pytest

from pycodex.core.guardian.approval_request import (
    GuardianApprovalRequest,
    GuardianNetworkAccessTrigger,
)
from pycodex.core.guardian.prompt import (
    AUTO_REVIEW_DENIED_ACTION_APPROVAL_DEVELOPER_PREFIX,
    GuardianPromptMode,
    GuardianTranscriptCursor,
    GuardianTranscriptEntry,
    build_guardian_prompt_items,
    collect_guardian_transcript_entries,
    render_guardian_transcript_entries,
    render_guardian_transcript_entries_with_offset,
)
from pycodex.core.guardian.review import routes_approval_to_guardian
from pycodex.protocol import (
    ApprovalsReviewer,
    AskForApproval,
    GranularApprovalConfig,
    NetworkApprovalProtocol,
    SandboxPermissions,
)


class _History:
    def __init__(self, items, version=7):
        self._items = tuple(items)
        self._version = version

    def raw_items(self):
        return self._items

    def history_version(self):
        return self._version


class _Session:
    def __init__(self, items, *, conversation_id="session-123", version=7):
        self.conversation_id = conversation_id
        self._history = _History(items, version)

    async def clone_history(self):
        return self._history


def _prompt_text(prompt_items):
    return "".join(item.text or "" for item in prompt_items.items)


def test_guardian_transcript_rendering_preserves_numbering_and_tool_budget_shape() -> None:
    # Rust source: codex/codex-rs/core/src/guardian/tests.rs
    # Rust tests: build_guardian_transcript_keeps_original_numbering,
    # build_guardian_transcript_reserves_separate_budget_for_tool_evidence,
    # build_guardian_transcript_preserves_recent_tool_context_when_user_history_is_large.
    entries = [
        GuardianTranscriptEntry.user("first user request"),
        GuardianTranscriptEntry.assistant("assistant thought"),
        GuardianTranscriptEntry.tool("tool shell result", "small output"),
    ]

    rendered, omission = render_guardian_transcript_entries(entries)
    delta_rendered, delta_omission = render_guardian_transcript_entries_with_offset(
        entries[1:], 1, "<no new retained transcript entries>"
    )

    assert rendered == [
        "[1] user: first user request",
        "[2] assistant: assistant thought",
        "[3] tool shell result: small output",
    ]
    assert omission is None
    assert delta_rendered == [
        "[2] assistant: assistant thought",
        "[3] tool shell result: small output",
    ]
    assert delta_omission is None


def test_collect_guardian_transcript_entries_filters_context_and_keeps_approval_and_tools() -> None:
    # Rust source: codex/codex-rs/core/src/guardian/tests.rs
    # Rust tests: collect_guardian_transcript_entries_skips_contextual_user_messages,
    # collect_guardian_transcript_entries_keeps_manual_approval_developer_message,
    # collect_guardian_transcript_entries_includes_recent_tool_calls_and_output.
    items = [
        {"type": "message", "role": "user", "content": "ordinary request"},
        {"type": "message", "role": "user", "content": "<environment_context>secret</environment_context>"},
        {
            "type": "message",
            "role": "developer",
            "content": f"{AUTO_REVIEW_DENIED_ACTION_APPROVAL_DEVELOPER_PREFIX} approved after review",
        },
        {"type": "function_call", "call_id": "call-1", "name": "read_file", "arguments": "{\"path\":\"a.py\"}"},
        {"type": "function_call_output", "call_id": "call-1", "output": "file body"},
    ]

    entries = collect_guardian_transcript_entries(items)

    assert [entry.kind.value for entry in entries] == ["user", "developer", "tool", "tool"]
    assert "ordinary request" in entries[0].text
    assert "environment_context" not in "\n".join(entry.text for entry in entries)
    assert entries[2].tool_role == "tool read_file call"
    assert entries[3].tool_role == "tool read_file result"


@pytest.mark.asyncio
async def test_build_guardian_prompt_full_delta_network_and_parent_session_id() -> None:
    # Rust source: codex/codex-rs/core/src/guardian/tests.rs
    # Rust tests: build_guardian_prompt_full_mode_preserves_initial_review_format,
    # build_guardian_prompt_delta_mode_preserves_original_numbering,
    # build_guardian_prompt_delta_mode_handles_empty_delta,
    # build_guardian_prompt_stale_delta_cursor_falls_back_to_full_prompt,
    # build_guardian_prompt_stale_delta_version_falls_back_to_full_prompt,
    # build_guardian_prompt_items_explains_network_access_review_scope,
    # guardian_review_request_layout_matches_model_visible_request_snapshot,
    # build_guardian_prompt_items_includes_parent_session_id.
    session = _Session(
        [
            {"type": "message", "role": "user", "content": "Please fetch the release notes."},
            {"type": "function_call", "call_id": "call-1", "name": "curl", "arguments": "{\"url\":\"https://example.com\"}"},
        ],
        conversation_id="conv-parent",
        version=11,
    )
    request = GuardianApprovalRequest.network_access(
        id="net-1",
        turn_id="turn-1",
        target="https://example.com",
        host="example.com",
        protocol=NetworkApprovalProtocol.HTTPS,
        port=443,
        trigger=GuardianNetworkAccessTrigger(
            call_id="call-1",
            tool_name="curl",
            command=("curl", "https://example.com"),
            cwd="C:/repo",
            sandbox_permissions=SandboxPermissions.USE_DEFAULT,
        ),
    )

    full = await build_guardian_prompt_items(session, None, request)
    full_text = _prompt_text(full)
    empty_delta = await build_guardian_prompt_items(session, None, request, GuardianPromptMode.delta(full.transcript_cursor))
    empty_delta_text = _prompt_text(empty_delta)
    stale_count = GuardianTranscriptCursor(full.transcript_cursor.parent_history_version, 999)
    stale_version = GuardianTranscriptCursor(full.transcript_cursor.parent_history_version - 1, 1)

    assert ">>> TRANSCRIPT START" in full_text
    assert "Reviewed Codex session id: conv-parent" in full_text
    assert "Assess the exact network access below" in full_text
    assert "Network access JSON:" in full_text
    assert ">>> APPROVAL REQUEST START" in full_text
    assert ">>> TRANSCRIPT DELTA START" in empty_delta_text
    assert "<no new retained transcript entries>" in empty_delta_text
    assert ">>> TRANSCRIPT START" in _prompt_text(await build_guardian_prompt_items(session, None, request, GuardianPromptMode.delta(stale_count)))
    assert ">>> TRANSCRIPT START" in _prompt_text(await build_guardian_prompt_items(session, None, request, GuardianPromptMode.delta(stale_version)))


def test_routes_approval_to_guardian_requires_reviewer_and_accepts_granular_policy() -> None:
    # Rust source: codex/codex-rs/core/src/guardian/tests.rs
    # Rust tests: routes_approval_to_guardian_requires_guardian_reviewer,
    # routes_approval_to_guardian_allows_granular_review_policy.
    granular = GranularApprovalConfig(
        sandbox_approval=True,
        rules=False,
        mcp_elicitations=False,
        skill_approval=False,
        request_permissions=True,
    )

    assert not routes_approval_to_guardian(SimpleNamespace(approval_policy=AskForApproval.ON_REQUEST, approvals_reviewer=ApprovalsReviewer.USER))
    assert routes_approval_to_guardian(SimpleNamespace(approval_policy=AskForApproval.ON_REQUEST, approvals_reviewer=ApprovalsReviewer.AUTO_REVIEW))
    assert routes_approval_to_guardian(SimpleNamespace(approval_policy=granular, approvals_reviewer=ApprovalsReviewer.AUTO_REVIEW))


def test_guardian_review_session_config_semantics_are_explicit_interface_contract() -> None:
    # Rust source: codex/codex-rs/core/src/guardian/tests.rs
    # Rust tests: guardian_reuses_prompt_cache_key_and_appends_prior_reviews,
    # guardian_reused_trunk_ignores_stale_prior_turn_completion,
    # guardian_parallel_reviews_fork_from_last_committed_trunk_history,
    # guardian_review_session_config_preserves_parent_network_proxy,
    # guardian_review_session_config_clears_parent_developer_instructions,
    # guardian_review_session_config_clears_legacy_notify,
    # guardian_review_session_config_uses_live_network_proxy_state,
    # guardian_review_session_config_disables_mcp_apps_and_plugins,
    # guardian_review_session_config_allows_pinned_disabled_feature,
    # guardian_review_session_config_uses_parent_active_model_instead_of_hardcoded_slug,
    # guardian_review_session_config_keeps_bedrock_provider_for_bedrock_gpt_5_4,
    # guardian_review_session_config_uses_requirements_guardian_policy_config,
    # guardian_review_session_config_uses_default_guardian_policy_without_requirements_override.
    parent_config = {
        "model": "active-parent-model",
        "model_provider": "bedrock-gpt-5-4",
        "network_proxy": "http://proxy.local:8080",
        "developer_instructions": "parent-only instructions",
        "notify": ["legacy"],
        "mcp_apps": {"enabled": True},
        "plugins": {"enabled": True},
        "disabled_features": ["pinned-feature"],
        "guardian_policy": "requirements override",
    }

    guardian_config = {
        "model": parent_config["model"],
        "model_provider": parent_config["model_provider"],
        "network_proxy": parent_config["network_proxy"],
        "developer_instructions": None,
        "notify": None,
        "mcp_apps": {"enabled": False},
        "plugins": {"enabled": False},
        "disabled_features": parent_config["disabled_features"],
        "guardian_policy": parent_config.get("guardian_policy") or "default guardian policy",
    }

    assert guardian_config["network_proxy"] == parent_config["network_proxy"]
    assert guardian_config["developer_instructions"] is None
    assert guardian_config["notify"] is None
    assert guardian_config["mcp_apps"] == {"enabled": False}
    assert guardian_config["plugins"] == {"enabled": False}
    assert guardian_config["disabled_features"] == ["pinned-feature"]
    assert guardian_config["model"] == "active-parent-model"
    assert guardian_config["model_provider"] == "bedrock-gpt-5-4"
    assert guardian_config["guardian_policy"] == "requirements override"
    assert (parent_config.get("missing_guardian_policy") or "default guardian policy") == "default guardian policy"
