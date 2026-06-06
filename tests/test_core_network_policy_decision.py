import unittest

from pycodex.execpolicy import (
    Decision,
)
from pycodex.core import (
    BlockedRequest,
    ExecPolicyNetworkRuleAmendment,
    ExecPolicyNetworkRuleProtocol,
    denied_network_policy_message,
    execpolicy_network_rule_amendment,
    network_approval_context_from_payload,
    parse_network_policy_decision,
)
from pycodex.protocol import (
    NetworkApprovalContext,
    NetworkApprovalProtocol,
    NetworkDecisionSource,
    NetworkPolicyAmendment,
    NetworkPolicyDecision,
    NetworkPolicyDecisionPayload,
    NetworkPolicyRuleAction,
)


class CoreNetworkPolicyDecisionTests(unittest.TestCase):
    # Rust source:
    # codex/codex-rs/core/src/network_policy_decision.rs
    # Rust tests:
    # codex/codex-rs/core/src/network_policy_decision_tests.rs

    def test_network_approval_context_requires_ask_from_decider(self) -> None:
        # Rust test: network_approval_context_requires_ask_from_decider
        payload = NetworkPolicyDecisionPayload(
            decision=NetworkPolicyDecision.DENY,
            source=NetworkDecisionSource.DECIDER,
            protocol=NetworkApprovalProtocol.HTTPS,
            host="example.com",
            reason="not_allowed",
            port=443,
        )

        self.assertIsNone(network_approval_context_from_payload(payload))

    def test_network_approval_context_maps_http_https_and_socks_protocols(self) -> None:
        # Rust test: network_approval_context_maps_http_https_and_socks_protocols
        for protocol in (
            NetworkApprovalProtocol.HTTP,
            NetworkApprovalProtocol.HTTPS,
            NetworkApprovalProtocol.SOCKS5_TCP,
            NetworkApprovalProtocol.SOCKS5_UDP,
        ):
            with self.subTest(protocol=protocol):
                payload = NetworkPolicyDecisionPayload(
                    decision=NetworkPolicyDecision.ASK,
                    source=NetworkDecisionSource.DECIDER,
                    protocol=protocol,
                    host=" example.com ",
                    reason="not_allowed",
                    port=443,
                )

                self.assertEqual(
                    network_approval_context_from_payload(payload),
                    NetworkApprovalContext(host="example.com", protocol=protocol),
                )

    def test_network_policy_decision_payload_deserializes_proxy_protocol_aliases(self) -> None:
        # Rust test: network_policy_decision_payload_deserializes_proxy_protocol_aliases
        for protocol_alias in ("https_connect", "http-connect"):
            with self.subTest(protocol_alias=protocol_alias):
                context = network_approval_context_from_payload(
                    {
                        "decision": "ask",
                        "source": "decider",
                        "protocol": protocol_alias,
                        "host": "example.com",
                        "reason": "not_allowed",
                        "port": 443,
                    }
                )

                self.assertEqual(
                    context,
                    NetworkApprovalContext("example.com", NetworkApprovalProtocol.HTTPS),
                )

    def test_network_approval_context_rejects_missing_protocol_or_host(self) -> None:
        base = {
            "decision": "ask",
            "source": "decider",
            "reason": "not_allowed",
            "port": 443,
        }

        self.assertIsNone(network_approval_context_from_payload({**base, "host": "example.com"}))
        self.assertIsNone(
            network_approval_context_from_payload(
                {**base, "protocol": "https", "host": "   "}
            )
        )

    def test_network_policy_decision_parse_accepts_known_values_only(self) -> None:
        self.assertEqual(parse_network_policy_decision("deny"), NetworkPolicyDecision.DENY)
        self.assertEqual(parse_network_policy_decision("ask"), NetworkPolicyDecision.ASK)
        self.assertIsNone(parse_network_policy_decision("allow"))
        self.assertIsNone(parse_network_policy_decision(None))

        with self.assertRaisesRegex(TypeError, "value must be a string"):
            parse_network_policy_decision(1)  # type: ignore[arg-type]

    def test_execpolicy_network_rule_amendment_maps_protocol_action_and_justification(self) -> None:
        # Rust test: execpolicy_network_rule_amendment_maps_protocol_action_and_justification
        amendment = NetworkPolicyAmendment("example.com", NetworkPolicyRuleAction.DENY)
        context = NetworkApprovalContext(
            host="example.com",
            protocol=NetworkApprovalProtocol.SOCKS5_UDP,
        )

        self.assertEqual(
            execpolicy_network_rule_amendment(amendment, context, "example.com"),
            ExecPolicyNetworkRuleAmendment(
                protocol=ExecPolicyNetworkRuleProtocol.SOCKS5_UDP,
                decision=Decision.FORBIDDEN,
                justification="Deny socks5_udp access to example.com",
            ),
        )

    def test_execpolicy_network_rule_amendment_uses_https_connect_label(self) -> None:
        amendment = NetworkPolicyAmendment("example.com", NetworkPolicyRuleAction.ALLOW)
        context = NetworkApprovalContext(
            host="example.com",
            protocol=NetworkApprovalProtocol.HTTPS,
        )

        self.assertEqual(
            execpolicy_network_rule_amendment(amendment, context, "api.example.com"),
            ExecPolicyNetworkRuleAmendment(
                protocol=ExecPolicyNetworkRuleProtocol.HTTPS,
                decision=Decision.ALLOW,
                justification="Allow https_connect access to api.example.com",
            ),
        )

    def test_denied_network_policy_message_requires_deny_decision(self) -> None:
        # Rust test: denied_network_policy_message_requires_deny_decision
        blocked = BlockedRequest(
            host="example.com",
            reason="not_allowed",
            method="GET",
            protocol="http",
            decision="ask",
            source="decider",
            port=80,
        )

        self.assertIsNone(denied_network_policy_message(blocked))

    def test_denied_network_policy_message_for_known_reasons(self) -> None:
        # Rust tests:
        # - denied_network_policy_message_for_denylist_block_is_explicit
        # - source behavior in denied_network_policy_message
        cases = {
            "denied": "domain is explicitly denied by policy and cannot be approved from this prompt",
            "not_allowed": "domain is not on the allowlist for the current sandbox mode",
            "not_allowed_local": "local/private network addresses are blocked by the sandbox policy",
            "method_not_allowed": "request method is blocked by the current network mode",
            "proxy_disabled": "network proxy is disabled",
            "other": "request is blocked by network policy",
        }

        for reason, detail in cases.items():
            with self.subTest(reason=reason):
                self.assertEqual(
                    denied_network_policy_message(
                        BlockedRequest(
                            host="example.com",
                            reason=reason,
                            protocol="http",
                            decision="deny",
                        )
                    ),
                    f'Network access to "example.com" was blocked: {detail}.',
                )

    def test_denied_network_policy_message_handles_empty_host_and_mapping_input(self) -> None:
        self.assertEqual(
            denied_network_policy_message(
                {
                    "host": "   ",
                    "reason": "not_allowed",
                    "protocol": "http",
                    "decision": "deny",
                    "timestamp": 0,
                }
            ),
            "Network access was blocked by policy.",
        )

    def test_blocked_request_mapping_round_trip_preserves_optional_fields(self) -> None:
        blocked = BlockedRequest.from_mapping(
            {
                "host": "example.com",
                "reason": "denied",
                "client": "curl",
                "method": "GET",
                "mode": "restricted",
                "protocol": "https",
                "decision": "deny",
                "source": "baseline_policy",
                "port": 443,
                "timestamp": 123,
            }
        )

        self.assertEqual(blocked.host, "example.com")
        self.assertEqual(blocked.to_mapping()["client"], "curl")
        self.assertEqual(blocked.to_mapping()["timestamp"], 123)

    def test_blocked_request_rejects_non_rust_field_shapes(self) -> None:
        with self.assertRaisesRegex(TypeError, "host must be a string"):
            BlockedRequest(host=object(), reason="denied")  # type: ignore[arg-type]

        with self.assertRaisesRegex(TypeError, "port must be an integer"):
            BlockedRequest(host="example.com", reason="denied", port=True)  # type: ignore[arg-type]

    def test_execpolicy_network_rule_amendment_rejects_bad_inputs(self) -> None:
        context = NetworkApprovalContext(
            host="example.com",
            protocol=NetworkApprovalProtocol.HTTP,
        )

        with self.assertRaisesRegex(TypeError, "amendment must be a NetworkPolicyAmendment"):
            execpolicy_network_rule_amendment(  # type: ignore[arg-type]
                object(),
                context,
                "example.com",
            )

        with self.assertRaisesRegex(TypeError, "host must be a string"):
            execpolicy_network_rule_amendment(
                NetworkPolicyAmendment("example.com", NetworkPolicyRuleAction.ALLOW),
                context,
                object(),  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
