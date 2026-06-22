import asyncio
import re

from pycodex.network_proxy import (
    AUDIT_TARGET,
    DEFAULT_CLIENT_ADDRESS,
    DEFAULT_METHOD,
    POLICY_DECISION_DENY,
    POLICY_DECISION_EVENT_NAME,
    POLICY_SCOPE_DOMAIN,
    POLICY_SCOPE_NON_DOMAIN,
    BlockDecisionAuditEventArgs,
    HostBlockDecision,
    HostBlockReason,
    NetworkDecision,
    NetworkDecisionSource,
    NetworkPolicyDecision,
    NetworkPolicyRequest,
    NetworkPolicyRequestArgs,
    NetworkProtocol,
    REASON_DENIED,
    REASON_METHOD_NOT_ALLOWED,
    REASON_NOT_ALLOWED,
    REASON_NOT_ALLOWED_LOCAL,
    emit_block_decision_audit_event,
    evaluate_host_policy,
)


LEGACY_DOMAIN_POLICY_DECISION_EVENT_NAME = "codex.network_proxy.domain_policy_decision"
LEGACY_BLOCK_DECISION_EVENT_NAME = "codex.network_proxy.block_decision"


class PolicyState:
    def __init__(
        self,
        decision: HostBlockDecision,
        metadata: dict[str, str] | None = None,
    ) -> None:
        self.decision = decision
        self.audit_metadata = metadata or {}
        self.audit_events: list[dict[str, str]] = []
        self.host_blocked_calls: list[tuple[str, int]] = []

    async def host_blocked(self, host: str, port: int) -> HostBlockDecision:
        self.host_blocked_calls.append((host, port))
        return self.decision

    def record_audit_event(self, event: dict[str, str]) -> None:
        self.audit_events.append(event)


def request(
    host: str = "example.com",
    *,
    port: int = 80,
    protocol: NetworkProtocol = NetworkProtocol.HTTP,
    client_addr: str | None = None,
    method: str | None = None,
) -> NetworkPolicyRequest:
    return NetworkPolicyRequest.new(
        NetworkPolicyRequestArgs(
            protocol=protocol,
            host=host,
            port=port,
            client_addr=client_addr,
            method=method,
            command=None,
            exec_policy_hint=None,
        )
    )


def policy_event(state: PolicyState) -> dict[str, str]:
    matches = [
        event
        for event in state.audit_events
        if event.get("event.name") == POLICY_DECISION_EVENT_NAME
    ]
    assert len(matches) == 1
    return matches[0]


def is_rfc3339_utc_millis(timestamp: str) -> bool:
    return re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z",
        timestamp,
    ) is not None


def test_evaluate_host_policy_emits_domain_event_for_decider_allow_override() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/network_policy.rs
    # Rust test: evaluate_host_policy_emits_domain_event_for_decider_allow_override
    # Contract: NotAllowed baseline requests consult the decider; an allow override emits domain audit fields.
    state = PolicyState(HostBlockDecision.blocked(HostBlockReason.NOT_ALLOWED))
    calls: list[NetworkPolicyRequest] = []

    async def decider(req: NetworkPolicyRequest) -> NetworkDecision:
        calls.append(req)
        return NetworkDecision.allow()

    decision = asyncio.run(evaluate_host_policy(state, decider, request()))

    assert decision == NetworkDecision.allow()
    assert len(calls) == 1
    assert state.host_blocked_calls == [("example.com", 80)]

    event = policy_event(state)
    assert event["target"] == AUDIT_TARGET
    assert event["target"].startswith("codex_otel.")
    assert event["network.policy.scope"] == POLICY_SCOPE_DOMAIN
    assert event["network.policy.decision"] == "allow"
    assert event["network.policy.source"] == "decider"
    assert event["network.policy.reason"] == REASON_NOT_ALLOWED
    assert event["network.transport.protocol"] == "http"
    assert event["server.address"] == "example.com"
    assert event["server.port"] == "80"
    assert event["http.request.method"] == DEFAULT_METHOD
    assert event["client.address"] == DEFAULT_CLIENT_ADDRESS
    assert event["network.policy.override"] == "true"
    assert is_rfc3339_utc_millis(event["event.timestamp"])
    assert LEGACY_DOMAIN_POLICY_DECISION_EVENT_NAME not in [e.get("event.name") for e in state.audit_events]
    assert LEGACY_BLOCK_DECISION_EVENT_NAME not in [e.get("event.name") for e in state.audit_events]


def test_evaluate_host_policy_emits_domain_event_for_baseline_deny() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/network_policy.rs
    # Rust test: evaluate_host_policy_emits_domain_event_for_baseline_deny
    # Contract: non-NotAllowed host blocks bypass the decider and emit baseline deny fields.
    state = PolicyState(HostBlockDecision.blocked(HostBlockReason.DENIED))

    decision = asyncio.run(
        evaluate_host_policy(
            state,
            None,
            request("blocked.com", client_addr="127.0.0.1:1234", method="GET"),
        )
    )

    assert decision == NetworkDecision.deny_with_source(
        REASON_DENIED,
        NetworkDecisionSource.BASELINE_POLICY,
    )
    event = policy_event(state)
    assert event["network.policy.decision"] == "deny"
    assert event["network.policy.source"] == "baseline_policy"
    assert event["network.policy.reason"] == REASON_DENIED
    assert event["network.policy.override"] == "false"
    assert event["http.request.method"] == "GET"
    assert event["client.address"] == "127.0.0.1:1234"


def test_evaluate_host_policy_emits_domain_event_for_decider_ask() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/network_policy.rs
    # Rust test: evaluate_host_policy_emits_domain_event_for_decider_ask
    # Contract: decider ask is returned as a deny-shaped decision with decision=ask and source=decider.
    state = PolicyState(HostBlockDecision.blocked(HostBlockReason.NOT_ALLOWED))

    async def decider(_req: NetworkPolicyRequest) -> NetworkDecision:
        return NetworkDecision.ask(REASON_NOT_ALLOWED)

    decision = asyncio.run(evaluate_host_policy(state, decider, request(method="GET")))

    assert decision == NetworkDecision.ask(REASON_NOT_ALLOWED)
    event = policy_event(state)
    assert event["network.policy.decision"] == "ask"
    assert event["network.policy.source"] == "decider"
    assert event["network.policy.reason"] == REASON_NOT_ALLOWED
    assert event["network.policy.override"] == "false"


def test_evaluate_host_policy_emits_metadata_fields() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/network_policy.rs
    # Rust test: evaluate_host_policy_emits_metadata_fields
    # Contract: audit metadata is projected to the same tracing field names as Rust.
    state = PolicyState(
        HostBlockDecision.blocked(HostBlockReason.NOT_ALLOWED),
        {
            "conversation_id": "conversation-1",
            "app_version": "1.2.3",
            "user_account_id": "acct-1",
            "auth_mode": "Chatgpt",
            "originator": "codex_cli_rs",
            "user_email": "test@example.com",
            "terminal_type": "iTerm.app/3.6.5",
            "model": "gpt-5.3-codex",
            "slug": "gpt-5.3-codex",
        },
    )

    asyncio.run(evaluate_host_policy(state, None, request(method="GET")))

    event = policy_event(state)
    assert event["conversation.id"] == "conversation-1"
    assert event["app.version"] == "1.2.3"
    assert event["auth_mode"] == "Chatgpt"
    assert event["originator"] == "codex_cli_rs"
    assert event["user.account_id"] == "acct-1"
    assert event["user.email"] == "test@example.com"
    assert event["terminal.type"] == "iTerm.app/3.6.5"
    assert event["model"] == "gpt-5.3-codex"
    assert event["slug"] == "gpt-5.3-codex"


def test_emit_block_decision_audit_event_emits_non_domain_event() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/network_policy.rs
    # Rust test: emit_block_decision_audit_event_emits_non_domain_event
    # Contract: non-domain block audit events use mode_guard source, deny decision, defaults, and no legacy event name.
    state = PolicyState(HostBlockDecision.allow())

    emit_block_decision_audit_event(
        state,  # type: ignore[arg-type]
        BlockDecisionAuditEventArgs(
            source=NetworkDecisionSource.MODE_GUARD,
            reason=REASON_METHOD_NOT_ALLOWED,
            protocol=NetworkProtocol.HTTP,
            server_address="unix-socket",
            server_port=0,
            method="POST",
            client_addr=None,
        ),
    )

    event = policy_event(state)
    assert event["target"] == AUDIT_TARGET
    assert event["network.policy.scope"] == POLICY_SCOPE_NON_DOMAIN
    assert event["network.policy.decision"] == POLICY_DECISION_DENY
    assert event["network.policy.source"] == "mode_guard"
    assert event["network.policy.reason"] == REASON_METHOD_NOT_ALLOWED
    assert event["network.transport.protocol"] == "http"
    assert event["server.address"] == "unix-socket"
    assert event["server.port"] == "0"
    assert event["http.request.method"] == "POST"
    assert event["client.address"] == DEFAULT_CLIENT_ADDRESS
    assert event["network.policy.override"] == "false"
    assert LEGACY_BLOCK_DECISION_EVENT_NAME not in [e.get("event.name") for e in state.audit_events]


def test_evaluate_host_policy_still_denies_not_allowed_local_without_decider_override() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/network_policy.rs
    # Rust test: evaluate_host_policy_still_denies_not_allowed_local_without_decider_override
    # Contract: NotAllowedLocal is a baseline deny and never invokes a decider override.
    state = PolicyState(HostBlockDecision.blocked(HostBlockReason.NOT_ALLOWED_LOCAL))

    decision = asyncio.run(evaluate_host_policy(state, None, request("127.0.0.1", method="GET")))

    assert decision == NetworkDecision.deny_with_source(
        REASON_NOT_ALLOWED_LOCAL,
        NetworkDecisionSource.BASELINE_POLICY,
    )


def test_ask_uses_decider_source_and_ask_decision() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/network_policy.rs
    # Rust test: ask_uses_decider_source_and_ask_decision
    # Contract: NetworkDecision::ask stores source=Decider and decision=Ask.
    assert NetworkDecision.ask(REASON_NOT_ALLOWED) == NetworkDecision(
        "deny",
        REASON_NOT_ALLOWED,
        NetworkDecisionSource.DECIDER,
        NetworkPolicyDecision.ASK,
    )
