from __future__ import annotations

from pycodex.app_server_protocol.common import (
    ClientNotification,
    ClientRequest,
    ClientRequestSerializationScope,
    FuzzyFileSearchMatchType,
    FuzzyFileSearchResponse,
    FuzzyFileSearchResult,
    FuzzyFileSearchSessionStartParams,
    SERVER_NOTIFICATION_METHODS,
    ServerNotification,
    ServerRequest,
    server_notification_from_jsonrpc,
)
from pycodex.app_server_protocol.jsonrpc_lite import JSONRPCNotification, JSONRPCRequest


def test_client_request_serialization_scope_covers_keyed_families() -> None:
    # Rust: codex-app-server-protocol protocol/common.rs
    # test client_request_serialization_scope_covers_keyed_families.
    assert ClientRequest("ThreadResume", 1, {"thread_id": "thread-1"}).serialization_scope() == (
        ClientRequestSerializationScope.thread("thread-1")
    )
    assert ClientRequest(
        "ThreadResume",
        1,
        {"thread_id": "", "path": "/tmp/resume-thread.jsonl"},
    ).serialization_scope() == ClientRequestSerializationScope.thread_path("/tmp/resume-thread.jsonl")
    assert ClientRequest("ThreadFork", 1, {"threadId": "thread-1"}).serialization_scope() == (
        ClientRequestSerializationScope.thread("thread-1")
    )
    assert ClientRequest(
        "OneOffCommandExec",
        1,
        {"command": ["sleep", "10"], "processId": "proc-1"},
    ).serialization_scope() == ClientRequestSerializationScope.command_exec_process("proc-1")
    assert ClientRequest("FuzzyFileSearchSessionUpdate", 1, {"sessionId": "search-1"}).serialization_scope() == (
        ClientRequestSerializationScope.fuzzy_file_search_session("search-1")
    )
    assert ClientRequest("FsWatch", 1, {"watchId": "watch-1"}).serialization_scope() == (
        ClientRequestSerializationScope.fs_watch("watch-1")
    )
    assert ClientRequest("PluginInstall", 1, {"pluginName": "plugin-a"}).serialization_scope() == (
        ClientRequestSerializationScope.global_("config")
    )
    assert ClientRequest("SkillsList", 1, {}).serialization_scope() == (
        ClientRequestSerializationScope.global_shared_read("config")
    )
    assert ClientRequest("McpServerOauthLogin", 1, {"name": "server-a"}).serialization_scope() == (
        ClientRequestSerializationScope.mcp_oauth("server-a")
    )
    assert ClientRequest("McpResourceRead", 1, {"threadId": "thread-1"}).serialization_scope() == (
        ClientRequestSerializationScope.thread("thread-1")
    )
    assert ClientRequest("ConfigRead", 1, {}).serialization_scope() == (
        ClientRequestSerializationScope.global_shared_read("config")
    )
    assert ClientRequest("GetAccount", 1, {}).serialization_scope() == (
        ClientRequestSerializationScope.global_("account-auth")
    )
    assert ClientRequest("ThreadGoalSet", 1, {"thread_id": "goal-thread"}).serialization_scope() == (
        ClientRequestSerializationScope.thread("goal-thread")
    )
    assert ClientRequest(
        "ThreadApproveGuardianDeniedAction",
        1,
        {"threadId": "guardian-thread"},
    ).serialization_scope() == ClientRequestSerializationScope.thread("guardian-thread")
    assert ClientRequest("MarketplaceRemove", 1, {"marketplaceName": "marketplace"}).serialization_scope() == (
        ClientRequestSerializationScope.global_("config")
    )
    assert ClientRequest("SendAddCreditsNudgeEmail", 1, {"creditType": "credits"}).serialization_scope() == (
        ClientRequestSerializationScope.global_("account-auth")
    )
    assert ClientRequest("EnvironmentAdd", 1, {"environmentId": "remote-a"}).serialization_scope() == (
        ClientRequestSerializationScope.global_("environment")
    )


def test_client_request_serialization_scope_covers_unkeyed_representatives() -> None:
    # Rust: codex-app-server-protocol protocol/common.rs
    # test client_request_serialization_scope_covers_unkeyed_representatives.
    assert ClientRequest("Initialize", 1, {}).serialization_scope() is None
    assert ClientRequest("ThreadStart", 1, {}).serialization_scope() is None
    assert ClientRequest("OneOffCommandExec", 1, {"command": ["true"]}).serialization_scope() is None
    assert ClientRequest("FsReadFile", 1, {"path": "/tmp/file.txt"}).serialization_scope() is None
    assert ClientRequest("ThreadTurnsList", 1, {"threadId": "thread-1"}).serialization_scope() is None
    assert ClientRequest("ThreadTurnsItemsList", 1, {"threadId": "thread-1", "turnId": "turn-1"}).serialization_scope() is None
    assert ClientRequest("McpResourceRead", 1, {"threadId": None}).serialization_scope() is None


def test_jsonrpc_method_roundtrips_and_legacy_names() -> None:
    # Rust: codex-app-server-protocol protocol/common.rs serde rename behavior.
    request = ClientRequest.from_jsonrpc(
        JSONRPCRequest(
            id=42,
            method="getConversationSummary",
            params={"conversationId": "67e55044-10b1-426f-9247-bb680e5fe0c8"},
        )
    )
    assert request.type == "GetConversationSummary"
    assert request.to_mapping() == {
        "id": 42,
        "method": "getConversationSummary",
        "params": {"conversationId": "67e55044-10b1-426f-9247-bb680e5fe0c8"},
    }

    server_request = ServerRequest.from_jsonrpc(
        JSONRPCRequest(id="srv-1", method="execCommandApproval", params={"id": "approval-1"})
    )
    assert server_request.type == "ExecCommandApproval"
    assert server_request.to_mapping()["method"] == "execCommandApproval"

    initialized = ClientNotification.from_jsonrpc(JSONRPCNotification(method="initialized"))
    assert initialized.type == "Initialized"
    assert initialized.to_mapping() == {"method": "initialized"}


def test_server_notification_method_lookup_uses_common_registry() -> None:
    # Rust: codex-app-server-protocol protocol/common.rs ServerNotification tags.
    notification = ServerNotification("ThreadStarted", {"threadId": "thread-1"})
    assert notification.to_mapping()["method"] == SERVER_NOTIFICATION_METHODS["ThreadStarted"]

    parsed = server_notification_from_jsonrpc(
        JSONRPCNotification(method="thread/started", params={"threadId": "thread-1"})
    )
    assert parsed.type == "ThreadStarted"


def test_fuzzy_file_search_payloads_preserve_rust_wire_shapes() -> None:
    # Rust: codex-app-server-protocol protocol/common.rs fuzzy search payload structs.
    start = FuzzyFileSearchSessionStartParams.from_mapping(
        {"sessionId": "search-1", "roots": ["/tmp/repo"]}
    )
    assert start.to_camel_mapping() == {"sessionId": "search-1", "roots": ["/tmp/repo"]}

    result = FuzzyFileSearchResult(
        root="/tmp/repo",
        path="src/lib.rs",
        match_type=FuzzyFileSearchMatchType.FILE,
        file_name="lib.rs",
        score=42,
        indices=[0, 4],
    )
    assert result.to_camel_mapping() == {
        "root": "/tmp/repo",
        "path": "src/lib.rs",
        "matchType": "file",
        "fileName": "lib.rs",
        "score": 42,
        "indices": [0, 4],
    }

    response = FuzzyFileSearchResponse.from_mapping({"files": [result.to_camel_mapping()]})
    assert response.to_camel_mapping()["files"][0]["fileName"] == "lib.rs"
