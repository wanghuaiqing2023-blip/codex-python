import json
import unittest

from pycodex.codex_api.endpoint.realtime_websocket import RealtimeEvent
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeEventParser
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeHandoffRequested
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeInputAudioSpeechStarted
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeNoopRequested
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeResponseCancelled
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeResponseCreated
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeResponseDone
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeTranscriptDelta
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeTranscriptDone
from pycodex.codex_api.endpoint.realtime_websocket import parse_realtime_event
from pycodex.protocol import RealtimeAudioFrame


def payload(**value: object) -> str:
    return json.dumps(value, separators=(",", ":"))


class RealtimeWebsocketProtocolTests(unittest.TestCase):
    # Rust source: codex-api/src/endpoint/realtime_websocket/protocol_common.rs
    # Rust test: methods.rs parse_session_updated_event.
    # Contract: session.updated requires session.id and preserves optional instructions.
    def test_parse_session_updated_event(self) -> None:
        event = parse_realtime_event(
            payload(
                type="session.updated",
                session={"id": "sess_123", "instructions": "backend prompt"},
            ),
            RealtimeEventParser.V1,
        )
        self.assertEqual(
            event,
            RealtimeEvent.session_updated("sess_123", "backend prompt"),
        )
        self.assertIsNone(
            parse_realtime_event(payload(type="session.updated", session={}), RealtimeEventParser.V1)
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/protocol_v1.rs
    # Rust test: methods.rs parse_audio_delta_event.
    # Contract: V1 output audio requires explicit delta/data, sample_rate, and channels.
    def test_parse_v1_audio_delta_event(self) -> None:
        event = parse_realtime_event(
            payload(
                type="conversation.output_audio.delta",
                delta="AAA=",
                sample_rate=48000,
                channels=1,
                samples_per_channel=960,
            ),
            RealtimeEventParser.V1,
        )
        self.assertEqual(
            event,
            RealtimeEvent.audio_out(
                RealtimeAudioFrame(
                    data="AAA=",
                    sample_rate=48000,
                    num_channels=1,
                    samples_per_channel=960,
                    item_id=None,
                )
            ),
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/protocol_v1.rs
    # Contract: V1 audio fields use Value::as_u64 plus u32/u16 try_from; invalid
    # numeric values make the audio event unparseable.
    def test_parse_v1_audio_delta_rejects_negative_and_overflow_numeric_fields(self) -> None:
        for field, value in [
            ("sample_rate", -1),
            ("sample_rate", 2**32),
            ("channels", -1),
            ("channels", 2**16),
            ("num_channels", 2**16),
        ]:
            data = {
                "type": "conversation.output_audio.delta",
                "delta": "AAA=",
                "sample_rate": 48000,
                "channels": 1,
            }
            if field == "num_channels":
                data.pop("channels")
            data[field] = value
            with self.subTest(field=field, value=value):
                self.assertIsNone(
                    parse_realtime_event(payload(**data), RealtimeEventParser.V1)
                )

    # Rust source: codex-api/src/endpoint/realtime_websocket/protocol_v1.rs
    # Rust tests: parse_conversation_item_added_event, parse_conversation_item_done_event.
    # Contract: V1 conversation item events forward item JSON and done item ids.
    def test_parse_v1_conversation_item_events(self) -> None:
        self.assertEqual(
            parse_realtime_event(
                payload(type="conversation.item.added", item={"type": "message", "seq": 7}),
                RealtimeEventParser.V1,
            ),
            RealtimeEvent.conversation_item_added({"type": "message", "seq": 7}),
        )
        self.assertEqual(
            parse_realtime_event(
                payload(type="conversation.item.done", item={"id": "item_123", "type": "message"}),
                RealtimeEventParser.V1,
            ),
            RealtimeEvent.conversation_item_done("item_123"),
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/protocol_v1.rs
    # Rust test: methods.rs parse_handoff_requested_event.
    # Contract: V1 handoff requested carries explicit handoff_id/item_id/input_transcript.
    def test_parse_v1_handoff_requested_event(self) -> None:
        self.assertEqual(
            parse_realtime_event(
                payload(
                    type="conversation.handoff.requested",
                    handoff_id="handoff_123",
                    item_id="item_123",
                    input_transcript="delegate this",
                ),
                RealtimeEventParser.V1,
            ),
            RealtimeEvent.handoff_requested(
                RealtimeHandoffRequested(
                    "handoff_123",
                    "item_123",
                    "delegate this",
                    (),
                )
            ),
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/protocol_v1.rs
    # Rust tests: parse_input/output transcript delta/done variants.
    # Contract: V1 maps alternate transcript event names into input/output delta/done events.
    def test_parse_v1_transcript_aliases(self) -> None:
        self.assertEqual(
            parse_realtime_event(
                payload(type="conversation.item.input_audio_transcription.delta", delta="hello"),
                RealtimeEventParser.V1,
            ),
            RealtimeEvent.input_transcript_delta(RealtimeTranscriptDelta("hello")),
        )
        self.assertEqual(
            parse_realtime_event(
                payload(type="conversation.input_transcript.turn_marked", transcript="hello realtime"),
                RealtimeEventParser.V1,
            ),
            RealtimeEvent.input_transcript_done(RealtimeTranscriptDone("hello realtime")),
        )
        self.assertEqual(
            parse_realtime_event(
                payload(type="response.output_audio_transcript.delta", delta="hi"),
                RealtimeEventParser.V1,
            ),
            RealtimeEvent.output_transcript_delta(RealtimeTranscriptDelta("hi")),
        )
        self.assertEqual(
            parse_realtime_event(
                payload(type="response.output_audio_transcript.done", transcript="hi there"),
                RealtimeEventParser.V1,
            ),
            RealtimeEvent.output_transcript_done(RealtimeTranscriptDone("hi there")),
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/protocol_v2.rs
    # Rust test: methods.rs parse_realtime_v2_handoff_tool_call_event.
    # Contract: V2 background_agent function_call done becomes HandoffRequested.
    def test_parse_v2_handoff_tool_call_event(self) -> None:
        self.assertEqual(
            parse_realtime_event(
                payload(
                    type="conversation.item.done",
                    item={
                        "id": "item_123",
                        "type": "function_call",
                        "name": "background_agent",
                        "call_id": "call_123",
                        "arguments": '{"prompt":"delegate this"}',
                    },
                ),
                RealtimeEventParser.REALTIME_V2,
            ),
            RealtimeEvent.handoff_requested(
                RealtimeHandoffRequested("call_123", "item_123", "delegate this", ())
            ),
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/protocol_v2.rs
    # Rust test: methods.rs parse_realtime_v2_noop_tool_call_event.
    # Contract: V2 remain_silent function_call done becomes NoopRequested.
    def test_parse_v2_noop_tool_call_event(self) -> None:
        self.assertEqual(
            parse_realtime_event(
                payload(
                    type="conversation.item.done",
                    item={
                        "id": "item_silent",
                        "type": "function_call",
                        "name": "remain_silent",
                        "call_id": "call_silent",
                        "arguments": "{}",
                    },
                ),
                RealtimeEventParser.REALTIME_V2,
            ),
            RealtimeEvent.noop_requested(RealtimeNoopRequested("call_silent", "item_silent")),
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/protocol_v2.rs
    # Rust tests: parse_realtime_v2_*transcript*.
    # Contract: V2 transcript delta/done aliases map to input/output transcript events.
    def test_parse_v2_transcript_events(self) -> None:
        self.assertEqual(
            parse_realtime_event(
                payload(type="conversation.item.input_audio_transcription.delta", delta="hello"),
                RealtimeEventParser.REALTIME_V2,
            ),
            RealtimeEvent.input_transcript_delta(RealtimeTranscriptDelta("hello")),
        )
        self.assertEqual(
            parse_realtime_event(
                payload(type="response.output_text.done", text="hello there"),
                RealtimeEventParser.REALTIME_V2,
            ),
            RealtimeEvent.output_transcript_done(RealtimeTranscriptDone("hello there")),
        )
        self.assertEqual(
            parse_realtime_event(
                payload(type="response.output_audio_transcript.done", transcript="audio there"),
                RealtimeEventParser.REALTIME_V2,
            ),
            RealtimeEvent.output_transcript_done(RealtimeTranscriptDone("audio there")),
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/protocol_v2.rs
    # Rust tests: parse_realtime_v2_conversation_item_created_event and item_done output text.
    # Contract: V2 item created/added forwards item JSON; ordinary item done returns item id.
    def test_parse_v2_conversation_item_events(self) -> None:
        self.assertEqual(
            parse_realtime_event(
                payload(type="conversation.item.created", item={"type": "message", "role": "user"}),
                RealtimeEventParser.REALTIME_V2,
            ),
            RealtimeEvent.conversation_item_added({"type": "message", "role": "user"}),
        )
        self.assertEqual(
            parse_realtime_event(
                payload(
                    type="conversation.item.done",
                    item={"id": "item_output_1", "type": "message", "role": "assistant"},
                ),
                RealtimeEventParser.REALTIME_V2,
            ),
            RealtimeEvent.conversation_item_done("item_output_1"),
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/protocol_v2.rs
    # Rust tests: parse_realtime_v2_output_audio_delta_defaults_audio_shape and response_audio_delta_with_item_id.
    # Contract: V2 output audio defaults sample rate/channels and carries optional item_id.
    def test_parse_v2_audio_delta_defaults(self) -> None:
        self.assertEqual(
            parse_realtime_event(
                payload(type="response.output_audio.delta", delta="AQID"),
                RealtimeEventParser.REALTIME_V2,
            ),
            RealtimeEvent.audio_out(
                RealtimeAudioFrame(
                    data="AQID",
                    sample_rate=24_000,
                    num_channels=1,
                    samples_per_channel=None,
                    item_id=None,
                )
            ),
        )
        self.assertEqual(
            parse_realtime_event(
                payload(type="response.audio.delta", delta="AQID", item_id="item_audio_1"),
                RealtimeEventParser.REALTIME_V2,
            ),
            RealtimeEvent.audio_out(
                RealtimeAudioFrame(
                    data="AQID",
                    sample_rate=24_000,
                    num_channels=1,
                    samples_per_channel=None,
                    item_id="item_audio_1",
                )
            ),
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/protocol_v2.rs
    # Contract: V2 audio fields use Value::as_u64 plus try_from and default
    # invalid sample_rate/channels, while invalid samples_per_channel is absent.
    def test_parse_v2_audio_delta_defaults_invalid_numeric_fields(self) -> None:
        event = parse_realtime_event(
            payload(
                type="response.output_audio.delta",
                delta="AQID",
                sample_rate=-1,
                channels=2**16,
                samples_per_channel=-1,
            ),
            RealtimeEventParser.REALTIME_V2,
        )

        self.assertEqual(
            event,
            RealtimeEvent.audio_out(
                RealtimeAudioFrame(
                    data="AQID",
                    sample_rate=24_000,
                    num_channels=1,
                    samples_per_channel=None,
                    item_id=None,
                )
            ),
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/protocol_v2.rs
    # Rust tests: parse_realtime_v2_speech_started/response_cancelled/response_done/response_created.
    # Contract: V2 lifecycle events project optional response/item ids.
    def test_parse_v2_lifecycle_events(self) -> None:
        self.assertEqual(
            parse_realtime_event(
                payload(type="input_audio_buffer.speech_started", item_id="item_input_1"),
                RealtimeEventParser.REALTIME_V2,
            ),
            RealtimeEvent.input_audio_speech_started(
                RealtimeInputAudioSpeechStarted("item_input_1")
            ),
        )
        self.assertEqual(
            parse_realtime_event(
                payload(type="response.cancelled", response={"id": "resp_cancelled_1"}),
                RealtimeEventParser.REALTIME_V2,
            ),
            RealtimeEvent.response_cancelled(RealtimeResponseCancelled("resp_cancelled_1")),
        )
        self.assertEqual(
            parse_realtime_event(
                payload(type="response.done", response={"output": []}),
                RealtimeEventParser.REALTIME_V2,
            ),
            RealtimeEvent.response_done(RealtimeResponseDone(None)),
        )
        self.assertEqual(
            parse_realtime_event(
                payload(type="response.created", response={"id": "resp_created_1"}),
                RealtimeEventParser.REALTIME_V2,
            ),
            RealtimeEvent.response_created(RealtimeResponseCreated("resp_created_1")),
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/protocol_common.rs
    # Contract: invalid JSON, missing type, unsupported event types, and unparseable required fields return None.
    def test_invalid_or_unsupported_payloads_return_none(self) -> None:
        self.assertIsNone(parse_realtime_event("{", RealtimeEventParser.V1))
        self.assertIsNone(parse_realtime_event(payload(foo="bar"), RealtimeEventParser.REALTIME_V2))
        self.assertIsNone(
            parse_realtime_event(payload(type="unknown.event"), RealtimeEventParser.REALTIME_V2)
        )
        self.assertIsNone(
            parse_realtime_event(
                payload(type="conversation.output_audio.delta", delta="AAA=", sample_rate=48000),
                RealtimeEventParser.V1,
            )
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/protocol_common.rs
    # Contract: error events prefer top-level message, then nested error.message, then JSON-ish error.
    def test_parse_error_event_fallbacks(self) -> None:
        self.assertEqual(
            parse_realtime_event(payload(type="error", message="top"), RealtimeEventParser.V1),
            RealtimeEvent.error("top"),
        )
        self.assertEqual(
            parse_realtime_event(
                payload(type="error", error={"message": "nested"}),
                RealtimeEventParser.REALTIME_V2,
            ),
            RealtimeEvent.error("nested"),
        )


if __name__ == "__main__":
    unittest.main()
