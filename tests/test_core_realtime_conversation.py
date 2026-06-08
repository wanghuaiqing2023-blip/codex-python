import unittest

from pycodex.core.realtime_conversation import (
    RealtimeHandoffRequested,
    RealtimeTranscriptEntry,
    RealtimeWsVersion,
    realtime_delegation_from_handoff,
    realtime_request_headers,
    realtime_text_from_handoff_request,
    wrap_realtime_delegation_input,
)


class RealtimeConversationTests(unittest.TestCase):
    def test_prefers_handoff_input_transcript_over_active_transcript(self) -> None:
        handoff = RealtimeHandoffRequested(
            handoff_id="handoff_1",
            item_id="item_1",
            input_transcript="ignored",
            active_transcript=(
                RealtimeTranscriptEntry(role="user", text="hello"),
                RealtimeTranscriptEntry(role="assistant", text="hi there"),
            ),
        )

        self.assertEqual(realtime_text_from_handoff_request(handoff), "ignored")

    def test_extracts_text_from_active_transcript_if_input_missing(self) -> None:
        handoff = RealtimeHandoffRequested(
            handoff_id="handoff_1",
            item_id="item_1",
            input_transcript="",
            active_transcript=(RealtimeTranscriptEntry(role="user", text="hello"),),
        )

        self.assertEqual(realtime_text_from_handoff_request(handoff), "user: hello")

    def test_extracts_input_transcript_if_active_transcript_missing(self) -> None:
        handoff = RealtimeHandoffRequested(
            handoff_id="handoff_1",
            item_id="item_1",
            input_transcript="ignored",
            active_transcript=(),
        )

        self.assertEqual(realtime_text_from_handoff_request(handoff), "ignored")

    def test_wraps_handoff_with_transcript_delta(self) -> None:
        handoff = RealtimeHandoffRequested(
            handoff_id="handoff_1",
            item_id="item_1",
            input_transcript="delegate this",
            active_transcript=(
                RealtimeTranscriptEntry(role="user", text="hello"),
                RealtimeTranscriptEntry(role="assistant", text="hi there"),
            ),
        )

        self.assertEqual(
            realtime_delegation_from_handoff(handoff),
            "<realtime_delegation>\n"
            "  <input>delegate this</input>\n"
            "  <transcript_delta>user: hello\nassistant: hi there</transcript_delta>\n"
            "</realtime_delegation>",
        )

    def test_ignores_empty_handoff_request_input_transcript(self) -> None:
        handoff = RealtimeHandoffRequested(
            handoff_id="handoff_1",
            item_id="item_1",
            input_transcript="",
            active_transcript=(),
        )

        self.assertIsNone(realtime_text_from_handoff_request(handoff))

    def test_wraps_realtime_delegation_input_without_transcript(self) -> None:
        self.assertEqual(
            wrap_realtime_delegation_input("hello"),
            "<realtime_delegation>\n"
            "  <input>hello</input>\n"
            "</realtime_delegation>",
        )

    def test_wraps_realtime_delegation_input_with_xml_escaping(self) -> None:
        self.assertEqual(
            wrap_realtime_delegation_input("use a < b && c > d", "saw <that>"),
            "<realtime_delegation>\n"
            "  <input>use a &lt; b &amp;&amp; c &gt; d</input>\n"
            "  <transcript_delta>saw &lt;that&gt;</transcript_delta>\n"
            "</realtime_delegation>",
        )

    def test_wraps_realtime_delegation_input_with_xml_escaping_without_transcript(self) -> None:
        self.assertEqual(
            wrap_realtime_delegation_input("use a < b && c > d"),
            "<realtime_delegation>\n"
            "  <input>use a &lt; b &amp;&amp; c &gt; d</input>\n"
            "</realtime_delegation>",
        )

    def test_uses_quicksilver_alpha_header_for_realtime_v1(self) -> None:
        headers = realtime_request_headers("session_1", "sk-test", RealtimeWsVersion.V1)

        self.assertEqual(headers.get("openai-alpha"), "quicksilver=v1")
        self.assertEqual(headers.get("x-session-id"), "session_1")
        self.assertEqual(headers.get("authorization"), "Bearer sk-test")

    def test_omits_quicksilver_alpha_header_for_realtime_v2(self) -> None:
        headers = realtime_request_headers("session_1", "sk-test", RealtimeWsVersion.V2)

        self.assertNotIn("openai-alpha", headers)

    def test_invalid_session_header_is_ignored_but_invalid_api_key_errors(self) -> None:
        headers = realtime_request_headers("bad\r\nsession", None, "v1")

        self.assertNotIn("x-session-id", headers)
        with self.assertRaises(ValueError):
            realtime_request_headers(None, "bad\r\nkey", "v1")


if __name__ == "__main__":
    unittest.main()
