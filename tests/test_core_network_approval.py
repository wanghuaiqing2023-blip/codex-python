import threading
import unittest

from pycodex.core import (
    NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED,
    ActiveNetworkApproval,
    BlockedRequest,
    CancellationToken,
    DeferredNetworkApproval,
    HostApprovalKey,
    InlineNetworkApprovalDisposition,
    NetworkApprovalOutcome,
    NetworkApprovalRejected,
    NetworkApprovalService,
    NetworkDecision,
    PendingApprovalDecision,
    PendingHostApproval,
    allows_network_approval_flow,
    begin_network_approval,
    finish_deferred_network_approval,
    finish_immediate_network_approval,
    network_approval_outcome_to_result,
    permission_profile_allows_network_approval_flow,
    plan_inline_network_policy_request,
    protocol_key_label,
)
from pycodex.core.network_approval import (
    ActiveNetworkApprovalCall,
    NetworkApprovalMode,
    NetworkApprovalSpec,
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

    def test_network_approval_dataclasses_reject_non_rust_shapes(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown network decision type"):
            NetworkDecision("ask")
        with self.assertRaisesRegex(ValueError, "allow decision cannot include reason"):
            NetworkDecision("allow", "because")
        with self.assertRaisesRegex(TypeError, "deny decision reason must be a string"):
            NetworkDecision.deny(123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "host must be a string"):
            HostApprovalKey(123, "https", 443)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "port must be an integer"):
            HostApprovalKey("example.com", "https", True)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "port must fit in u16"):
            HostApprovalKey("example.com", "https", 70000)
        with self.assertRaisesRegex(TypeError, "host must be a string"):
            HostApprovalKey.from_request({"host": 123, "port": 443}, NetworkApprovalProtocol.HTTPS)
        with self.assertRaisesRegex(TypeError, "port must be an integer"):
            HostApprovalKey.from_request({"host": "example.com", "port": "443"}, NetworkApprovalProtocol.HTTPS)
        with self.assertRaisesRegex(ValueError, "denied_by_user outcome cannot include message"):
            NetworkApprovalOutcome("denied_by_user", "no")
        with self.assertRaisesRegex(TypeError, "denied_by_policy message must be a string"):
            NetworkApprovalOutcome.denied_by_policy(123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "command must be a string"):
            NetworkApprovalSpec(None, NetworkApprovalMode.IMMEDIATE, {}, 123)  # type: ignore[arg-type]

        self.assertIs(NetworkApprovalSpec(None, "deferred", {}, "curl").mode, NetworkApprovalMode.DEFERRED)

        with self.assertRaisesRegex(TypeError, "cancellation_token must be a CancellationToken"):
            ActiveNetworkApprovalCall("reg", "turn", {}, "curl", object())  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "cancellation_token must be a CancellationToken"):
            ActiveNetworkApproval("reg", NetworkApprovalMode.IMMEDIATE, object())  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "cancellation_token must be a CancellationToken"):
            DeferredNetworkApproval("reg", object())  # type: ignore[arg-type]

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

    def test_begin_network_approval_registers_only_when_managed_network_is_active(self) -> None:
        service = NetworkApprovalService()
        spec = NetworkApprovalSpec(
            network={"proxy": True},
            mode=NetworkApprovalMode.IMMEDIATE,
            trigger={"kind": "command"},
            command="curl https://example.com",
        )

        self.assertIsNone(begin_network_approval(service, "turn-1", False, spec))
        self.assertIsNone(
            begin_network_approval(
                service,
                "turn-1",
                True,
                NetworkApprovalSpec(None, NetworkApprovalMode.IMMEDIATE, {}, "curl"),
            )
        )
        active = begin_network_approval(
            service,
            "turn-1",
            True,
            spec,
            registration_id="registration-1",
        )

        self.assertEqual(active.registration_id, "registration-1")
        self.assertIs(active.mode, NetworkApprovalMode.IMMEDIATE)
        self.assertIsNotNone(service.resolve_single_active_call())

    def test_finish_immediate_network_approval_consumes_call_outcome(self) -> None:
        service = NetworkApprovalService()
        active = begin_network_approval(
            service,
            "turn-1",
            True,
            NetworkApprovalSpec({"proxy": True}, NetworkApprovalMode.IMMEDIATE, {}, "curl"),
            registration_id="registration-1",
        )
        service.record_call_outcome(
            "registration-1",
            NetworkApprovalOutcome.denied_by_policy("blocked"),
        )

        with self.assertRaisesRegex(NetworkApprovalRejected, "blocked"):
            finish_immediate_network_approval(service, active)

        self.assertIsNone(service.resolve_single_active_call())

    def test_deferred_network_approval_finishes_only_once(self) -> None:
        service = NetworkApprovalService()
        active = begin_network_approval(
            service,
            "turn-1",
            True,
            NetworkApprovalSpec({"proxy": True}, NetworkApprovalMode.DEFERRED, {}, "curl"),
            registration_id="registration-1",
        )
        deferred = active.into_deferred()
        self.assertIsInstance(deferred, DeferredNetworkApproval)
        service.record_call_outcome(
            "registration-1",
            NetworkApprovalOutcome.denied_by_policy("blocked once"),
        )

        with self.assertRaisesRegex(NetworkApprovalRejected, "blocked once"):
            finish_deferred_network_approval(service, deferred)

        service.register_call("registration-1", "turn-2", {}, "curl")
        service.record_call_outcome(
            "registration-1",
            NetworkApprovalOutcome.denied_by_policy("blocked twice"),
        )
        with self.assertRaisesRegex(NetworkApprovalRejected, "blocked once"):
            finish_deferred_network_approval(service, deferred)

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
        with self.assertRaisesRegex(ValueError, "port must fit in u16"):
            NetworkApprovalService.format_network_target("https", "example.com", 70000)

        self.assertEqual(
            NetworkApprovalService.approval_id_for_key(key),
            "network#https#example.com#443",
        )

    def test_inline_network_policy_request_uses_session_caches_before_prompting(self) -> None:
        service = NetworkApprovalService()
        key = HostApprovalKey("example.com", "https", 443)
        request = {"host": "Example.COM", "port": 443}

        service.session_approved_hosts.add(key)
        approved = plan_inline_network_policy_request(
            service,
            request,
            NetworkApprovalProtocol.HTTPS,
            permission_profile=PermissionProfile.read_only(),
            approval_policy=AskForApproval.ON_REQUEST,
        )

        self.assertIs(approved.disposition, InlineNetworkApprovalDisposition.ALLOW_CACHED)
        self.assertEqual(approved.decision, NetworkDecision.allow())
        self.assertEqual(approved.approval_id, "network#https#example.com#443")
        self.assertEqual(approved.prompt_command, ("network-access", "https://Example.COM:443"))

        service.session_approved_hosts.clear()
        service.session_denied_hosts.add(key)
        denied = plan_inline_network_policy_request(
            service,
            request,
            NetworkApprovalProtocol.HTTPS,
            permission_profile=PermissionProfile.read_only(),
            approval_policy=AskForApproval.ON_REQUEST,
        )

        self.assertIs(denied.disposition, InlineNetworkApprovalDisposition.DENY_CACHED)
        self.assertEqual(denied.decision, NetworkDecision.deny(NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED))

    def test_inline_network_policy_request_denies_when_review_flow_is_unavailable(self) -> None:
        service = NetworkApprovalService()
        token = service.register_call("registration-1", "turn-1", {}, "curl https://example.com")

        plan = plan_inline_network_policy_request(
            service,
            {"host": "example.com", "port": 443},
            NetworkApprovalProtocol.HTTPS,
            permission_profile=PermissionProfile.disabled(),
            approval_policy=AskForApproval.ON_REQUEST,
        )

        self.assertIs(plan.disposition, InlineNetworkApprovalDisposition.DENY_POLICY)
        self.assertEqual(plan.decision, NetworkDecision.deny(NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED))
        self.assertEqual(plan.pending.decision, PendingApprovalDecision.DENY)
        self.assertTrue(token.is_cancelled())
        self.assertEqual(
            service.take_call_outcome("registration-1"),
            NetworkApprovalOutcome.denied_by_policy(
                'Network access to "https://example.com:443" was blocked by policy.'
            ),
        )

    def test_inline_network_policy_request_returns_review_plan_for_owner_and_waiters(self) -> None:
        service = NetworkApprovalService()
        request = {"host": "example.com", "port": 443}

        owner = plan_inline_network_policy_request(
            service,
            request,
            NetworkApprovalProtocol.HTTPS,
            permission_profile=PermissionProfile.workspace_write(),
            approval_policy=AskForApproval.ON_REQUEST,
        )
        waiter = plan_inline_network_policy_request(
            service,
            request,
            NetworkApprovalProtocol.HTTPS,
            permission_profile=PermissionProfile.workspace_write(),
            approval_policy=AskForApproval.ON_REQUEST,
        )

        self.assertIs(owner.disposition, InlineNetworkApprovalDisposition.REVIEW_REQUIRED)
        self.assertTrue(owner.pending_owner)
        self.assertIs(waiter.disposition, InlineNetworkApprovalDisposition.WAIT_FOR_PENDING)
        self.assertFalse(waiter.pending_owner)
        self.assertIs(waiter.pending, owner.pending)
        self.assertEqual(owner.prompt_reason, "example.com is not in the allowed_domains")

    def test_resolve_network_review_decision_maps_user_choices(self) -> None:
        from pycodex.core.network_approval import resolve_network_review_decision
        from pycodex.protocol.approvals import NetworkPolicyAmendment, NetworkPolicyRuleAction, ReviewDecision

        self.assertIs(
            resolve_network_review_decision(ReviewDecision.approved()).decision,
            PendingApprovalDecision.ALLOW_ONCE,
        )
        session = resolve_network_review_decision(ReviewDecision.approved_for_session())
        self.assertIs(session.decision, PendingApprovalDecision.ALLOW_FOR_SESSION)
        self.assertTrue(session.cache_approved_host)

        denied = resolve_network_review_decision(
            ReviewDecision.network_policy_amendment_decision(
                NetworkPolicyAmendment("example.com", NetworkPolicyRuleAction.DENY)
            )
        )
        self.assertIs(denied.decision, PendingApprovalDecision.DENY)
        self.assertTrue(denied.cache_denied_host)
        self.assertEqual(denied.outcome, NetworkApprovalOutcome.denied_by_user())

    def test_resolve_network_review_decision_maps_timeout_to_policy_denial(self) -> None:
        from pycodex.core.network_approval import resolve_network_review_decision
        from pycodex.protocol.approvals import ReviewDecision

        resolved = resolve_network_review_decision(ReviewDecision.timed_out())

        self.assertIs(resolved.decision, PendingApprovalDecision.DENY)
        self.assertEqual(
            resolved.outcome,
            NetworkApprovalOutcome.denied_by_policy("Network approval request timed out."),
        )

    def test_apply_network_review_decision_updates_pending_and_session_cache(self) -> None:
        from pycodex.core.network_approval import apply_network_review_decision
        from pycodex.protocol.approvals import NetworkPolicyAmendment, NetworkPolicyRuleAction, ReviewDecision

        service = NetworkApprovalService()
        key = HostApprovalKey("example.com", "https", 443)
        pending, _ = service.get_or_create_pending_approval(key)

        apply_network_review_decision(service, key, ReviewDecision.approved_for_session())

        self.assertIs(pending.decision, PendingApprovalDecision.ALLOW_FOR_SESSION)
        self.assertIn(key, service.session_approved_hosts)
        self.assertNotIn(key, service.session_denied_hosts)

        apply_network_review_decision(
            service,
            key,
            ReviewDecision.network_policy_amendment_decision(
                NetworkPolicyAmendment("example.com", NetworkPolicyRuleAction.DENY)
            ),
        )

        self.assertIs(pending.decision, PendingApprovalDecision.DENY)
        self.assertNotIn(key, service.session_approved_hosts)
        self.assertIn(key, service.session_denied_hosts)

    def test_apply_network_review_decision_records_call_outcome_for_denial(self) -> None:
        from pycodex.core.network_approval import apply_network_review_decision
        from pycodex.protocol.approvals import ReviewDecision

        service = NetworkApprovalService()
        key = HostApprovalKey("example.com", "https", 443)
        service.register_call("registration-1", "turn-1", {}, "curl https://example.com")

        apply_network_review_decision(
            service,
            key,
            ReviewDecision.abort(),
            registration_id="registration-1",
        )

        self.assertEqual(
            service.take_call_outcome("registration-1"),
            NetworkApprovalOutcome.denied_by_user(),
        )


if __name__ == "__main__":
    unittest.main()
