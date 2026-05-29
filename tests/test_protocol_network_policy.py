import unittest

from pycodex.protocol import (
    NetworkApprovalProtocol,
    NetworkDecisionSource,
    NetworkPolicyDecision,
    NetworkPolicyDecisionPayload,
)


class ProtocolNetworkPolicyTests(unittest.TestCase):
    def test_network_policy_decision_payload_round_trips_wire_shape(self):
        payload = NetworkPolicyDecisionPayload.from_mapping(
            {
                "decision": "ask",
                "source": "decider",
                "protocol": "https",
                "host": "api.example.com",
                "reason": "needs approval",
                "port": 443,
            }
        )

        self.assertTrue(payload.is_ask_from_decider())
        self.assertEqual(payload.protocol, NetworkApprovalProtocol.HTTPS)
        self.assertEqual(
            payload.to_mapping(),
            {
                "decision": "ask",
                "source": "decider",
                "protocol": "https",
                "host": "api.example.com",
                "reason": "needs approval",
                "port": 443,
            },
        )

    def test_network_policy_payload_rejects_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "protocol must be a string"):
            NetworkPolicyDecisionPayload.from_mapping(
                {"decision": "deny", "source": "proxy_state", "protocol": 123}
            )
        with self.assertRaisesRegex(TypeError, "protocol must be a NetworkApprovalProtocol or None"):
            NetworkPolicyDecisionPayload(
                NetworkPolicyDecision.DENY,
                NetworkDecisionSource.PROXY_STATE,
                protocol=object(),  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(TypeError, "host must be a string"):
            NetworkPolicyDecisionPayload(NetworkPolicyDecision.DENY, NetworkDecisionSource.MODE_GUARD, host=123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "reason must be a string"):
            NetworkPolicyDecisionPayload(NetworkPolicyDecision.DENY, NetworkDecisionSource.MODE_GUARD, reason=123)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "port must be an integer"):
            NetworkPolicyDecisionPayload(NetworkPolicyDecision.DENY, NetworkDecisionSource.MODE_GUARD, port=True)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "port must fit in u16"):
            NetworkPolicyDecisionPayload(NetworkPolicyDecision.DENY, NetworkDecisionSource.MODE_GUARD, port=70000)


if __name__ == "__main__":
    unittest.main()
