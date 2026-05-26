import threading
import unittest

from pycodex.core import (
    NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED,
    BlockedRequest,
    CancellationToken,
    HostApprovalKey,
    NetworkApprovalOutcome,
    NetworkApprovalRejected,
    NetworkApprovalService,
    NetworkDecision,
    PendingApprovalDecision,
    PendingHostApproval,
    allows_network_approval_flow,
    network_approval_outcome_to_result,
    permission_profile_allows_network_approval_flow,
    protocol_key_label,
)
from pycodex.protocol import (
    AskForApproval,
    NetworkApprovalProtocol,
    NetworkSandboxPolicy,
    PermissionProfile,
)


class NetworkApprovalTests(unittest.TestCase):
    def test_host_approval_key_normalizes_host_and_protocol_labels(self) -> None:
        key = HostApprovalKey.from_request(
            {"host": "Example.COM", "port": 443},
            NetworkApprovalProtocol.SOCKS5_TCP,
        )

        self.assertEqual(key, HostApprovalKey("example.com", "socks5-tcp", 443))
        self.assertEqual(protocol_key_label("http-connect"), "https")

    def test_pending_approvals_are_deduped_per_host_protocol_and_port(self) -> None:
        service = NetworkApprovalService()
        key = HostApprovalKey("example.com", "http", 443)

        first, first_is_owner = service.get_or_create_pending_approval(key)
        second, second_is_owner = service.get_or_create_pending_approval(key)

        self.assertTrue(first_is_owner)
        self.assertFalse(second_is_owner)
        self.assertIs(first, second)

    def test_pending_approvals_do_not_dedupe_across_ports(self) -> None:
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

    def test_session_approved_hosts_sync_replaces_existing_target_hosts(self) -> None:
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

        self.assertEqual(target.session_approved_hosts, source.session_approved_hosts)

    def test_pending_waiters_receive_owner_decision(self) -> None:
        pending = PendingHostApproval()
        result: list[PendingApprovalDecision | None] = []
        waiter = threading.Thread(target=lambda: result.append(pending.wait_for_decision(1.0)))

        waiter.start()
        pending.set_decision(PendingApprovalDecision.ALLOW_ONCE)
        waiter.join(1.0)

        self.assertEqual(result, [PendingApprovalDecision.ALLOW_ONCE])

    def test_allow_once_and_allow_for_session_both_allow_network(self) -> None:
        self.assertEqual(PendingApprovalDecision.ALLOW_ONCE.to_network_decision(), NetworkDecision.allow())
        self.assertEqual(PendingApprovalDecision.ALLOW_FOR_SESSION.to_network_decision(), NetworkDecision.allow())
        self.assertEqual(
            PendingApprovalDecision.DENY.to_network_decision(),
            NetworkDecision.deny(NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED),
        )

    def test_only_never_policy_disables_network_approval_flow(self) -> None:
        self.assertFalse(allows_network_approval_flow(AskForApproval.NEVER))
        self.assertTrue(allows_network_approval_flow(AskForApproval.ON_REQUEST))
        self.assertTrue(allows_network_approval_flow(AskForApproval.ON_FAILURE))
        self.assertTrue(allows_network_approval_flow(AskForApproval.UNLESS_TRUSTED))

    def test_network_approval_flow_is_limited_to_managed_permission_profiles(self) -> None:
        self.assertTrue(permission_profile_allows_network_approval_flow(PermissionProfile.read_only()))
        self.assertTrue(permission_profile_allows_network_approval_flow(PermissionProfile.workspace_write()))
        self.assertFalse(permission_profile_allows_network_approval_flow(PermissionProfile.disabled()))
        self.assertFalse(
            permission_profile_allows_network_approval_flow(
                PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED)
            )
        )

    def test_active_call_preserves_triggering_command_context(self) -> None:
        service = NetworkApprovalService()
        trigger = {
            "call_id": "call-1",
            "tool_name": "shell_command",
            "command": ["curl", "https://example.com"],
            "cwd": "/repo",
        }

        service.register_call(
            "registration-1",
            "turn-1",
            trigger,
            "curl https://example.com",
        )

        call = service.resolve_single_active_call()
        self.assertIsNotNone(call)
        self.assertEqual(call.trigger, trigger)
        self.assertEqual(call.command, "curl https://example.com")

    def test_record_blocked_request_sets_policy_outcome_for_owner_call(self) -> None:
        service = NetworkApprovalService()
        token = service.register_call("registration-1", "turn-1", {}, "curl https://example.com")

        service.record_blocked_request(
            BlockedRequest(
                host="example.com",
                reason="not_allowed",
                protocol="http",
                decision="deny",
                port=80,
            )
        )

        self.assertTrue(token.is_cancelled())
        self.assertEqual(
            service.take_call_outcome("registration-1"),
            NetworkApprovalOutcome.denied_by_policy(
                'Network access to "example.com" was blocked: domain is not on the allowlist for the current sandbox mode.'
            ),
        )

    def test_blocked_request_policy_does_not_override_user_denial_outcome(self) -> None:
        service = NetworkApprovalService()
        service.register_call("registration-1", "turn-1", {}, "curl https://example.com")
        service.record_call_outcome("registration-1", NetworkApprovalOutcome.denied_by_user())

        service.record_blocked_request(
            BlockedRequest(
                host="example.com",
                reason="not_allowed",
                protocol="http",
                decision="deny",
            )
        )

        self.assertEqual(
            service.take_call_outcome("registration-1"),
            NetworkApprovalOutcome.denied_by_user(),
        )

    def test_finish_call_returns_denial_and_unregisters_active_call(self) -> None:
        service = NetworkApprovalService()
        service.register_call("registration-1", "turn-1", {}, "curl https://example.com")
        service.record_call_outcome(
            "registration-1",
            NetworkApprovalOutcome.denied_by_policy("network denied"),
        )

        with self.assertRaisesRegex(NetworkApprovalRejected, "network denied"):
            service.finish_call("registration-1")

        self.assertIsNone(service.resolve_single_active_call())
        self.assertIsNone(service.take_call_outcome("registration-1"))

    def test_outcome_conversion_maps_user_denial_and_success(self) -> None:
        network_approval_outcome_to_result(None)
        with self.assertRaisesRegex(NetworkApprovalRejected, "rejected by user"):
            network_approval_outcome_to_result(NetworkApprovalOutcome.denied_by_user())

    def test_record_call_outcome_ignores_inactive_call(self) -> None:
        service = NetworkApprovalService()
        token = CancellationToken()
        service.register_call("registration-1", "turn-1", {}, "curl", token)
        service.unregister_call("registration-1")

        service.record_call_outcome(
            "registration-1",
            NetworkApprovalOutcome.denied_by_policy("network denied"),
        )

        self.assertFalse(token.is_cancelled())
        self.assertIsNone(service.take_call_outcome("registration-1"))

    def test_record_blocked_request_ignores_ambiguous_unattributed_requests(self) -> None:
        service = NetworkApprovalService()
        service.register_call("registration-1", "turn-1", {}, "curl")
        service.register_call("registration-2", "turn-1", {}, "curl")

        service.record_blocked_request(
            BlockedRequest(
                host="example.com",
                reason="not_allowed",
                protocol="http",
                decision="deny",
            )
        )

        self.assertIsNone(service.take_call_outcome("registration-1"))
        self.assertIsNone(service.take_call_outcome("registration-2"))

    def test_format_network_target_and_approval_id(self) -> None:
        key = HostApprovalKey("Example.com", "https", 443)

        self.assertEqual(
            NetworkApprovalService.format_network_target("https", "example.com", 443),
            "https://example.com:443",
        )
        self.assertEqual(
            NetworkApprovalService.approval_id_for_key(key),
            "network#https#example.com#443",
        )


if __name__ == "__main__":
    unittest.main()
