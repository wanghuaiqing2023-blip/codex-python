import unittest

from pycodex.core.unified_exec import (
    HeadTailBuffer,
    UnifiedExecEndEventPlan,
    split_valid_utf8_prefix_with_max,
    unified_exec_failed_end_event_plan,
    unified_exec_success_end_event_plan,
)


class CoreUnifiedExecAsyncWatcherTests(unittest.TestCase):
    def test_split_valid_utf8_prefix_respects_max_bytes_for_ascii(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/async_watcher_tests.rs
        # Behavior anchor: split_valid_utf8_prefix_respects_max_bytes_for_ascii.
        buffer = bytearray(b"hello word!")

        first = split_valid_utf8_prefix_with_max(buffer, 5)

        self.assertEqual(first, b"hello")
        self.assertEqual(buffer, bytearray(b" word!"))

        second = split_valid_utf8_prefix_with_max(buffer, 5)

        self.assertEqual(second, b" word")
        self.assertEqual(buffer, bytearray(b"!"))

    def test_split_valid_utf8_prefix_avoids_splitting_utf8_codepoints(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/async_watcher_tests.rs
        # Behavior anchor: split_valid_utf8_prefix_avoids_splitting_utf8_codepoints.
        codepoint = bytes([0xE7, 0x94, 0xB2])
        buffer = bytearray(codepoint * 3)

        first = split_valid_utf8_prefix_with_max(buffer, 3)

        self.assertEqual(first, codepoint)
        self.assertEqual(buffer, bytearray(codepoint * 2))

    def test_split_valid_utf8_prefix_makes_progress_on_invalid_utf8(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/async_watcher_tests.rs
        # Behavior anchor: split_valid_utf8_prefix_makes_progress_on_invalid_utf8.
        buffer = bytearray([0xFF, ord("a"), ord("b")])

        first = split_valid_utf8_prefix_with_max(buffer, 2)

        self.assertEqual(first, bytes([0xFF]))
        self.assertEqual(buffer, bytearray(b"ab"))

    def test_success_end_event_uses_transcript_as_primary_output(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/async_watcher.rs
        # Behavior anchor: emit_exec_end_for_unified_exec resolves
        # aggregated_output from transcript before fallback output.
        transcript = HeadTailBuffer.new(100)
        transcript.push_chunk(b"real transcript")

        plan = unified_exec_success_end_event_plan(
            call_id="call-1",
            command=("bash", "-lc", "echo hi"),
            cwd="/repo",
            process_id=123,
            transcript=transcript,
            fallback_output="fallback",
            exit_code=7,
            duration_ms=42,
        )

        self.assertIsInstance(plan, UnifiedExecEndEventPlan)
        self.assertEqual(plan.call_id, "call-1")
        self.assertEqual(plan.command, ("bash", "-lc", "echo hi"))
        self.assertEqual(plan.cwd, "/repo")
        self.assertEqual(plan.process_id, "123")
        self.assertEqual(plan.source, "unified_exec_startup")
        self.assertEqual(plan.status, "success")
        self.assertEqual(plan.exit_code, 7)
        self.assertEqual(plan.stdout, "real transcript")
        self.assertEqual(plan.stderr, "")
        self.assertEqual(plan.aggregated_output, "real transcript")
        self.assertEqual(plan.duration_ms, 42)
        self.assertFalse(plan.timed_out)

    def test_success_end_event_uses_fallback_when_transcript_empty(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/async_watcher.rs
        # Behavior anchor: resolve_aggregated_output returns fallback when the
        # HeadTailBuffer has no retained bytes.
        plan = unified_exec_success_end_event_plan(
            call_id="call-2",
            command=("python", "-V"),
            cwd="/repo",
            process_id=None,
            transcript=HeadTailBuffer.new(100),
            fallback_output="fallback only",
            exit_code=0,
        )

        self.assertEqual(plan.stdout, "fallback only")
        self.assertEqual(plan.aggregated_output, "fallback only")
        self.assertIsNone(plan.process_id)

    def test_failed_end_event_prefers_explicit_fallback_stdout(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/async_watcher.rs
        # Behavior anchor: emit_failed_exec_end_for_unified_exec uses explicit
        # fallback_output as stdout when it is non-empty.
        transcript = HeadTailBuffer.new(100)
        transcript.push_chunk(b"transcript should not win")

        plan = unified_exec_failed_end_event_plan(
            call_id="call-3",
            command=("bash", "-lc", "bad"),
            cwd="/repo",
            process_id="456",
            transcript=transcript,
            fallback_output="pre-denial stdout",
            message="permission denied",
            duration_ms=5,
        )

        self.assertEqual(plan.status, "failed")
        self.assertEqual(plan.exit_code, -1)
        self.assertEqual(plan.stdout, "pre-denial stdout")
        self.assertEqual(plan.stderr, "permission denied")
        self.assertEqual(plan.aggregated_output, "pre-denial stdout\npermission denied")
        self.assertEqual(plan.process_id, "456")

    def test_failed_end_event_uses_message_only_when_stdout_empty(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/async_watcher.rs
        # Behavior anchor: failed aggregated output is message-only when stdout
        # and fallback output are both empty.
        plan = unified_exec_failed_end_event_plan(
            call_id="call-4",
            command=("bash", "-lc", "bad"),
            cwd="/repo",
            process_id=None,
            transcript=HeadTailBuffer.new(100),
            fallback_output="",
            message="process failed",
        )

        self.assertEqual(plan.stdout, "")
        self.assertEqual(plan.stderr, "process failed")
        self.assertEqual(plan.aggregated_output, "process failed")


if __name__ == "__main__":
    unittest.main()
