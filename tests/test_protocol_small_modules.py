import unittest

from pycodex.protocol import (
    AgentMessageContent,
    AgentMessageEvent,
    AgentMessageItem,
    EventMsg,
    MemoryCitation,
    MemoryCitationEntry,
    NetworkApprovalProtocol,
    NetworkDecisionSource,
    NetworkPolicyDecision,
    NetworkPolicyDecisionPayload,
    format_si_suffix,
    format_with_separators,
)


class ProtocolSmallModulesTests(unittest.TestCase):
    def test_memory_citation_round_trip_and_agent_events(self):
        citation = MemoryCitation(
            entries=(MemoryCitationEntry("memory.md", 3, 7, "Relevant note"),),
            rollout_ids=("rollout-1", "rollout-2"),
        )

        self.assertEqual(MemoryCitation.from_mapping(citation.to_mapping()), citation)
        self.assertEqual(citation.to_mapping()["entries"][0]["lineStart"], 3)
        item = AgentMessageItem(
            "msg-1",
            (AgentMessageContent.text_content("hello"),),
            memory_citation=citation,
        )
        self.assertEqual(
            item.as_legacy_events()[0].payload,
            AgentMessageEvent("hello", memory_citation=citation),
        )

    def test_agent_message_event_parses_memory_citation(self):
        msg = EventMsg.from_mapping(
            {
                "type": "agent_message",
                "message": "remembered",
                "memory_citation": {
                    "entries": [{"path": "a.md", "lineStart": 1, "lineEnd": 2, "note": "n"}],
                    "rolloutIds": ["r1"],
                },
            }
        )

        self.assertEqual(
            msg.payload.memory_citation,
            MemoryCitation((MemoryCitationEntry("a.md", 1, 2, "n"),), ("r1",)),
        )
        self.assertEqual(msg.to_mapping()["memory_citation"]["rolloutIds"], ["r1"])

    def test_network_policy_decision_payload(self):
        payload = NetworkPolicyDecisionPayload.from_mapping(
            {
                "decision": "ask",
                "source": "decider",
                "protocol": "https_connect",
                "host": "example.com",
                "reason": "needs network",
                "port": 443,
            }
        )

        self.assertTrue(payload.is_ask_from_decider())
        self.assertEqual(payload.protocol, NetworkApprovalProtocol.HTTPS)
        self.assertEqual(payload.to_mapping()["protocol"], "https")
        self.assertEqual(NetworkPolicyDecision.DENY.as_str(), "deny")
        self.assertEqual(NetworkDecisionSource.BASELINE_POLICY.as_str(), "baseline_policy")

        denied = NetworkPolicyDecisionPayload(NetworkPolicyDecision.DENY, NetworkDecisionSource.MODE_GUARD)
        self.assertFalse(denied.is_ask_from_decider())
        with self.assertRaisesRegex(ValueError, "u16"):
            NetworkPolicyDecisionPayload.from_mapping({"decision": "deny", "source": "proxy_state", "port": 70000})

    def test_number_format_helpers_match_upstream_examples(self):
        self.assertEqual(format_with_separators(1_234_567), "1,234,567")
        self.assertEqual(format_si_suffix(0), "0")
        self.assertEqual(format_si_suffix(999), "999")
        self.assertEqual(format_si_suffix(1_000), "1.00K")
        self.assertEqual(format_si_suffix(1_200), "1.20K")
        self.assertEqual(format_si_suffix(10_000), "10.0K")
        self.assertEqual(format_si_suffix(100_000), "100K")
        self.assertEqual(format_si_suffix(999_500), "1.00M")
        self.assertEqual(format_si_suffix(1_234_000), "1.23M")
        self.assertEqual(format_si_suffix(12_345_678), "12.3M")
        self.assertEqual(format_si_suffix(999_950_000), "1.00G")
        self.assertEqual(format_si_suffix(1_234_000_000), "1.23G")
        self.assertEqual(format_si_suffix(1_234_000_000_000), "1,234G")
        self.assertEqual(format_si_suffix(-5), "0")


if __name__ == "__main__":
    unittest.main()
