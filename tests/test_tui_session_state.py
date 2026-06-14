# Parity source: codex-rs/tui/src/session_state.rs

from pycodex.tui.session_state import (
    MessageHistoryMetadata,
    SessionNetworkProxyRuntime,
    ThreadSessionState,
)


def test_message_history_metadata_defaults_match_rust_default():
    assert MessageHistoryMetadata() == MessageHistoryMetadata(log_id=0, entry_count=0)


def test_network_proxy_runtime_stores_http_and_socks_addresses():
    proxy = SessionNetworkProxyRuntime(http_addr="127.0.0.1:8080", socks_addr="127.0.0.1:1080")

    assert proxy.http_addr == "127.0.0.1:8080"
    assert proxy.socks_addr == "127.0.0.1:1080"


def test_thread_session_state_holds_protocol_values_without_reinterpretation():
    state = ThreadSessionState(
        thread_id="thread-1",
        forked_from_id="thread-0",
        fork_parent_title="Parent",
        thread_name="Work",
        model="gpt-5",
        model_provider_id="openai",
        service_tier="default",
        approval_policy="on-request",
        approvals_reviewer="user",
        permission_profile={"profile": "workspace-write"},
        active_permission_profile="workspace-write",
        cwd="/repo",
        runtime_workspace_roots=["/repo"],
        instruction_source_paths=["/repo/AGENTS.md"],
        reasoning_effort="medium",
        collaboration_mode={"mode": "pair"},
        personality={"tone": "warm"},
        message_history=MessageHistoryMetadata(log_id=7, entry_count=3),
        network_proxy=SessionNetworkProxyRuntime("http", "socks"),
        rollout_path="/tmp/rollout.jsonl",
    )

    assert state.thread_id == "thread-1"
    assert state.permission_profile == {"profile": "workspace-write"}
    assert state.message_history == MessageHistoryMetadata(log_id=7, entry_count=3)


def test_set_cwd_retargeting_replaces_previous_cwd_root_when_present():
    state = ThreadSessionState(
        thread_id="thread-1",
        cwd="/repo/a",
        runtime_workspace_roots=["/repo/a", "/repo/shared"],
    )

    state.set_cwd_retargeting_implicit_runtime_workspace_root("/repo/b")

    assert state.cwd == "/repo/b"
    assert state.runtime_workspace_roots == ["/repo/b", "/repo/shared"]


def test_set_cwd_retargeting_only_updates_cwd_when_previous_cwd_not_root():
    state = ThreadSessionState(
        thread_id="thread-1",
        cwd="/repo/a",
        runtime_workspace_roots=["/repo/shared"],
    )

    state.set_cwd_retargeting_implicit_runtime_workspace_root("/repo/b")

    assert state.cwd == "/repo/b"
    assert state.runtime_workspace_roots == ["/repo/shared"]


def test_set_cwd_retargeting_deduplicates_existing_new_cwd_root():
    state = ThreadSessionState(
        thread_id="thread-1",
        cwd="/repo/a",
        runtime_workspace_roots=["/repo/a", "/repo/b", "/repo/shared", "/repo/shared"],
    )

    state.set_cwd_retargeting_implicit_runtime_workspace_root("/repo/b")

    assert state.runtime_workspace_roots == ["/repo/b", "/repo/shared"]
