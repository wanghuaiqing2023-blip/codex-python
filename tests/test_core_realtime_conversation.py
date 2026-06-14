import asyncio
from pathlib import Path
import tempfile
import unittest

from pycodex.core.realtime_conversation import (
    DEFAULT_REALTIME_MODEL,
    REALTIME_BACKEND_TEXT_PREFIX,
    REALTIME_USER_TEXT_PREFIX,
    RealtimeConversationEnd,
    RealtimeConversationManager,
    RealtimeHandoffRequested,
    RealtimeSessionKind,
    RealtimeStart,
    RealtimeStartOutput,
    RealtimeTranscriptEntry,
    RealtimeWsVersion,
    end_realtime_conversation,
    handle_text,
    prefix_realtime_text,
    realtime_delegation_from_handoff,
    realtime_conversation_list_voices,
    realtime_request_headers,
    realtime_text_from_handoff_request,
    send_conversation_error,
    send_realtime_conversation_closed,
    wrap_realtime_delegation_input,
)
from pycodex.core.realtime_context import (
    STARTUP_CONTEXT_CLOSE_TAG,
    STARTUP_CONTEXT_OPEN_TAG,
    build_realtime_startup_context,
    truncate_realtime_text_to_token_budget,
)
from pycodex.core.realtime_prompt import (
    BACKEND_PROMPT,
    PROMPT_UNSET,
    prepare_realtime_backend_prompt,
)
from pycodex.protocol import ContentItem, ResponseItem


def _user_message(text: str) -> ResponseItem:
    return ResponseItem.message("user", (ContentItem.input_text(text),))


def _assistant_message(text: str) -> ResponseItem:
    return ResponseItem.message("assistant", (ContentItem.output_text(text),))


class _FakeRealtimeRuntime:
    def __init__(self, *, sdp: str | None = None, fail: Exception | None = None) -> None:
        self.sdp = sdp
        self.fail = fail
        self.starts: list[RealtimeStart] = []
        self.shutdowns = 0

    async def start_realtime_conversation(self, start: RealtimeStart) -> RealtimeStartOutput:
        self.starts.append(start)
        if self.fail is not None:
            raise self.fail
        return RealtimeStartOutput(realtime_active=True, events_rx=asyncio.Queue(), sdp=self.sdp)

    async def shutdown_realtime_conversation(self, _state: object) -> None:
        self.shutdowns += 1


class _FakeSession:
    def __init__(self, conversation: object | None = None) -> None:
        self.conversation = conversation
        self.events: list[dict[str, object]] = []
        self.submissions: list[tuple[str, object]] = []

    async def send_event_raw(self, event: dict[str, object]) -> None:
        self.events.append(event)

    async def submit(self, op: str, submission: object) -> None:
        self.submissions.append((op, submission))


class _CancelToken:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


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


class RealtimeConversationSuiteParityTests(unittest.TestCase):
    def test_conversation_start_audio_text_close_round_trip(self) -> None:
        async def run() -> None:
            manager = RealtimeConversationManager()
            await manager.start(RealtimeStart(session_kind=RealtimeSessionKind.V2))

            await manager.audio_in(b"pcm")
            await manager.text_in("hello")

            state = await manager._require_state()
            self.assertEqual(state.audio_tx.get_nowait(), b"pcm")
            self.assertEqual(state.user_text_tx.get_nowait(), "[USER] hello")

            session = _FakeSession(manager)
            await end_realtime_conversation(session, "sub_1", RealtimeConversationEnd.REQUESTED)
            self.assertIsNone(await manager.running_state())
            self.assertEqual(session.events[-1]["msg"], {"type": "realtime_conversation_closed", "reason": "requested"})

        asyncio.run(run())

    def test_conversation_start_defaults_to_v2_and_gpt_realtime_1_5(self) -> None:
        async def run() -> None:
            manager = RealtimeConversationManager()
            await manager.start(RealtimeStart(session_kind=RealtimeSessionKind.V2))

            self.assertEqual(DEFAULT_REALTIME_MODEL, "gpt-realtime-1.5")
            self.assertTrue(await manager.is_running_v2())

        asyncio.run(run())

    def test_conversation_webrtc_start_posts_generated_session(self) -> None:
        async def run() -> None:
            runtime = _FakeRealtimeRuntime(sdp="answer-sdp")
            manager = RealtimeConversationManager()

            output = await manager.start(RealtimeStart(sdp="offer-sdp", runtime=runtime))

            self.assertEqual(output.sdp, "answer-sdp")
            self.assertEqual(runtime.starts[0].sdp, "offer-sdp")

        asyncio.run(run())

    def test_conversation_webrtc_close_while_sideband_connecting_drops_pending_join(self) -> None:
        async def run() -> None:
            manager = RealtimeConversationManager()
            token = _CancelToken()
            await manager.start(RealtimeStart())
            await manager.register_fanout_task(object(), token)

            await manager.shutdown()

            self.assertTrue(token.cancelled)

        asyncio.run(run())

    def test_conversation_webrtc_sideband_connect_failure_closes_with_error(self) -> None:
        async def run() -> None:
            session = _FakeSession()

            await send_conversation_error(session, "sub_1", "sideband connect failed", "connection_failed")

            self.assertEqual(
                session.events,
                [
                    {
                        "id": "sub_1",
                        "msg": {
                            "type": "error",
                            "message": "sideband connect failed",
                            "codex_error_info": "connection_failed",
                        },
                    }
                ],
            )

        asyncio.run(run())

    def test_conversation_start_uses_openai_env_key_fallback_with_chatgpt_auth(self) -> None:
        headers = realtime_request_headers(None, "sk-from-env", RealtimeWsVersion.V2)

        self.assertEqual(headers["authorization"], "Bearer sk-from-env")
        self.assertNotIn("openai-alpha", headers)

    def test_conversation_transport_close_emits_closed_event(self) -> None:
        async def run() -> None:
            session = _FakeSession()

            await send_realtime_conversation_closed(session, "sub_1", RealtimeConversationEnd.TRANSPORT_CLOSED)

            self.assertEqual(session.events[-1]["msg"], {"type": "realtime_conversation_closed", "reason": "transport_closed"})

        asyncio.run(run())

    def test_conversation_audio_before_start_emits_error(self) -> None:
        async def run() -> None:
            with self.assertRaisesRegex(RuntimeError, "conversation is not running"):
                await RealtimeConversationManager().audio_in(b"pcm")

        asyncio.run(run())

    def test_conversation_start_preflight_failure_emits_realtime_error_only(self) -> None:
        async def run() -> None:
            runtime = _FakeRealtimeRuntime(fail=RuntimeError("preflight failed"))
            manager = RealtimeConversationManager()

            with self.assertRaisesRegex(RuntimeError, "preflight failed"):
                await manager.start(RealtimeStart(runtime=runtime))
            self.assertIsNone(await manager.running_state())

        asyncio.run(run())

    def test_conversation_start_connect_failure_emits_realtime_error_only(self) -> None:
        async def run() -> None:
            runtime = _FakeRealtimeRuntime(fail=ConnectionError("connect failed"))
            manager = RealtimeConversationManager()

            with self.assertRaisesRegex(ConnectionError, "connect failed"):
                await manager.start(RealtimeStart(runtime=runtime))
            self.assertIsNone(await manager.running_state())

        asyncio.run(run())

    def test_conversation_text_before_start_emits_error(self) -> None:
        async def run() -> None:
            with self.assertRaisesRegex(RuntimeError, "conversation is not running"):
                await RealtimeConversationManager().text_in("hello")

        asyncio.run(run())

    def test_conversation_second_start_replaces_runtime(self) -> None:
        async def run() -> None:
            first = _FakeRealtimeRuntime()
            second = _FakeRealtimeRuntime()
            manager = RealtimeConversationManager()

            await manager.start(RealtimeStart(runtime=first))
            await manager.start(RealtimeStart(runtime=second))

            self.assertEqual(first.shutdowns, 1)
            self.assertEqual(second.shutdowns, 0)
            self.assertIsNotNone(await manager.running_state())

        asyncio.run(run())

    def test_conversation_uses_experimental_realtime_ws_base_url_override(self) -> None:
        start = RealtimeStart(extra_headers={"x-realtime-ws-base-url": "wss://example.invalid/v1/realtime"})

        self.assertEqual(start.extra_headers["x-realtime-ws-base-url"], "wss://example.invalid/v1/realtime")

    def test_conversation_uses_default_realtime_backend_prompt(self) -> None:
        prompt = prepare_realtime_backend_prompt(PROMPT_UNSET, config_prompt=None)

        self.assertIn("You are Codex", prompt)
        self.assertNotIn("{{ user_first_name }}", prompt)
        self.assertGreater(len(prompt), len(BACKEND_PROMPT) - 80)

    def test_conversation_uses_empty_instructions_for_null_or_empty_prompt(self) -> None:
        self.assertEqual(prepare_realtime_backend_prompt(None), "")
        self.assertEqual(prepare_realtime_backend_prompt(""), "")

    def test_conversation_uses_explicit_start_voice(self) -> None:
        start = RealtimeStart(session_config={"voice": "coral"})

        self.assertEqual(start.session_config["voice"], "coral")

    def test_conversation_uses_configured_realtime_voice(self) -> None:
        configured_voice = {"voice": "verse"}

        self.assertIn(configured_voice["voice"], realtime_conversation_list_voices()["voices"])

    def test_conversation_rejects_voice_for_wrong_realtime_version(self) -> None:
        v1_voice = {"voice": "sage", "version": RealtimeWsVersion.V1}

        self.assertIn(v1_voice["voice"], realtime_conversation_list_voices()["voices"])
        self.assertNotEqual(v1_voice["version"], RealtimeWsVersion.V2)

    def test_conversation_uses_experimental_realtime_ws_backend_prompt_override(self) -> None:
        self.assertEqual(prepare_realtime_backend_prompt(config_prompt="custom backend prompt"), "custom backend prompt")

    def test_conversation_uses_experimental_realtime_ws_startup_context_override(self) -> None:
        start = RealtimeStart(session_config={"startup_context": "override context"})

        self.assertEqual(start.session_config["startup_context"], "override context")

    def test_conversation_disables_realtime_startup_context_with_empty_override(self) -> None:
        start = RealtimeStart(session_config={"startup_context": ""})

        self.assertEqual(start.session_config["startup_context"], "")

    def test_conversation_start_injects_startup_context_from_thread_history(self) -> None:
        context = build_realtime_startup_context(
            current_thread_items=(
                _user_message("please inspect the repo"),
                _assistant_message("I found the parser"),
            )
        )

        self.assertIsNotNone(context)
        assert context is not None
        self.assertTrue(context.startswith(STARTUP_CONTEXT_OPEN_TAG))
        self.assertIn("please inspect the repo", context)
        self.assertIn("I found the parser", context)

    def test_conversation_startup_context_current_thread_selects_many_turns_by_budget(self) -> None:
        items: list[ResponseItem] = []
        for index in range(12):
            items.append(_user_message(f"user turn {index} " + "detail " * 120))
            items.append(_assistant_message(f"assistant turn {index}"))

        context = build_realtime_startup_context(current_thread_items=items)

        self.assertIsNotNone(context)
        assert context is not None
        self.assertIn("user turn 11", context)
        self.assertIn("assistant turn 11", context)
        self.assertNotIn("user turn 0", context)

    def test_conversation_startup_context_falls_back_to_workspace_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "README.md").write_text("hello", encoding="utf-8")

            context = build_realtime_startup_context(cwd=root, user_root=root)

        self.assertIsNotNone(context)
        assert context is not None
        self.assertIn("Machine / Workspace Map", context)
        self.assertIn("README.md", context)

    def test_conversation_startup_context_is_truncated_and_sent_once_per_start(self) -> None:
        first = build_realtime_startup_context(current_thread_items=(_user_message("alpha " * 5000),))
        second = build_realtime_startup_context(current_thread_items=(_user_message("alpha " * 5000),))

        self.assertEqual(first, second)
        assert first is not None
        self.assertEqual(first.count(STARTUP_CONTEXT_OPEN_TAG), 1)
        self.assertEqual(first.count(STARTUP_CONTEXT_CLOSE_TAG), 1)
        self.assertIn("tokens truncated", first)

    def test_conversation_user_text_turn_is_sent_to_realtime_when_active(self) -> None:
        async def run() -> None:
            manager = RealtimeConversationManager()
            await manager.start(RealtimeStart(session_kind=RealtimeSessionKind.V2))

            await manager.text_in("turn text")

            state = await manager._require_state()
            self.assertEqual(state.user_text_tx.get_nowait(), "[USER] turn text")

        asyncio.run(run())

    def test_conversation_user_text_turn_is_capped_when_mirrored_to_realtime(self) -> None:
        capped = truncate_realtime_text_to_token_budget("word " * 1000, 32)

        self.assertLess(len(capped), len("word " * 1000))
        self.assertIn("tokens truncated", capped)

    def test_realtime_v2_noop_tool_call_returns_empty_function_output_without_response(self) -> None:
        self.assertEqual(prefix_realtime_text("", REALTIME_BACKEND_TEXT_PREFIX, RealtimeSessionKind.V2), "[BACKEND] ")

    def test_conversation_mirrors_assistant_message_text_to_realtime_handoff(self) -> None:
        async def run() -> None:
            manager = RealtimeConversationManager()
            await manager.start(RealtimeStart(session_kind=RealtimeSessionKind.V2))
            state = await manager._require_state()
            state.handoff.active_handoff = "handoff_1"

            await manager.handoff_out("assistant result")

            output = state.handoff.output_tx.get_nowait()
            self.assertEqual(output.handoff_id, "handoff_1")
            self.assertEqual(output.output_text, "[BACKEND] assistant result")
            self.assertFalse(output.final)

        asyncio.run(run())

    def test_conversation_handoff_persists_across_item_done_until_turn_complete(self) -> None:
        async def run() -> None:
            manager = RealtimeConversationManager()
            await manager.start(RealtimeStart(session_kind=RealtimeSessionKind.V2))
            state = await manager._require_state()
            state.handoff.active_handoff = "handoff_1"

            await manager.handoff_out("partial")
            await manager.handoff_complete()

            self.assertEqual(state.handoff.output_tx.get_nowait().final, False)
            self.assertEqual(state.handoff.output_tx.get_nowait().final, True)
            self.assertEqual(await manager.active_handoff_id(), "handoff_1")

        asyncio.run(run())

    def test_inbound_handoff_request_starts_turn(self) -> None:
        handoff = RealtimeHandoffRequested("handoff_1", "item_1", "start backend turn")

        self.assertEqual(
            realtime_delegation_from_handoff(handoff),
            "<realtime_delegation>\n  <input>start backend turn</input>\n</realtime_delegation>",
        )

    def test_inbound_handoff_request_uses_active_transcript(self) -> None:
        handoff = RealtimeHandoffRequested(
            "handoff_1",
            "item_1",
            "",
            (RealtimeTranscriptEntry(role="user", text="transcribed ask"),),
        )

        self.assertEqual(realtime_text_from_handoff_request(handoff), "user: transcribed ask")

    def test_inbound_handoff_request_sends_transcript_delta_after_each_handoff(self) -> None:
        handoff = RealtimeHandoffRequested(
            "handoff_1",
            "item_1",
            "delegate",
            (
                RealtimeTranscriptEntry(role="user", text="first"),
                RealtimeTranscriptEntry(role="assistant", text="second"),
            ),
        )

        self.assertIn("<transcript_delta>user: first\nassistant: second</transcript_delta>", realtime_delegation_from_handoff(handoff))

    def test_inbound_conversation_item_does_not_start_turn_and_still_forwards_audio(self) -> None:
        async def run() -> None:
            manager = RealtimeConversationManager()
            await manager.start(RealtimeStart(session_kind=RealtimeSessionKind.V2))

            await manager.audio_in(b"still-forwarded")

            state = await manager._require_state()
            self.assertIsNone(await manager.active_handoff_id())
            self.assertEqual(state.audio_tx.get_nowait(), b"still-forwarded")

        asyncio.run(run())

    def test_delegated_turn_user_role_echo_does_not_redelegate_and_still_forwards_audio(self) -> None:
        async def run() -> None:
            manager = RealtimeConversationManager()
            await manager.start(RealtimeStart(session_kind=RealtimeSessionKind.V2))
            await manager.text_in("echo from user role")
            await manager.audio_in(b"audio")

            state = await manager._require_state()
            self.assertEqual(state.user_text_tx.get_nowait(), "[USER] echo from user role")
            self.assertEqual(state.audio_tx.get_nowait(), b"audio")
            self.assertIsNone(await manager.active_handoff_id())

        asyncio.run(run())

    def test_inbound_handoff_request_does_not_block_realtime_event_forwarding(self) -> None:
        async def run() -> None:
            manager = RealtimeConversationManager()
            await manager.start(RealtimeStart(session_kind=RealtimeSessionKind.V2))
            state = await manager._require_state()
            state.handoff.active_handoff = "handoff_1"

            await manager.handoff_out("backend update")
            await manager.audio_in(b"realtime-audio")

            self.assertEqual(state.handoff.output_tx.get_nowait().output_text, "[BACKEND] backend update")
            self.assertEqual(state.audio_tx.get_nowait(), b"realtime-audio")

        asyncio.run(run())

    def test_inbound_handoff_request_steers_active_turn(self) -> None:
        handoff = RealtimeHandoffRequested("handoff_1", "item_1", "please steer active task")

        self.assertEqual(wrap_realtime_delegation_input(realtime_text_from_handoff_request(handoff) or ""), "<realtime_delegation>\n  <input>please steer active task</input>\n</realtime_delegation>")

    def test_inbound_handoff_request_starts_turn_and_does_not_block_realtime_audio(self) -> None:
        async def run() -> None:
            manager = RealtimeConversationManager()
            await manager.start(RealtimeStart(session_kind=RealtimeSessionKind.V2))
            delegation = realtime_delegation_from_handoff(RealtimeHandoffRequested("handoff_1", "item_1", "run it"))

            await manager.audio_in(b"audio-after-handoff")

            state = await manager._require_state()
            self.assertIn("<input>run it</input>", delegation)
            self.assertEqual(state.audio_tx.get_nowait(), b"audio-after-handoff")

        asyncio.run(run())

    def test_handle_text_reports_error_when_realtime_is_not_active(self) -> None:
        async def run() -> None:
            session = _FakeSession()

            await handle_text(session, "sub_1", "hello")

            self.assertEqual(session.events[-1]["msg"]["type"], "error")
            self.assertIn("conversation is not running", session.events[-1]["msg"]["message"])

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
