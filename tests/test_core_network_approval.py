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
from pycodex.core.tools.network_approval import (
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

    def test_protocol_key_label_rejects_invalid_protocol_type(self) -> None:
        with self.assertRaisesRegex(TypeError, "protocol must be a NetworkApprovalProtocol or string"):
            protocol_key_label(123)  # type: ignore[arg-type]

    def test_protocol_key_label_rejects_invalid_protocol_string(self) -> None:
        with self.assertRaises(ValueError):
            protocol_key_label("sftp")

    def test_host_approval_key_from_request_can_read_object_fields(self) -> None:
        class Request:
            def __init__(self) -> None:
                self.host = "ObjectHost.COM"
                self.port = 8080

        key = HostApprovalKey.from_request(Request(), NetworkApprovalProtocol.HTTP)
        self.assertEqual(key, HostApprovalKey("objecthost.com", "http", 8080))

    def test_host_approval_key_from_request_mapping_missing_field_raises_keyerror(self) -> None:
        with self.assertRaises(KeyError):
            HostApprovalKey.from_request({"port": 443}, NetworkApprovalProtocol.HTTPS)

    def test_host_approval_key_from_request_object_missing_field_raises_attributeerror(self) -> None:
        class Request:
            def __init__(self) -> None:
                self.port = 443

        with self.assertRaises(AttributeError):
            HostApprovalKey.from_request(Request(), NetworkApprovalProtocol.HTTPS)

    def test_host_approval_key_from_request_rejects_non_string_host_type(self) -> None:
        class Request:
            def __init__(self) -> None:
                self.host = 123
                self.port = 443

        with self.assertRaisesRegex(TypeError, "host must be a string"):
            HostApprovalKey.from_request({"host": 123, "port": 443}, NetworkApprovalProtocol.HTTPS)
        with self.assertRaisesRegex(TypeError, "host must be a string"):
            HostApprovalKey.from_request(Request(), NetworkApprovalProtocol.HTTPS)

    def test_host_approval_key_from_request_rejects_non_integer_port_type(self) -> None:
        class Request:
            def __init__(self) -> None:
                self.host = "example.com"
                self.port = True

        with self.assertRaisesRegex(TypeError, "port must be an integer"):
            HostApprovalKey.from_request({"host": "example.com", "port": "443"}, NetworkApprovalProtocol.HTTPS)
        with self.assertRaisesRegex(TypeError, "port must be an integer"):
            HostApprovalKey.from_request(Request(), NetworkApprovalProtocol.HTTPS)
        with self.assertRaisesRegex(TypeError, "port must be an integer"):
            HostApprovalKey.from_request({"host": "example.com", "port": 443.1}, NetworkApprovalProtocol.HTTPS)

    def test_register_call_with_existing_registration_id_overwrites_previous_call(self) -> None:
        service = NetworkApprovalService()
        token_1 = service.register_call("registration-1", "turn-1", {"call": 1}, "cmd-1")
        token_2 = service.register_call("registration-1", "turn-2", {"call": 2}, "cmd-2")
        call = service.resolve_single_active_call()

        self.assertEqual(token_1.__class__.__name__, "CancellationToken")
        self.assertEqual(token_2.__class__.__name__, "CancellationToken")
        self.assertIsNotNone(call)
        self.assertEqual(call.turn_id, "turn-2")
        self.assertEqual(call.command, "cmd-2")
        self.assertEqual(call.trigger, {"call": 2})

    def test_register_call_replaces_existing_registration_without_cancelling_old_token(self) -> None:
        service = NetworkApprovalService()
        old_token = CancellationToken()
        new_token = CancellationToken()

        service.register_call("registration-1", "turn-1", {"call": 1}, "cmd-1", old_token)
        service.register_call("registration-1", "turn-2", {"call": 2}, "cmd-2", new_token)

        self.assertIs(service.active_calls["registration-1"].cancellation_token, new_token)
        self.assertFalse(old_token.is_cancelled())

    def test_register_call_reuse_keeps_previous_registration_outcome(self) -> None:
        service = NetworkApprovalService()
        old_token = CancellationToken()
        new_token = CancellationToken()
        old_outcome = NetworkApprovalOutcome.denied_by_policy("previous call denied")

        service.register_call("registration-1", "turn-1", {"call": 1}, "cmd-1", old_token)
        service.record_call_outcome("registration-1", old_outcome)
        service.register_call("registration-1", "turn-2", {"call": 2}, "cmd-2", new_token)

        self.assertIs(service.active_calls["registration-1"].cancellation_token, new_token)
        self.assertTrue(old_token.is_cancelled())
        self.assertFalse(new_token.is_cancelled())
        self.assertEqual(service.take_call_outcome("registration-1"), old_outcome)

    def test_finish_call_after_registration_reuse_consumes_previous_outcome(self) -> None:
        service = NetworkApprovalService()
        old_token = CancellationToken()
        new_token = CancellationToken()

        service.register_call("registration-1", "turn-1", {"call": 1}, "cmd-1", old_token)
        service.record_call_outcome(
            "registration-1",
            NetworkApprovalOutcome.denied_by_user(),
        )
        service.register_call("registration-1", "turn-2", {"call": 2}, "cmd-2", new_token)

        with self.assertRaisesRegex(NetworkApprovalRejected, "rejected by user"):
            service.finish_call("registration-1")

        self.assertFalse(new_token.is_cancelled())
        self.assertIsNone(service.take_call_outcome("registration-1"))

    def test_record_call_outcome_can_override_reused_registration_outcome(self) -> None:
        service = NetworkApprovalService()
        old_token = CancellationToken()
        new_token = CancellationToken()

        service.register_call("registration-1", "turn-1", {"call": 1}, "cmd-1", old_token)
        service.record_call_outcome(
            "registration-1",
            NetworkApprovalOutcome.denied_by_policy("old blocked"),
        )
        service.register_call("registration-1", "turn-2", {"call": 2}, "cmd-2", new_token)
        service.record_call_outcome(
            "registration-1",
            NetworkApprovalOutcome.denied_by_policy("new blocked"),
        )

        with self.assertRaisesRegex(NetworkApprovalRejected, "new blocked"):
            service.finish_call("registration-1")
        self.assertIsNone(service.take_call_outcome("registration-1"))

    def test_register_call_validates_types(self) -> None:
        service = NetworkApprovalService()
        custom_token = CancellationToken()

        with self.assertRaisesRegex(TypeError, "registration_id must be a string"):
            service.register_call(123, "turn-1", {}, "cmd")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "turn_id must be a string"):
            service.register_call("registration-1", 123, {}, "cmd")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "command must be a string"):
            service.register_call("registration-1", "turn-1", {}, 123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "cancellation_token must be a CancellationToken"):
            service.register_call("registration-1", "turn-1", {}, "cmd", 123)  # type: ignore[arg-type]

    def test_register_call_uses_provided_cancellation_token(self) -> None:
        service = NetworkApprovalService()
        token = CancellationToken()

        returned = service.register_call("registration-1", "turn-1", {}, "cmd", token)
        call = service.active_calls["registration-1"]

        self.assertIs(returned, token)
        self.assertIs(call.cancellation_token, token)

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

    def test_session_approved_hosts_preserve_protocol_and_port_scope(self) -> None:
        source = NetworkApprovalService()
        source.session_approved_hosts.update(
            {
                HostApprovalKey("example.com", "https", 443),
                HostApprovalKey("example.com", "https", 8443),
                HostApprovalKey("example.com", "http", 80),
            }
        )
        seeded = NetworkApprovalService()
        source.sync_session_approved_hosts_to(seeded)

        self.assertEqual(
            sorted(
                list(seeded.session_approved_hosts),
                key=lambda k: (k.host, k.protocol, k.port),
            ),
            [
                HostApprovalKey("example.com", "http", 80),
                HostApprovalKey("example.com", "https", 443),
                HostApprovalKey("example.com", "https", 8443),
            ],
        )

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

    def test_allows_network_approval_flow_rejects_invalid_policy_type(self) -> None:
        with self.assertRaisesRegex(
            TypeError,
            "approval_policy must be an AskForApproval or string",
        ):
            allows_network_approval_flow(123)  # type: ignore[arg-type]

    def test_network_approval_flow_is_limited_to_managed_permission_profiles(self) -> None:
        self.assertTrue(permission_profile_allows_network_approval_flow(PermissionProfile.read_only()))
        self.assertTrue(permission_profile_allows_network_approval_flow(PermissionProfile.workspace_write()))
        self.assertFalse(permission_profile_allows_network_approval_flow(PermissionProfile.disabled()))
        self.assertFalse(
            permission_profile_allows_network_approval_flow(
                PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED)
            )
        )

    def test_permission_profile_allows_network_approval_flow_rejects_invalid_profile(self) -> None:
        with self.assertRaisesRegex(TypeError, "permission_profile must be a PermissionProfile"):
            permission_profile_allows_network_approval_flow("disabled")

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

    def test_begin_network_approval_reuses_registration_id_and_replaces_call_state(self) -> None:
        service = NetworkApprovalService()
        first = begin_network_approval(
            service,
            "turn-1",
            True,
            NetworkApprovalSpec({"proxy": True}, NetworkApprovalMode.IMMEDIATE, {}, "curl https://example.com"),
            registration_id="registration-1",
        )

        second = begin_network_approval(
            service,
            "turn-2",
            True,
            NetworkApprovalSpec({"proxy": True}, NetworkApprovalMode.IMMEDIATE, {}, "curl https://example.org"),
            registration_id="registration-1",
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(second.registration_id, "registration-1")
        self.assertIsNot(first.cancellation_token, second.cancellation_token)
        self.assertFalse(first.cancellation_token.is_cancelled())

        call = service.resolve_single_active_call()
        self.assertIsNotNone(call)
        if call is not None:
            self.assertEqual(call.turn_id, "turn-2")
            self.assertEqual(call.command, "curl https://example.org")

    def test_resolve_single_active_call_requires_single_owner(self) -> None:
        service = NetworkApprovalService()
        service.register_call("registration-1", "turn-1", {}, "curl https://example.com")
        service.register_call("registration-2", "turn-2", {}, "curl https://example.org")

        self.assertIsNone(service.resolve_single_active_call())

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

    def test_finish_immediate_network_approval_noop_without_registration_id(self) -> None:
        service = NetworkApprovalService()
        active = ActiveNetworkApproval(None, NetworkApprovalMode.IMMEDIATE, CancellationToken())

        finish_immediate_network_approval(service, active)

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

    def test_deferred_finish_reuses_denial_result_after_first_consumer(self) -> None:
        service = NetworkApprovalService()
        token = service.register_call("registration-1", "turn-1", {}, "curl https://example.com")
        deferred = DeferredNetworkApproval("registration-1", token)
        service.record_call_outcome(
            "registration-1",
            NetworkApprovalOutcome.denied_by_policy("network denied"),
        )

        with self.assertRaisesRegex(NetworkApprovalRejected, "network denied"):
            deferred.finish(service)
        with self.assertRaisesRegex(NetworkApprovalRejected, "network denied"):
            deferred.finish(service)

    def test_deferred_finish_noop_without_recorded_outcome(self) -> None:
        service = NetworkApprovalService()
        token = service.register_call("registration-1", "turn-1", {}, "curl https://example.com")
        deferred = DeferredNetworkApproval("registration-1", token)

        deferred.finish(service)
        self.assertIsNone(service.take_call_outcome("registration-1"))

    def test_finish_deferred_network_approval_noop_when_registration_missing(self) -> None:
        service = NetworkApprovalService()
        token = service.register_call("registration-1", "turn-1", {}, "curl https://example.com")
        service.unregister_call("registration-1")

        finish_deferred_network_approval(service, DeferredNetworkApproval("registration-1", token))

    def test_finish_deferred_network_approval_rejects_invalid_deferred_type(self) -> None:
        service = NetworkApprovalService()
        with self.assertRaisesRegex(TypeError, "deferred must be DeferredNetworkApproval or None"):
            finish_deferred_network_approval(service, 123)  # type: ignore[arg-type]

    def test_finish_deferred_network_approval_allows_none(self) -> None:
        service = NetworkApprovalService()
        finish_deferred_network_approval(service, None)

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

    def test_record_call_outcome_does_not_override_user_denial(self) -> None:
        service = NetworkApprovalService()
        service.register_call("registration-1", "turn-1", {}, "curl https://example.com")
        service.record_call_outcome(
            "registration-1",
            NetworkApprovalOutcome.denied_by_user(),
        )
        service.record_call_outcome(
            "registration-1",
            NetworkApprovalOutcome.denied_by_policy("network denied"),
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

    def test_finish_call_outcome_returns_none_for_missing_registration(self) -> None:
        service = NetworkApprovalService()
        service.register_call("registration-1", "turn-1", {}, "curl")
        service.unregister_call("registration-1")

        self.assertIsNone(service.finish_call_outcome("registration-1"))

    def test_finish_call_does_nothing_on_missing_outcome(self) -> None:
        service = NetworkApprovalService()
        service.register_call("registration-1", "turn-1", {}, "curl")

        service.finish_call("registration-1")

        self.assertIsNone(service.take_call_outcome("registration-1"))

    def test_remove_call_is_noop_for_unknown_registration(self) -> None:
        service = NetworkApprovalService()

        self.assertIsNone(service.remove_call("registration-missing"))

    def test_unregister_call_is_noop_for_unknown_registration(self) -> None:
        service = NetworkApprovalService()

        service.unregister_call("registration-missing")

        self.assertIsNone(service.resolve_single_active_call())

    def test_unregister_call_removes_target_outcome_but_keeps_other_calls(self) -> None:
        service = NetworkApprovalService()
        service.register_call("registration-1", "turn-1", {"call": 1}, "cmd-1")
        service.register_call("registration-2", "turn-2", {"call": 2}, "cmd-2")
        service.record_call_outcome(
            "registration-1",
            NetworkApprovalOutcome.denied_by_policy("blocked one"),
        )
        service.record_call_outcome(
            "registration-2",
            NetworkApprovalOutcome.denied_by_user(),
        )

        service.unregister_call("registration-1")

        self.assertIsNone(service.active_calls.get("registration-1"))
        self.assertIsNone(service.take_call_outcome("registration-1"))
        self.assertIn("registration-2", service.active_calls)
        with self.assertRaisesRegex(NetworkApprovalRejected, "rejected by user"):
            service.finish_call("registration-2")
        self.assertIsNone(service.active_calls.get("registration-2"))

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

    def test_finish_call_only_consumes_target_registration(self) -> None:
        service = NetworkApprovalService()
        service.register_call("registration-1", "turn-1", {}, "curl https://example.com")
        service.register_call("registration-2", "turn-2", {}, "curl https://example.org")

        service.record_call_outcome(
            "registration-1",
            NetworkApprovalOutcome.denied_by_policy("registration one blocked"),
        )

        with self.assertRaisesRegex(NetworkApprovalRejected, "registration one blocked"):
            service.finish_call("registration-1")

        self.assertIsNone(service.take_call_outcome("registration-1"))
        self.assertIsNotNone(service.resolve_single_active_call())
        self.assertIsNotNone(service.active_calls.get("registration-2"))

    def test_finish_call_unknown_registration_removes_no_active_calls(self) -> None:
        service = NetworkApprovalService()
        service.register_call("registration-1", "turn-1", {}, "curl https://example.com")
        token = service.active_calls["registration-1"].cancellation_token

        self.assertIsNone(service.finish_call_outcome("missing"))
        self.assertIsNotNone(service.active_calls.get("registration-1"))
        self.assertFalse(token.is_cancelled())

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

    def test_inline_network_policy_request_prefers_cached_deny_over_cached_allow(self) -> None:
        service = NetworkApprovalService()
        key = HostApprovalKey("example.com", "https", 443)
        request = {"host": "Example.COM", "port": 443}

        service.session_approved_hosts.add(key)
        service.session_denied_hosts.add(key)

        plan = plan_inline_network_policy_request(
            service,
            request,
            NetworkApprovalProtocol.HTTPS,
            permission_profile=PermissionProfile.read_only(),
            approval_policy=AskForApproval.ON_REQUEST,
        )

        self.assertIs(plan.disposition, InlineNetworkApprovalDisposition.DENY_CACHED)
        self.assertEqual(plan.decision, NetworkDecision.deny(NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED))
        self.assertEqual(plan.approval_id, "network#https#example.com#443")
        self.assertEqual(plan.prompt_reason, "example.com is not in the allowed_domains")
        self.assertEqual(plan.target, "https://example.com:443")
        self.assertEqual(plan.pending, None)

    def test_inline_network_policy_request_denies_removes_pending_entry_on_gate_rejection(self) -> None:
        service = NetworkApprovalService()
        request = {"host": "example.com", "port": 443}
        key = HostApprovalKey.from_request(request, NetworkApprovalProtocol.HTTPS)

        owner = plan_inline_network_policy_request(
            service,
            request,
            NetworkApprovalProtocol.HTTPS,
            permission_profile=PermissionProfile.workspace_write(),
            approval_policy=AskForApproval.ON_REQUEST,
        )
        self.assertTrue(owner.pending_owner)
        self.assertIn(key, service.pending_host_approvals)

        denied = plan_inline_network_policy_request(
            service,
            request,
            NetworkApprovalProtocol.HTTPS,
            permission_profile=None,
            approval_policy=AskForApproval.ON_REQUEST,
        )

        self.assertIs(denied.disposition, InlineNetworkApprovalDisposition.DENY_POLICY)
        self.assertIsNotNone(denied.pending)
        self.assertIs(denied.pending.decision, PendingApprovalDecision.DENY)
        self.assertFalse(service.pending_host_approvals)
        self.assertIsNot(denied.pending, owner.pending)

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

    def test_inline_network_policy_request_denies_when_review_flow_set_to_never(self) -> None:
        service = NetworkApprovalService()

        denied = plan_inline_network_policy_request(
            service,
            {"host": "example.com", "port": 443},
            NetworkApprovalProtocol.HTTPS,
            permission_profile=PermissionProfile.read_only(),
            approval_policy=AskForApproval.NEVER,
        )

        self.assertIs(denied.disposition, InlineNetworkApprovalDisposition.DENY_POLICY)
        self.assertEqual(denied.decision, NetworkDecision.deny(NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED))
        self.assertEqual(denied.pending.decision, PendingApprovalDecision.DENY)
        self.assertFalse(service.pending_host_approvals)

    def test_inline_network_policy_request_denies_when_permission_profile_and_policy_block(self) -> None:
        service = NetworkApprovalService()

        plan = plan_inline_network_policy_request(
            service,
            {"host": "example.com", "port": 443},
            NetworkApprovalProtocol.HTTPS,
            permission_profile=PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED),
            approval_policy=AskForApproval.NEVER,
        )

        self.assertIs(plan.disposition, InlineNetworkApprovalDisposition.DENY_POLICY)
        self.assertEqual(plan.decision, NetworkDecision.deny(NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED))
        self.assertIsNotNone(plan.pending)
        if plan.pending is not None:
            self.assertEqual(plan.pending.decision, PendingApprovalDecision.DENY)
        self.assertFalse(service.pending_host_approvals)

    def test_inline_network_policy_request_rejects_invalid_protocol_type(self) -> None:
        service = NetworkApprovalService()

        with self.assertRaisesRegex(
            TypeError,
            "protocol must be a NetworkApprovalProtocol or string",
        ):
            plan_inline_network_policy_request(
                service,
                {"host": "example.com", "port": 443},
                123,  # type: ignore[arg-type]
                permission_profile=PermissionProfile.read_only(),
                approval_policy=AskForApproval.ON_REQUEST,
            )

    def test_inline_network_policy_request_rejects_invalid_protocol_string(self) -> None:
        service = NetworkApprovalService()

        with self.assertRaises(ValueError):
            plan_inline_network_policy_request(
                service,
                {"host": "example.com", "port": 443},
                "ftp",
                permission_profile=PermissionProfile.read_only(),
                approval_policy=AskForApproval.ON_REQUEST,
            )

    def test_inline_network_policy_request_rejects_invalid_permission_profile_type(self) -> None:
        service = NetworkApprovalService()

        with self.assertRaisesRegex(
            TypeError,
            "permission_profile must be a PermissionProfile",
        ):
            plan_inline_network_policy_request(
                service,
                {"host": "example.com", "port": 443},
                NetworkApprovalProtocol.HTTPS,
                permission_profile="managed",  # type: ignore[arg-type]
                approval_policy=AskForApproval.ON_REQUEST,
            )

    def test_inline_network_policy_request_rejects_invalid_approval_policy_type(self) -> None:
        service = NetworkApprovalService()

        with self.assertRaises(ValueError):
            plan_inline_network_policy_request(
                service,
                {"host": "example.com", "port": 443},
                NetworkApprovalProtocol.HTTPS,
                permission_profile=PermissionProfile.read_only(),
                approval_policy="never-maybe",  # type: ignore[arg-type]
            )

        with self.assertRaises(TypeError):
            plan_inline_network_policy_request(
                service,
                {"host": "example.com", "port": 443},
                NetworkApprovalProtocol.HTTPS,
                permission_profile=PermissionProfile.read_only(),
                approval_policy=123,  # type: ignore[arg-type]
            )

    def test_inline_network_policy_request_rejects_invalid_request_type(self) -> None:
        service = NetworkApprovalService()

        with self.assertRaisesRegex(
            TypeError,
            "request must be a mapping or object with host and port attributes",
        ):
            plan_inline_network_policy_request(
                service,
                123,  # type: ignore[arg-type]
                NetworkApprovalProtocol.HTTPS,
                permission_profile=PermissionProfile.read_only(),
                approval_policy=AskForApproval.ON_REQUEST,
            )

    def test_inline_network_policy_request_denies_when_review_flow_is_unavailable_without_active_call(self) -> None:
        service = NetworkApprovalService()
        key = HostApprovalKey.from_request({"host": "example.com", "port": 443}, NetworkApprovalProtocol.HTTPS)
        pending, _ = service.get_or_create_pending_approval(key)
        self.assertIsNotNone(pending)

        plan = plan_inline_network_policy_request(
            service,
            {"host": "example.com", "port": 443},
            NetworkApprovalProtocol.HTTPS,
            permission_profile=None,
            approval_policy=AskForApproval.ON_REQUEST,
        )

        self.assertIs(plan.disposition, InlineNetworkApprovalDisposition.DENY_POLICY)
        self.assertEqual(plan.decision, NetworkDecision.deny(NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED))
        self.assertIsNotNone(plan.pending)
        if plan.pending is not None:
            self.assertEqual(plan.pending.decision, PendingApprovalDecision.DENY)
        self.assertFalse(service.pending_host_approvals)

    def test_begin_network_approval_rejects_invalid_arguments(self) -> None:
        service = NetworkApprovalService()
        spec = NetworkApprovalSpec({"proxy": True}, NetworkApprovalMode.IMMEDIATE, {}, "curl https://example.com")

        with self.assertRaisesRegex(TypeError, "service must be a NetworkApprovalService"):
            begin_network_approval(123, "turn-1", True, spec)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "turn_id must be a string"):
            begin_network_approval(service, 123, True, spec)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "managed_network_active must be a bool"):
            begin_network_approval(service, "turn-1", "true", spec)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "spec must be NetworkApprovalSpec or None"):
            begin_network_approval(service, "turn-1", True, True)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "registration_id must be a string"):
            begin_network_approval(
                service,
                "turn-1",
                True,
                spec,
                registration_id=123,  # type: ignore[arg-type]
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
        from pycodex.core.tools.network_approval import resolve_network_review_decision
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
        from pycodex.core.tools.network_approval import resolve_network_review_decision
        from pycodex.protocol.approvals import ReviewDecision

        resolved = resolve_network_review_decision(ReviewDecision.timed_out())

        self.assertIs(resolved.decision, PendingApprovalDecision.DENY)
        self.assertEqual(
            resolved.outcome,
            NetworkApprovalOutcome.denied_by_policy("Network approval request timed out."),
        )

    def test_resolve_network_review_decision_rejects_unknown_type(self) -> None:
        from pycodex.core.tools.network_approval import resolve_network_review_decision

        with self.assertRaisesRegex(ValueError, "unknown review decision: mystery"):
            resolve_network_review_decision({"mystery": {}})

    def test_resolve_network_review_decision_rejects_invalid_shape(self) -> None:
        from pycodex.core.tools.network_approval import resolve_network_review_decision

        with self.assertRaisesRegex(TypeError, "review decision must be a mapping, review decision, or string"):
            resolve_network_review_decision(123)  # type: ignore[arg-type]

    def test_resolve_network_review_decision_accepts_wire_string_denied(self) -> None:
        from pycodex.core.tools.network_approval import resolve_network_review_decision

        resolved = resolve_network_review_decision("denied")
        self.assertIs(resolved.decision, PendingApprovalDecision.DENY)
        self.assertEqual(resolved.outcome, NetworkApprovalOutcome.denied_by_user())

    def test_resolve_network_review_decision_accepts_review_decision_instance(self) -> None:
        from pycodex.core.tools.network_approval import resolve_network_review_decision
        from pycodex.protocol.approvals import ReviewDecision

        resolved = resolve_network_review_decision(ReviewDecision.approved_for_session())
        self.assertIs(resolved.decision, PendingApprovalDecision.ALLOW_FOR_SESSION)
        self.assertTrue(resolved.cache_approved_host)

    def test_resolve_network_review_decision_accepts_wire_string(self) -> None:
        from pycodex.core.tools.network_approval import resolve_network_review_decision

        resolved = resolve_network_review_decision("approved")
        self.assertIs(resolved.decision, PendingApprovalDecision.ALLOW_ONCE)

    def test_apply_network_review_decision_type_guards(self) -> None:
        from pycodex.core.tools.network_approval import apply_network_review_decision
        from pycodex.protocol.approvals import ReviewDecision

        service = NetworkApprovalService()
        key = HostApprovalKey("example.com", "https", 443)

        with self.assertRaisesRegex(TypeError, "service must be a NetworkApprovalService"):
            apply_network_review_decision(123, key, ReviewDecision.approved())  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "key must be a HostApprovalKey"):
            apply_network_review_decision(service, "example", ReviewDecision.approved())  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "registration_id must be a string"):
            apply_network_review_decision(
                service,
                key,
                ReviewDecision.approved(),
                registration_id=123,  # type: ignore[arg-type]
            )

    def test_apply_network_review_decision_updates_pending_and_session_cache(self) -> None:
        from pycodex.core.tools.network_approval import apply_network_review_decision
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
        self.assertNotIn(key, service.pending_host_approvals)

    def test_apply_network_review_decision_caches_allow_amendment_and_clears_pending(self) -> None:
        from pycodex.core.tools.network_approval import apply_network_review_decision
        from pycodex.protocol.approvals import NetworkPolicyAmendment, NetworkPolicyRuleAction, ReviewDecision

        service = NetworkApprovalService()
        key = HostApprovalKey("example.com", "https", 443)
        service.session_denied_hosts.add(key)
        pending, _ = service.get_or_create_pending_approval(key)

        resolution = apply_network_review_decision(
            service,
            key,
            ReviewDecision.network_policy_amendment_decision(
                NetworkPolicyAmendment("example.com", NetworkPolicyRuleAction.ALLOW)
            ),
        )

        self.assertIs(resolution.decision, PendingApprovalDecision.ALLOW_FOR_SESSION)
        self.assertIs(pending.decision, PendingApprovalDecision.ALLOW_FOR_SESSION)
        self.assertIn(key, service.session_approved_hosts)
        self.assertNotIn(key, service.session_denied_hosts)
        self.assertNotIn(key, service.pending_host_approvals)

    def test_apply_network_review_decision_records_call_outcome_for_denial(self) -> None:
        from pycodex.core.tools.network_approval import apply_network_review_decision
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

    def test_apply_network_review_decision_allow_does_not_record_outcome(self) -> None:
        from pycodex.core.tools.network_approval import apply_network_review_decision
        from pycodex.protocol.approvals import ReviewDecision

        service = NetworkApprovalService()
        key = HostApprovalKey("example.com", "https", 443)
        service.register_call("registration-1", "turn-1", {}, "curl https://example.com")

        apply_network_review_decision(
            service,
            key,
            ReviewDecision.approved(),
            registration_id="registration-1",
        )

        self.assertIsNone(service.take_call_outcome("registration-1"))

    def test_apply_network_review_decision_updates_session_caches_without_pending(self) -> None:
        from pycodex.core.tools.network_approval import apply_network_review_decision
        from pycodex.protocol.approvals import NetworkPolicyAmendment, NetworkPolicyRuleAction, ReviewDecision

        service = NetworkApprovalService()
        key = HostApprovalKey("Example.Com", "https", 443)

        apply_network_review_decision(
            service,
            key,
            ReviewDecision.network_policy_amendment_decision(
                NetworkPolicyAmendment("Example.Com", NetworkPolicyRuleAction.ALLOW)
            ),
        )
        self.assertIn(key, service.session_approved_hosts)
        self.assertNotIn(key, service.session_denied_hosts)

        apply_network_review_decision(
            service,
            key,
            ReviewDecision.network_policy_amendment_decision(
                NetworkPolicyAmendment("Example.Com", NetworkPolicyRuleAction.DENY)
            ),
        )
        self.assertNotIn(key, service.session_approved_hosts)
        self.assertIn(key, service.session_denied_hosts)
        self.assertNotIn(key, service.pending_host_approvals)


if __name__ == "__main__":
    unittest.main()
