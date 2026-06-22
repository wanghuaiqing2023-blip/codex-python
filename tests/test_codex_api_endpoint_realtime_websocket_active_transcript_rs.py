import unittest

from pycodex.codex_api.endpoint.realtime_websocket import RealtimeActiveTranscript
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeEvent
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeHandoffRequested
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeInputAudioSpeechStarted
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeResponseCreated
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeTranscriptDelta
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeTranscriptDone
from pycodex.codex_api.endpoint.realtime_websocket import RealtimeTranscriptEntry
from pycodex.codex_api.endpoint.realtime_websocket import append_handoff_input
from pycodex.codex_api.endpoint.realtime_websocket import append_transcript_delta
from pycodex.codex_api.endpoint.realtime_websocket import apply_transcript_done
from pycodex.codex_api.endpoint.realtime_websocket import contains_transcript_entry


class RealtimeWebsocketActiveTranscriptTests(unittest.TestCase):
    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Rust test: e2e_connect_and_exchange_events_against_mock_ws_server.
    # Contract: input/output deltas are accumulated and injected into handoff.active_transcript.
    def test_handoff_receives_transcript_since_previous_handoff(self) -> None:
        state = RealtimeActiveTranscript.new()
        state.update_active_transcript(
            RealtimeEvent.input_transcript_delta(RealtimeTranscriptDelta("delegate "))
        )
        state.update_active_transcript(
            RealtimeEvent.input_transcript_delta(RealtimeTranscriptDelta("now"))
        )
        state.update_active_transcript(
            RealtimeEvent.output_transcript_delta(RealtimeTranscriptDelta("working"))
        )

        event = state.update_active_transcript(
            RealtimeEvent.handoff_requested(
                RealtimeHandoffRequested("handoff_1", "item_2", "delegate now")
            )
        )

        self.assertEqual(
            event,
            RealtimeEvent.handoff_requested(
                RealtimeHandoffRequested(
                    "handoff_1",
                    "item_2",
                    "delegate now",
                    (
                        RealtimeTranscriptEntry("user", "delegate now"),
                        RealtimeTranscriptEntry("assistant", "working"),
                    ),
                )
            ),
        )
        self.assertEqual(state.last_handoff_entry_count, 2)
        self.assertTrue(state.new_input_entry)
        self.assertTrue(state.new_output_entry)

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: subsequent handoffs only receive transcript entries after the prior handoff.
    def test_subsequent_handoff_uses_entries_after_last_handoff(self) -> None:
        state = RealtimeActiveTranscript.new()
        state.update_active_transcript(
            RealtimeEvent.input_transcript_delta(RealtimeTranscriptDelta("first"))
        )
        state.update_active_transcript(
            RealtimeEvent.handoff_requested(RealtimeHandoffRequested("call_1", "item_1", "first"))
        )
        state.update_active_transcript(
            RealtimeEvent.input_transcript_delta(RealtimeTranscriptDelta("second"))
        )

        event = state.update_active_transcript(
            RealtimeEvent.handoff_requested(RealtimeHandoffRequested("call_2", "item_2", "second"))
        )

        self.assertEqual(
            event.payload.active_transcript,
            (RealtimeTranscriptEntry("user", "second"),),
        )
        self.assertEqual(state.last_handoff_entry_count, 2)

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: speech-started and response-created force the next same-role transcript into a new entry.
    def test_new_entry_flags_split_next_input_and_output(self) -> None:
        state = RealtimeActiveTranscript.new()
        state.update_active_transcript(
            RealtimeEvent.input_transcript_delta(RealtimeTranscriptDelta("hello"))
        )
        state.update_active_transcript(
            RealtimeEvent.input_audio_speech_started(RealtimeInputAudioSpeechStarted("item_1"))
        )
        state.update_active_transcript(
            RealtimeEvent.input_transcript_delta(RealtimeTranscriptDelta("again"))
        )
        state.update_active_transcript(
            RealtimeEvent.output_transcript_delta(RealtimeTranscriptDelta("one"))
        )
        state.update_active_transcript(RealtimeEvent.response_created(RealtimeResponseCreated("resp_1")))
        state.update_active_transcript(
            RealtimeEvent.output_transcript_delta(RealtimeTranscriptDelta("two"))
        )

        self.assertEqual(
            state.entries,
            [
                RealtimeTranscriptEntry("user", "hello"),
                RealtimeTranscriptEntry("user", "again"),
                RealtimeTranscriptEntry("assistant", "one"),
                RealtimeTranscriptEntry("assistant", "two"),
            ],
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: done events replace the last same-role text unless a new entry is forced.
    def test_done_replaces_or_pushes_transcript_text(self) -> None:
        state = RealtimeActiveTranscript.new()
        state.update_active_transcript(
            RealtimeEvent.input_transcript_delta(RealtimeTranscriptDelta("hel"))
        )
        state.update_active_transcript(
            RealtimeEvent.input_transcript_done(RealtimeTranscriptDone("hello"))
        )
        state.update_active_transcript(
            RealtimeEvent.input_audio_speech_started(RealtimeInputAudioSpeechStarted("item_2"))
        )
        state.update_active_transcript(
            RealtimeEvent.input_transcript_done(RealtimeTranscriptDone("next"))
        )

        self.assertEqual(
            state.entries,
            [
                RealtimeTranscriptEntry("user", "hello"),
                RealtimeTranscriptEntry("user", "next"),
            ],
        )

    # Rust source: codex-api/src/endpoint/realtime_websocket/methods.rs
    # Contract: helper functions ignore empty text, merge same-role deltas, trim handoff input, and de-duplicate.
    def test_low_level_transcript_helpers(self) -> None:
        entries: list[RealtimeTranscriptEntry] = []
        append_transcript_delta(entries, "user", "", False)
        self.assertEqual(entries, [])
        append_transcript_delta(entries, "user", "hel", False)
        append_transcript_delta(entries, "user", "lo", False)
        apply_transcript_done(entries, "user", "hello!", False)
        append_handoff_input(entries, " hello! ")
        append_handoff_input(entries, "new ask")

        self.assertTrue(contains_transcript_entry(entries, "user", "hello!"))
        self.assertEqual(
            entries,
            [
                RealtimeTranscriptEntry("user", "hello!"),
                RealtimeTranscriptEntry("user", "new ask"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
