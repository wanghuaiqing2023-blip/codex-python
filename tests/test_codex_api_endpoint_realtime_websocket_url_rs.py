import unittest

from pycodex.codex_api.endpoint.realtime_websocket import RealtimeEventParser
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeSessionMode
from pycodex.codex_api.endpoint.realtime_websocket import websocket_config
from pycodex.codex_api.endpoint.realtime_websocket import websocket_url_from_api_url
from pycodex.codex_api.endpoint.realtime_websocket import websocket_url_from_api_url_for_call


class RealtimeWebsocketUrlTests(unittest.TestCase):
    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Rust test: websocket_url_from_http_base_defaults_to_ws_path.
    # Contract: http base URLs become ws and default to /v1/realtime with V1 intent.
    def test_http_base_defaults_to_ws_realtime_path(self) -> None:
        self.assertEqual(
            websocket_url_from_api_url(
                "http://127.0.0.1:8011",
                None,
                None,
                RealtimeEventParser.V1,
                RealtimeSessionMode.CONVERSATIONAL,
            ),
            "ws://127.0.0.1:8011/v1/realtime?intent=quicksilver",
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Rust test: websocket_url_from_ws_base_defaults_to_ws_path.
    # Contract: websocket schemes are preserved and model is appended after intent.
    def test_ws_base_preserves_scheme_and_appends_model(self) -> None:
        self.assertEqual(
            websocket_url_from_api_url(
                "wss://example.com",
                None,
                "realtime-test-model",
                RealtimeEventParser.V1,
                RealtimeSessionMode.CONVERSATIONAL,
            ),
            "wss://example.com/v1/realtime?intent=quicksilver&model=realtime-test-model",
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Rust tests: websocket_url_from_v1_base_appends_realtime_path and nested variant.
    # Contract: base paths ending in /v1 append /realtime.
    def test_v1_base_appends_realtime_path(self) -> None:
        self.assertEqual(
            websocket_url_from_api_url(
                "https://api.openai.com/v1",
                None,
                "snapshot",
                RealtimeEventParser.V1,
                RealtimeSessionMode.CONVERSATIONAL,
            ),
            "wss://api.openai.com/v1/realtime?intent=quicksilver&model=snapshot",
        )
        self.assertEqual(
            websocket_url_from_api_url(
                "https://example.com/openai/v1",
                None,
                "snapshot",
                RealtimeEventParser.V1,
                RealtimeSessionMode.CONVERSATIONAL,
            ),
            "wss://example.com/openai/v1/realtime?intent=quicksilver&model=snapshot",
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Rust test: websocket_url_preserves_existing_realtime_path_and_extra_query_params.
    # Contract: existing query is preserved before intent/model/extra params; extra intent is ignored.
    def test_preserves_existing_realtime_path_and_extra_query_params(self) -> None:
        self.assertEqual(
            websocket_url_from_api_url(
                "https://example.com/v1/realtime?foo=bar",
                {"trace": "1", "intent": "ignored"},
                "snapshot",
                RealtimeEventParser.V1,
                RealtimeSessionMode.CONVERSATIONAL,
            ),
            "wss://example.com/v1/realtime?foo=bar&intent=quicksilver&model=snapshot&trace=1",
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Rust test: websocket_url_v1_ignores_transcription_mode.
    # Contract: V1 URL intent ignores transcription mode.
    def test_v1_transcription_mode_keeps_quicksilver_intent(self) -> None:
        self.assertEqual(
            websocket_url_from_api_url(
                "https://example.com",
                None,
                None,
                RealtimeEventParser.V1,
                RealtimeSessionMode.TRANSCRIPTION,
            ),
            "wss://example.com/v1/realtime?intent=quicksilver",
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Rust tests: websocket_url_omits_intent_for_realtime_v2_*.
    # Contract: Realtime V2 omits intent and filters provided intent/model when model is explicit.
    def test_realtime_v2_omits_intent(self) -> None:
        self.assertEqual(
            websocket_url_from_api_url(
                "https://example.com/v1/realtime?foo=bar",
                {"trace": "1", "intent": "ignored"},
                "snapshot",
                RealtimeEventParser.REALTIME_V2,
                RealtimeSessionMode.CONVERSATIONAL,
            ),
            "wss://example.com/v1/realtime?foo=bar&model=snapshot&trace=1",
        )
        self.assertEqual(
            websocket_url_from_api_url(
                "https://example.com",
                None,
                None,
                RealtimeEventParser.REALTIME_V2,
                RealtimeSessionMode.TRANSCRIPTION,
            ),
            "wss://example.com/v1/realtime",
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Rust test: websocket_url_for_call_id_joins_existing_realtime_session.
    # Contract: WebRTC sideband URLs append call_id after base realtime URL construction.
    def test_call_id_joins_existing_realtime_session(self) -> None:
        self.assertEqual(
            websocket_url_from_api_url_for_call(
                "https://api.openai.com/v1",
                None,
                RealtimeEventParser.REALTIME_V2,
                RealtimeSessionMode.CONVERSATIONAL,
                "rtc_test",
            ),
            "wss://api.openai.com/v1/realtime?call_id=rtc_test",
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: unsupported schemes are stream errors; websocket_config is default.
    def test_unsupported_scheme_errors_and_config_is_default(self) -> None:
        with self.assertRaisesRegex(Exception, "stream error: unsupported realtime api_url scheme: ftp"):
            websocket_url_from_api_url(
                "ftp://example.com",
                None,
                None,
                RealtimeEventParser.V1,
                RealtimeSessionMode.CONVERSATIONAL,
            )
        self.assertEqual(websocket_config(), {})


if __name__ == "__main__":
    unittest.main()
