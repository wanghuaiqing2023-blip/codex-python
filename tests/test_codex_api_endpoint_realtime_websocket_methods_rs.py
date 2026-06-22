import unittest

from pycodex.codex_api import session_update_session_json as exported_session_update_session_json
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeEventParser
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeSessionConfig
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeSessionMode
from pycodex.codex_api.endpoint.realtime_websocket import conversation_function_call_output_message
from pycodex.codex_api.endpoint.realtime_websocket import conversation_item_create_message
from pycodex.codex_api.endpoint.realtime_websocket import normalized_session_mode
from pycodex.codex_api.endpoint.realtime_websocket import session_update_message
from pycodex.codex_api.endpoint.realtime_websocket import session_update_session_json
from pycodex.codex_api.endpoint.realtime_websocket import websocket_intent
from pycodex.codex_api.endpoint.realtime_websocket.methods_common import (
    AGENT_FINAL_MESSAGE_PREFIX,
)
from pycodex.codex_api.endpoint.realtime_websocket.methods_v2 import (
    REALTIME_V2_BACKGROUND_AGENT_TOOL_DESCRIPTION,
)
from pycodex.protocol import RealtimeOutputModality
from pycodex.protocol import RealtimeVoice


def session_config(
    *,
    event_parser: RealtimeEventParser = RealtimeEventParser.REALTIME_V2,
    session_mode: RealtimeSessionMode = RealtimeSessionMode.CONVERSATIONAL,
    output_modality: RealtimeOutputModality = RealtimeOutputModality.AUDIO,
    voice: RealtimeVoice = RealtimeVoice.MARIN,
) -> RealtimeSessionConfig:
    return RealtimeSessionConfig(
        instructions="backend prompt",
        model="realtime-test-model",
        session_id="conv_1",
        event_parser=event_parser,
        session_mode=session_mode,
        output_modality=output_modality,
        voice=voice,
    )


class RealtimeWebsocketMethodsTests(unittest.TestCase):
    # Rust source: codex-api/src/endpoint/realtime_websocket/methods_common.rs
    # Rust tests: methods.rs websocket_url_v1_ignores_transcription_mode.
    # Contract: V1 normalizes every session mode to conversational and keeps quicksilver intent.
    def test_v1_normalizes_transcription_mode_and_uses_quicksilver_intent(self) -> None:
        self.assertEqual(
            normalized_session_mode(RealtimeEventParser.V1, RealtimeSessionMode.TRANSCRIPTION),
            RealtimeSessionMode.CONVERSATIONAL,
        )
        self.assertEqual(websocket_intent(RealtimeEventParser.V1), "quicksilver")
        self.assertIsNone(websocket_intent(RealtimeEventParser.REALTIME_V2))

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods_v1.rs
    # Rust test: methods.rs e2e_connect_and_exchange_events_against_mock_ws_server.
    # Contract: V1 text and handoff output outbound messages match serde JSON shape.
    def test_v1_outbound_text_and_handoff_output_messages(self) -> None:
        self.assertEqual(
            conversation_item_create_message(RealtimeEventParser.V1, "hello agent"),
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello agent"}],
                },
            },
        )
        self.assertEqual(
            conversation_function_call_output_message(
                RealtimeEventParser.V1,
                "handoff_1",
                "hello from background agent",
            ),
            {
                "type": "conversation.handoff.append",
                "handoff_id": "handoff_1",
                "output_text": (
                    f"{AGENT_FINAL_MESSAGE_PREFIX}hello from background agent"
                ),
            },
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods_v1.rs
    # Rust test: methods.rs e2e_connect_and_exchange_events_against_mock_ws_server.
    # Contract: V1 session.update session JSON uses quicksilver audio format and voice.
    def test_v1_session_update_json_includes_id_and_model(self) -> None:
        payload = session_update_session_json(
            session_config(
                event_parser=RealtimeEventParser.V1,
                session_mode=RealtimeSessionMode.TRANSCRIPTION,
                voice=RealtimeVoice.BREEZE,
            )
        )
        self.assertEqual(
            payload,
            {
                "type": "quicksilver",
                "instructions": "backend prompt",
                "audio": {
                    "input": {"format": {"type": "audio/pcm", "rate": 24_000}},
                    "output": {"voice": "breeze"},
                },
                "id": "conv_1",
                "model": "realtime-test-model",
            },
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods_v2.rs
    # Rust test: methods.rs realtime_v2_session_update_includes_background_agent_tool_and_handoff_output_item.
    # Contract: V2 conversational session includes audio, tools, output modality, and tool choice.
    def test_v2_conversational_session_update_matches_tool_contract(self) -> None:
        payload = session_update_session_json(
            session_config(
                output_modality=RealtimeOutputModality.TEXT,
                voice=RealtimeVoice.CEDAR,
            )
        )
        self.assertEqual(payload["type"], "realtime")
        self.assertEqual(payload["instructions"], "backend prompt")
        self.assertEqual(payload["output_modalities"], ["text"])
        self.assertEqual(payload["audio"]["input"]["format"], {"type": "audio/pcm", "rate": 24_000})
        self.assertEqual(payload["audio"]["input"]["noise_reduction"], {"type": "near_field"})
        self.assertEqual(
            payload["audio"]["input"]["transcription"],
            {"model": "gpt-4o-mini-transcribe"},
        )
        self.assertEqual(
            payload["audio"]["input"]["turn_detection"],
            {
                "type": "server_vad",
                "interrupt_response": True,
                "create_response": True,
                "silence_duration_ms": 500,
            },
        )
        self.assertEqual(payload["audio"]["output"]["format"], {"type": "audio/pcm", "rate": 24_000})
        self.assertEqual(payload["audio"]["output"]["voice"], "cedar")
        self.assertEqual(payload["tools"][0]["type"], "function")
        self.assertEqual(payload["tools"][0]["name"], "background_agent")
        self.assertEqual(
            payload["tools"][0]["description"],
            REALTIME_V2_BACKGROUND_AGENT_TOOL_DESCRIPTION,
        )
        self.assertEqual(payload["tools"][0]["parameters"]["required"], ["prompt"])
        self.assertEqual(payload["tools"][1]["type"], "function")
        self.assertEqual(payload["tools"][1]["name"], "remain_silent")
        self.assertEqual(payload["tools"][1]["parameters"]["properties"], {})
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertEqual(payload["id"], "conv_1")
        self.assertEqual(payload["model"], "realtime-test-model")

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods_v2.rs
    # Rust test: methods.rs realtime_v2_session_update_includes_background_agent_tool_and_handoff_output_item.
    # Contract: V2 text and function-call output messages use conversation.item.create.
    def test_v2_outbound_text_and_function_call_output_messages(self) -> None:
        self.assertEqual(
            conversation_item_create_message(RealtimeEventParser.REALTIME_V2, "delegate this"),
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "delegate this"}],
                },
            },
        )
        self.assertEqual(
            conversation_function_call_output_message(
                RealtimeEventParser.REALTIME_V2,
                "call_1",
                "delegated result",
            ),
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": "delegated result",
                },
            },
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods_v2.rs
    # Rust test: methods.rs transcription_mode_session_update_omits_output_audio_and_instructions.
    # Contract: V2 transcription sessions omit instructions, output audio, tools, and tool choice.
    def test_v2_transcription_session_omits_conversational_fields(self) -> None:
        payload = session_update_session_json(
            session_config(session_mode=RealtimeSessionMode.TRANSCRIPTION)
        )
        self.assertEqual(
            payload,
            {
                "type": "transcription",
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": 24_000},
                        "transcription": {"model": "gpt-4o-mini-transcribe"},
                    }
                },
                "id": "conv_1",
                "model": "realtime-test-model",
            },
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods_common.rs
    # Contract: session.update wrapper nests the same session JSON used by realtime_call.
    def test_session_update_message_and_public_export_reuse_same_session_json(self) -> None:
        config = session_config()
        self.assertEqual(
            session_update_message(config),
            {"type": "session.update", "session": session_update_session_json(config)},
        )
        self.assertEqual(exported_session_update_session_json(config), session_update_session_json(config))

    # Rust source: codex-api/src/endpoint/realtime_websocket/protocol.rs
    # Rust contract: SessionUpdateSession.id/model use skip_serializing_if = Option::is_none.
    def test_session_update_session_json_omits_absent_id_and_model(self) -> None:
        payload = session_update_session_json(
            RealtimeSessionConfig(
                instructions="backend prompt",
                model=None,
                session_id=None,
                event_parser=RealtimeEventParser.REALTIME_V2,
                session_mode=RealtimeSessionMode.TRANSCRIPTION,
                output_modality=RealtimeOutputModality.AUDIO,
                voice=RealtimeVoice.MARIN,
            )
        )
        self.assertNotIn("id", payload)
        self.assertNotIn("model", payload)
        self.assertNotIn("instructions", payload)
        self.assertNotIn("output", payload["audio"])


if __name__ == "__main__":
    unittest.main()
