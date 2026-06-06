import threading
import unittest

from pycodex.core.tools.network_approval import (
    ActiveNetworkApproval,
    CancellationToken,
    DeferredNetworkApproval,
    HostApprovalKey,
    NetworkApprovalMode,
    NetworkApprovalOutcome,
    NetworkApprovalRejected,
    NetworkApprovalService,
    PendingApprovalDecision,
    PendingHostApproval,
    allows_network_approval_flow,
    permission_profile_allows_network_approval_flow,
    protocol_key_label,
)
from pycodex.protocol import AskForApproval, NetworkApprovalProtocol, PermissionProfile


def _denied_blocked_request(host: str) -> dict[str, object]:
    return {
        "host": host,
        "reason": "not_allowed",
        "client": None,
        "method": None,
        "mode": None,
        "protocol": "http",
        "decision": "deny",
        "source": "decider",
        "port": 80,
    }


def _register_call_with_default_shell_trigger(
    service: NetworkApprovalService,
    registration_id: str,
) -> CancellationToken:
    return service.register_call(
        registration_id,
        "turn-1",
        {
            "call_id": "call-1",
            "tool_name": "shell_command",
            "command": ["curl", "https://example.com"],
            "cwd": "/tmp",
            "sandbox_permissions": "use_default",
            "additional_permissions": None,
            "justification": None,
            "tty": None,
        },
        "curl https://example.com",
    )


class ToolNetworkApprovalTests(unittest.TestCase):
    def test_pending_approvals_are_deduped_per_host_protocol_and_port(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs
        # Rust test: pending_approvals_are_deduped_per_host_protocol_and_port
        service = NetworkApprovalService()
        key = HostApprovalKey("example.com", "http", 443)

        first, first_is_owner = service.get_or_create_pending_approval(key)
        second, second_is_owner = service.get_or_create_pending_approval(key)

        self.assertTrue(first_is_owner)
        self.assertFalse(second_is_owner)
        self.assertIs(first, second)

    def test_pending_approvals_do_not_dedupe_across_ports(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs
        # Rust test: pending_approvals_do_not_dedupe_across_ports
        service = NetworkApprovalService()

        first, first_is_owner = service.get_or_create_pending_approval(
            HostApprovalKey("example.com", "https", 443)
        )
        second, second_is_owner = service.get_or_create_pending_approval(
            HostApprovalKey("example.com", "https", 8443)
        )

        self.assertTrue(first_is_owner)
        self.assertTrue(second_is_owner)
        self.assertIsNot(first, second)

    def test_session_approved_hosts_sync_preserves_protocol_and_port_scope(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs
        # Rust tests: session_approved_hosts_preserve_protocol_and_port_scope
        # and sync_session_approved_hosts_to_replaces_existing_target_hosts
        source = NetworkApprovalService()
        source.session_approved_hosts.update(
            {
                HostApprovalKey("example.com", "https", 443),
                HostApprovalKey("example.com", "https", 8443),
                HostApprovalKey("example.com", "http", 80),
            }
        )
        target = NetworkApprovalService()
        target.session_approved_hosts.add(HostApprovalKey("stale.example.com", "https", 443))

        source.sync_session_approved_hosts_to(target)

        self.assertEqual(
            sorted(target.session_approved_hosts, key=lambda key: (key.host, key.protocol, key.port)),
            [
                HostApprovalKey("example.com", "http", 80),
                HostApprovalKey("example.com", "https", 443),
                HostApprovalKey("example.com", "https", 8443),
            ],
        )

    def test_pending_waiters_receive_owner_decision(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs
        # Rust test: pending_waiters_receive_owner_decision
        pending = PendingHostApproval()
        received: list[PendingApprovalDecision | None] = []

        thread = threading.Thread(target=lambda: received.append(pending.wait_for_decision(1.0)))
        thread.start()
        pending.set_decision(PendingApprovalDecision.ALLOW_ONCE)
        thread.join(timeout=2.0)

        self.assertEqual(received, [PendingApprovalDecision.ALLOW_ONCE])

    def test_allow_once_and_allow_for_session_both_allow_network(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs
        # Rust test: allow_once_and_allow_for_session_both_allow_network
        self.assertEqual(PendingApprovalDecision.ALLOW_ONCE.to_network_decision().type, "allow")
        self.assertEqual(PendingApprovalDecision.ALLOW_FOR_SESSION.to_network_decision().type, "allow")
        self.assertEqual(PendingApprovalDecision.DENY.to_network_decision().type, "deny")
        self.assertEqual(PendingApprovalDecision.DENY.to_network_decision().reason, "not_allowed")

    def test_only_never_policy_disables_network_approval_flow(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs
        # Rust test: only_never_policy_disables_network_approval_flow
        self.assertFalse(allows_network_approval_flow(AskForApproval.NEVER))
        self.assertTrue(allows_network_approval_flow(AskForApproval.ON_REQUEST))
        self.assertTrue(allows_network_approval_flow(AskForApproval.ON_FAILURE))
        self.assertTrue(allows_network_approval_flow(AskForApproval.UNLESS_TRUSTED))

    def test_network_approval_flow_is_limited_to_managed_permission_profiles(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs
        # Rust test: network_approval_flow_is_limited_to_restricted_sandbox_modes
        self.assertTrue(permission_profile_allows_network_approval_flow(PermissionProfile.read_only()))
        self.assertTrue(permission_profile_allows_network_approval_flow(PermissionProfile.workspace_write()))
        self.assertFalse(permission_profile_allows_network_approval_flow(PermissionProfile.disabled()))

    def test_host_approval_key_normalizes_host_and_rejects_non_u16_ports(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs
        # Rust contract: HostApprovalKey stores lower-case host and u16 port.
        self.assertEqual(HostApprovalKey("EXAMPLE.COM", "https", 443).host, "example.com")
        with self.assertRaises(ValueError):
            HostApprovalKey("example.com", "https", 65536)
        with self.assertRaises(TypeError):
            HostApprovalKey("example.com", "https", True)  # type: ignore[arg-type]

    def test_protocol_key_label_matches_rust_host_approval_key_labels(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs::protocol_key_label
        # Rust contract: host approval keys distinguish http, https, socks5-tcp, and socks5-udp.
        self.assertEqual(protocol_key_label(NetworkApprovalProtocol.HTTP), "http")
        self.assertEqual(protocol_key_label(NetworkApprovalProtocol.HTTPS), "https")
        self.assertEqual(protocol_key_label(NetworkApprovalProtocol.SOCKS5_TCP), "socks5-tcp")
        self.assertEqual(protocol_key_label(NetworkApprovalProtocol.SOCKS5_UDP), "socks5-udp")
        self.assertEqual(
            HostApprovalKey.from_request(
                {"host": "API.EXAMPLE.COM", "port": 443},
                NetworkApprovalProtocol.HTTPS,
            ),
            HostApprovalKey("api.example.com", "https", 443),
        )

    def test_only_deferred_active_network_approval_converts_to_deferred_handle(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs::ActiveNetworkApproval::into_deferred
        # Rust contract: only deferred active approvals with a registration id produce a deferred handle.
        token = CancellationToken()

        deferred = ActiveNetworkApproval(
            "registration-1",
            NetworkApprovalMode.DEFERRED,
            token,
        ).into_deferred()
        self.assertIsInstance(deferred, DeferredNetworkApproval)
        assert deferred is not None
        self.assertEqual(deferred.registration_id, "registration-1")
        self.assertIs(deferred.cancellation_token, token)

        self.assertIsNone(
            ActiveNetworkApproval(
                "registration-2",
                NetworkApprovalMode.IMMEDIATE,
                token,
            ).into_deferred()
        )
        self.assertIsNone(
            ActiveNetworkApproval(
                None,
                NetworkApprovalMode.DEFERRED,
                token,
            ).into_deferred()
        )

    def test_active_call_preserves_triggering_command_context(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs
        # Rust test: active_call_preserves_triggering_command_context
        service = NetworkApprovalService()
        expected_trigger = {
            "call_id": "call-1",
            "tool_name": "shell_command",
            "command": ["curl", "https://example.com"],
            "cwd": "/repo",
            "sandbox_permissions": "use_default",
            "additional_permissions": None,
            "justification": "fetch release metadata",
            "tty": None,
        }

        service.register_call(
            "registration-1",
            "turn-1",
            expected_trigger,
            "curl https://example.com",
            CancellationToken(),
        )

        call = service.resolve_single_active_call()
        self.assertIsNotNone(call)
        assert call is not None
        self.assertEqual(call.trigger, expected_trigger)
        self.assertEqual(call.command, "curl https://example.com")

    def test_record_blocked_request_sets_policy_outcome_for_owner_call(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs
        # Rust test: record_blocked_request_sets_policy_outcome_for_owner_call
        service = NetworkApprovalService()
        cancellation_token = _register_call_with_default_shell_trigger(service, "registration-1")

        service.record_blocked_request(_denied_blocked_request("example.com"))

        self.assertTrue(cancellation_token.is_cancelled())
        self.assertEqual(
            service.take_call_outcome("registration-1"),
            NetworkApprovalOutcome.denied_by_policy(
                'Network access to "example.com" was blocked: domain is not on the allowlist '
                "for the current sandbox mode."
            ),
        )

    def test_blocked_request_policy_does_not_override_user_denial_outcome(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs
        # Rust test: blocked_request_policy_does_not_override_user_denial_outcome
        service = NetworkApprovalService()
        _register_call_with_default_shell_trigger(service, "registration-1")

        service.record_call_outcome("registration-1", NetworkApprovalOutcome.denied_by_user())
        service.record_blocked_request(_denied_blocked_request("example.com"))

        self.assertEqual(
            service.take_call_outcome("registration-1"),
            NetworkApprovalOutcome.denied_by_user(),
        )

    def test_finish_call_returns_denial_and_unregisters_active_call(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs
        # Rust test: finish_call_returns_denial_and_unregisters_active_call
        service = NetworkApprovalService()
        _register_call_with_default_shell_trigger(service, "registration-1")
        service.record_call_outcome(
            "registration-1",
            NetworkApprovalOutcome.denied_by_policy("network denied"),
        )

        with self.assertRaisesRegex(NetworkApprovalRejected, "^network denied$"):
            service.finish_call("registration-1")

        self.assertIsNone(service.resolve_single_active_call())
        self.assertIsNone(service.take_call_outcome("registration-1"))

    def test_deferred_finish_reuses_denial_result_after_first_consumer(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs
        # Rust test: deferred_finish_reuses_denial_result_after_first_consumer
        service = NetworkApprovalService()
        cancellation_token = _register_call_with_default_shell_trigger(service, "registration-1")
        deferred = DeferredNetworkApproval("registration-1", cancellation_token)
        service.record_call_outcome(
            "registration-1",
            NetworkApprovalOutcome.denied_by_policy("network denied"),
        )

        with self.assertRaisesRegex(NetworkApprovalRejected, "^network denied$"):
            deferred.finish(service)
        with self.assertRaisesRegex(NetworkApprovalRejected, "^network denied$"):
            deferred.finish(service)

    def test_record_call_outcome_ignores_inactive_call(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs
        # Rust test: record_call_outcome_ignores_inactive_call
        service = NetworkApprovalService()
        cancellation_token = _register_call_with_default_shell_trigger(service, "registration-1")
        service.unregister_call("registration-1")

        service.record_call_outcome(
            "registration-1",
            NetworkApprovalOutcome.denied_by_policy("network denied"),
        )

        self.assertFalse(cancellation_token.is_cancelled())
        self.assertIsNone(service.take_call_outcome("registration-1"))

    def test_record_blocked_request_ignores_ambiguous_unattributed_blocked_requests(self) -> None:
        # Rust source: codex-rs/core/src/tools/network_approval.rs
        # Rust test: record_blocked_request_ignores_ambiguous_unattributed_blocked_requests
        service = NetworkApprovalService()
        _register_call_with_default_shell_trigger(service, "registration-1")
        _register_call_with_default_shell_trigger(service, "registration-2")

        service.record_blocked_request(_denied_blocked_request("example.com"))

        self.assertIsNone(service.take_call_outcome("registration-1"))
        self.assertIsNone(service.take_call_outcome("registration-2"))


if __name__ == "__main__":
    unittest.main()
