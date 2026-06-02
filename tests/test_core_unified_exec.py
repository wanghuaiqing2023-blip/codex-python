import sys
import time
import unittest
from types import SimpleNamespace

from pycodex.core import (
    DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    EARLY_EXIT_GRACE_PERIOD_MS,
    HeadTailBuffer,
    MAX_EXEC_OUTPUT_DELTAS_PER_CALL,
    MAX_UNIFIED_EXEC_PROCESSES,
    MAX_YIELD_TIME_MS,
    MIN_EMPTY_YIELD_TIME_MS,
    MIN_YIELD_TIME_MS,
    ProcessEntry,
    ProcessOutputChunk,
    ProcessState,
    TRAILING_OUTPUT_GRACE_MS,
    UNIFIED_EXEC_OUTPUT_DELTA_MAX_BYTES,
    UNIFIED_EXEC_OUTPUT_MAX_BYTES,
    UNIFIED_EXEC_OUTPUT_MAX_TOKENS,
    UNIFIED_EXEC_ENV,
    UnifiedExecError,
    UnifiedExecProcessManager,
    apply_unified_exec_env,
    clamp_yield_time,
    env_overlay_for_exec_server,
    exec_server_after_seq,
    exec_server_process_id,
    exec_server_write_status_accepted,
    exec_server_write_status_marks_exited,
    generate_chunk_id,
    process_id_to_prune_from_meta,
    process_output_chunk,
    resolve_aggregated_output,
    resolve_failed_aggregated_output,
    resolve_max_tokens,
    resolve_write_stdin_yield_time,
    should_emit_exec_output_delta,
    should_emit_terminal_interaction,
    split_valid_utf8_prefix,
    split_valid_utf8_prefix_with_max,
    terminal_interaction_process_id,
)
from pycodex.protocol import ExecToolCallOutput, StreamOutput, TruncationPolicyConfig


class CoreUnifiedExecHeadTailBufferTests(unittest.TestCase):
    def test_keeps_prefix_and_suffix_when_over_budget(self) -> None:
        buffer = HeadTailBuffer.new(10)

        buffer.push_chunk(b"0123456789")
        self.assertEqual(buffer.omitted_bytes(), 0)
        buffer.push_chunk(b"ab")

        rendered = buffer.to_bytes().decode()
        self.assertGreater(buffer.omitted_bytes(), 0)
        self.assertTrue(rendered.startswith("01234"))
        self.assertTrue(rendered.endswith("89ab"))

    def test_max_bytes_zero_drops_everything(self) -> None:
        buffer = HeadTailBuffer.new(0)
        buffer.push_chunk(b"abc")

        self.assertEqual(buffer.retained_bytes(), 0)
        self.assertEqual(buffer.omitted_bytes(), 3)
        self.assertEqual(buffer.to_bytes(), b"")
        self.assertEqual(buffer.snapshot_chunks(), [])

    def test_head_budget_zero_keeps_only_last_byte_in_tail(self) -> None:
        buffer = HeadTailBuffer.new(1)
        buffer.push_chunk(b"abc")

        self.assertEqual(buffer.retained_bytes(), 1)
        self.assertEqual(buffer.omitted_bytes(), 2)
        self.assertEqual(buffer.to_bytes(), b"c")

    def test_draining_resets_state(self) -> None:
        buffer = HeadTailBuffer.new(10)
        buffer.push_chunk(b"0123456789")
        buffer.push_chunk(b"ab")

        drained = buffer.drain_chunks()

        self.assertTrue(drained)
        self.assertEqual(buffer.retained_bytes(), 0)
        self.assertEqual(buffer.omitted_bytes(), 0)
        self.assertEqual(buffer.to_bytes(), b"")

    def test_chunk_larger_than_tail_budget_keeps_only_tail_end(self) -> None:
        buffer = HeadTailBuffer.new(10)
        buffer.push_chunk(b"0123456789")
        buffer.push_chunk(b"ABCDEFGHIJK")

        out = buffer.to_bytes().decode()
        self.assertTrue(out.startswith("01234"))
        self.assertTrue(out.endswith("GHIJK"))
        self.assertGreater(buffer.omitted_bytes(), 0)

    def test_fills_head_then_tail_across_multiple_chunks(self) -> None:
        buffer = HeadTailBuffer.new(10)

        buffer.push_chunk(b"01")
        buffer.push_chunk(b"234")
        self.assertEqual(buffer.to_bytes(), b"01234")

        buffer.push_chunk(b"567")
        buffer.push_chunk(b"89")
        self.assertEqual(buffer.to_bytes(), b"0123456789")
        self.assertEqual(buffer.omitted_bytes(), 0)

        buffer.push_chunk(b"a")
        self.assertEqual(buffer.to_bytes(), b"012346789a")
        self.assertEqual(buffer.omitted_bytes(), 1)

    def test_default_matches_unified_exec_output_constants(self) -> None:
        buffer = HeadTailBuffer()
        self.assertEqual(buffer.max_bytes, UNIFIED_EXEC_OUTPUT_MAX_BYTES)
        self.assertEqual(UNIFIED_EXEC_OUTPUT_MAX_TOKENS, UNIFIED_EXEC_OUTPUT_MAX_BYTES // 4)

    def test_unified_exec_constants_match_upstream_defaults(self) -> None:
        self.assertEqual(MIN_YIELD_TIME_MS, 250)
        self.assertEqual(MIN_EMPTY_YIELD_TIME_MS, 5_000)
        self.assertEqual(MAX_YIELD_TIME_MS, 30_000)
        self.assertEqual(DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS, 300_000)
        self.assertEqual(DEFAULT_MAX_OUTPUT_TOKENS, 10_000)
        self.assertEqual(EARLY_EXIT_GRACE_PERIOD_MS, 150)
        self.assertEqual(TRAILING_OUTPUT_GRACE_MS, 100)
        self.assertEqual(UNIFIED_EXEC_OUTPUT_DELTA_MAX_BYTES, 8192)
        self.assertEqual(MAX_EXEC_OUTPUT_DELTAS_PER_CALL, 10_000)
        self.assertEqual(MAX_UNIFIED_EXEC_PROCESSES, 64)

    def test_should_emit_exec_output_delta_uses_upstream_count_cap(self) -> None:
        self.assertTrue(should_emit_exec_output_delta(0))
        self.assertTrue(should_emit_exec_output_delta(MAX_EXEC_OUTPUT_DELTAS_PER_CALL - 1))
        self.assertFalse(should_emit_exec_output_delta(MAX_EXEC_OUTPUT_DELTAS_PER_CALL))
        with self.assertRaises(TypeError):
            should_emit_exec_output_delta(True)  # type: ignore[arg-type]

    def test_resolve_aggregated_output_uses_fallback_only_when_buffer_empty(self) -> None:
        buffer = HeadTailBuffer.new(20)

        self.assertEqual(resolve_aggregated_output(buffer, "fallback"), "fallback")

        buffer.push_chunk(b"real output")
        self.assertEqual(resolve_aggregated_output(buffer, "fallback"), "real output")

    def test_resolve_aggregated_output_decodes_lossy_utf8_like_rust(self) -> None:
        buffer = HeadTailBuffer.new(20)
        buffer.push_chunk(b"ok\xffdone")

        self.assertEqual(resolve_aggregated_output(buffer, "fallback"), "ok\ufffddone")

    def test_resolve_failed_aggregated_output_matches_watcher_failure_join(self) -> None:
        self.assertEqual(resolve_failed_aggregated_output("", "failed"), "failed")
        self.assertEqual(resolve_failed_aggregated_output("stdout", "failed"), "stdout\nfailed")
        with self.assertRaises(TypeError):
            resolve_failed_aggregated_output(b"stdout", "failed")  # type: ignore[arg-type]

    def test_terminal_interaction_helpers_match_write_stdin_event_boundary(self) -> None:
        self.assertTrue(should_emit_terminal_interaction("input\n", None))
        self.assertTrue(should_emit_terminal_interaction("", 45))
        self.assertFalse(should_emit_terminal_interaction("", None))
        self.assertEqual(terminal_interaction_process_id(None, 45), 45)
        self.assertEqual(terminal_interaction_process_id(46, 45), 46)
        with self.assertRaises(TypeError):
            should_emit_terminal_interaction(b"input", None)  # type: ignore[arg-type]

    def test_split_valid_utf8_prefix_caps_delta_and_drains_buffer(self) -> None:
        buffer = bytearray("abc甲乙".encode("utf-8"))

        prefix = split_valid_utf8_prefix_with_max(buffer, 5)

        self.assertEqual(prefix, b"abc")
        self.assertEqual(buffer.decode("utf-8"), "甲乙")

    def test_split_valid_utf8_prefix_makes_progress_for_incomplete_multibyte(self) -> None:
        buffer = bytearray("甲".encode("utf-8")[:2])

        prefix = split_valid_utf8_prefix(buffer)

        self.assertEqual(prefix, b"\xe7")
        self.assertEqual(buffer, bytearray(b"\x94"))

    def test_split_valid_utf8_prefix_returns_none_for_empty_buffer(self) -> None:
        self.assertIsNone(split_valid_utf8_prefix(bytearray()))

    def test_process_output_chunk_updates_transcript_and_emits_deltas(self) -> None:
        pending = bytearray()
        transcript = HeadTailBuffer.new(20)

        chunks, emitted = process_output_chunk(pending, transcript, 0, "hi".encode("utf-8"))

        self.assertEqual(chunks, [ProcessOutputChunk(b"hi", "hi")])
        self.assertEqual(emitted, 1)
        self.assertEqual(pending, bytearray())
        self.assertEqual(transcript.to_bytes(), b"hi")

    def test_process_output_chunk_holds_incomplete_utf8_until_boundary(self) -> None:
        encoded = "甲".encode("utf-8")
        pending = bytearray(encoded[:2])
        transcript = HeadTailBuffer.new(20)

        chunks, emitted = process_output_chunk(pending, transcript, 0, encoded[2:])

        self.assertEqual(chunks, [ProcessOutputChunk(encoded, "甲")])
        self.assertEqual(emitted, 1)
        self.assertEqual(pending, bytearray())
        self.assertEqual(transcript.to_bytes(), encoded)

    def test_process_output_chunk_respects_delta_cap_but_keeps_transcript(self) -> None:
        pending = bytearray()
        transcript = HeadTailBuffer.new(20)

        chunks, emitted = process_output_chunk(
            pending,
            transcript,
            MAX_EXEC_OUTPUT_DELTAS_PER_CALL,
            b"after-cap",
        )

        self.assertEqual(chunks, [ProcessOutputChunk(b"after-cap", None)])
        self.assertEqual(emitted, MAX_EXEC_OUTPUT_DELTAS_PER_CALL)
        self.assertEqual(transcript.to_bytes(), b"after-cap")

    def test_clamp_yield_time_uses_upstream_bounds(self) -> None:
        self.assertEqual(clamp_yield_time(0), MIN_YIELD_TIME_MS)
        self.assertEqual(clamp_yield_time(MIN_YIELD_TIME_MS - 1), MIN_YIELD_TIME_MS)
        self.assertEqual(clamp_yield_time(2_500), 2_500)
        self.assertEqual(clamp_yield_time(MAX_YIELD_TIME_MS + 1), MAX_YIELD_TIME_MS)

    def test_resolve_write_stdin_yield_time_uses_empty_poll_bounds(self) -> None:
        self.assertEqual(resolve_write_stdin_yield_time("input", 0), MIN_YIELD_TIME_MS)
        self.assertEqual(resolve_write_stdin_yield_time("input", 2_500), 2_500)
        self.assertEqual(resolve_write_stdin_yield_time("", 0), MIN_EMPTY_YIELD_TIME_MS)
        self.assertEqual(
            resolve_write_stdin_yield_time("", DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS + 1),
            DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS,
        )

    def test_resolve_max_tokens_uses_default_only_when_missing(self) -> None:
        self.assertEqual(resolve_max_tokens(None), DEFAULT_MAX_OUTPUT_TOKENS)
        self.assertEqual(resolve_max_tokens(0), 0)
        self.assertEqual(resolve_max_tokens(123), 123)

    def test_generate_chunk_id_returns_six_hex_digits(self) -> None:
        chunk_id = generate_chunk_id()

        self.assertEqual(len(chunk_id), 6)
        self.assertTrue(all(ch in "0123456789abcdef" for ch in chunk_id))

    def test_process_state_defaults_to_running_without_exit_data(self) -> None:
        state = ProcessState()

        self.assertFalse(state.has_exited)
        self.assertIsNone(state.exit_code)
        self.assertIsNone(state.failure_message)

    def test_process_state_exited_preserves_failure_message(self) -> None:
        state = ProcessState(failure_message="stderr reader failed")

        exited = state.exited(7)

        self.assertTrue(exited.has_exited)
        self.assertEqual(exited.exit_code, 7)
        self.assertEqual(exited.failure_message, "stderr reader failed")
        self.assertFalse(state.has_exited)

    def test_process_state_failed_preserves_exit_code(self) -> None:
        state = ProcessState(exit_code=2)

        failed = state.failed("process crashed")

        self.assertTrue(failed.has_exited)
        self.assertEqual(failed.exit_code, 2)
        self.assertEqual(failed.failure_message, "process crashed")

    def test_unified_exec_error_factories_match_upstream_messages(self) -> None:
        cases = (
            (UnifiedExecError.create_process("no pty"), "Failed to create unified exec process: no pty"),
            (UnifiedExecError.process_failed("lost watcher"), "Unified exec process failed: lost watcher"),
            (UnifiedExecError.unknown_process_id(42), "Unknown process id 42"),
            (UnifiedExecError.write_to_stdin(), "failed to write to stdin"),
            (
                UnifiedExecError.stdin_closed(),
                "stdin is closed for this session; rerun exec_command with tty=true to keep stdin open",
            ),
            (UnifiedExecError.missing_command_line(), "missing command line for unified exec request"),
        )

        for error, message in cases:
            self.assertIsInstance(error, UnifiedExecError)
            self.assertEqual(str(error), message)

    def test_unified_exec_error_carries_variant_data(self) -> None:
        output = ExecToolCallOutput(aggregated_output=StreamOutput.new("sandbox said no"))

        error = UnifiedExecError.sandbox_denied("operation not permitted", output)

        self.assertEqual(error.kind, UnifiedExecError.SANDBOX_DENIED)
        self.assertEqual(error.message, "operation not permitted")
        self.assertIs(error.output, output)
        self.assertEqual(str(error), "Command denied by sandbox: operation not permitted")

    def test_unified_exec_env_injects_defaults(self) -> None:
        self.assertEqual(apply_unified_exec_env({}), dict(UNIFIED_EXEC_ENV))

    def test_unified_exec_env_overrides_existing_values(self) -> None:
        env = apply_unified_exec_env({"NO_COLOR": "0", "PATH": "/usr/bin"})

        self.assertEqual(env["NO_COLOR"], "1")
        self.assertEqual(env["PATH"], "/usr/bin")

    def test_env_overlay_for_exec_server_keeps_runtime_changes_only(self) -> None:
        local_policy_env = {
            "HOME": "/client-home",
            "PATH": "/client-path",
            "SHELL_SET": "policy",
        }
        request_env = {
            "HOME": "/client-home",
            "PATH": "/sandbox-path",
            "SHELL_SET": "policy",
            "CODEX_THREAD_ID": "thread-1",
            "CODEX_SANDBOX_NETWORK_DISABLED": "1",
        }

        self.assertEqual(
            env_overlay_for_exec_server(request_env, local_policy_env),
            {
                "PATH": "/sandbox-path",
                "CODEX_THREAD_ID": "thread-1",
                "CODEX_SANDBOX_NETWORK_DISABLED": "1",
            },
        )

    def test_exec_server_process_id_matches_unified_exec_process_id(self) -> None:
        self.assertEqual(exec_server_process_id(4321), "4321")

    def test_exec_server_after_seq_matches_checked_sub_boundary(self) -> None:
        self.assertIsNone(exec_server_after_seq(None))
        self.assertIsNone(exec_server_after_seq(0))
        self.assertEqual(exec_server_after_seq(1), 0)
        self.assertEqual(exec_server_after_seq(42), 41)
        with self.assertRaises(TypeError):
            exec_server_after_seq(True)  # type: ignore[arg-type]

    def test_exec_server_write_status_helpers_match_rust_boundaries(self) -> None:
        self.assertTrue(exec_server_write_status_accepted("Accepted"))
        self.assertFalse(exec_server_write_status_accepted("Starting"))
        self.assertFalse(exec_server_write_status_accepted("UnknownProcess"))
        self.assertFalse(exec_server_write_status_accepted("StdinClosed"))
        self.assertFalse(exec_server_write_status_marks_exited("Accepted"))
        self.assertFalse(exec_server_write_status_marks_exited("Starting"))
        self.assertTrue(exec_server_write_status_marks_exited("UnknownProcess"))
        self.assertTrue(exec_server_write_status_marks_exited("StdinClosed"))
        with self.assertRaises(TypeError):
            exec_server_write_status_accepted(None)  # type: ignore[arg-type]

    def test_process_pruning_prefers_exited_processes_outside_recently_used(self) -> None:
        meta = [
            (1, 10, False),
            (2, 20, True),
            (3, 30, False),
            (4, 31, False),
            (5, 32, False),
            (6, 33, False),
            (7, 34, False),
            (8, 35, False),
            (9, 36, False),
            (10, 37, False),
        ]

        self.assertEqual(process_id_to_prune_from_meta(meta), 2)

    def test_process_pruning_falls_back_to_lru_when_no_exited(self) -> None:
        meta = [
            (1, 10, False),
            (2, 20, False),
            (3, 30, False),
            (4, 31, False),
            (5, 32, False),
            (6, 33, False),
            (7, 34, False),
            (8, 35, False),
            (9, 36, False),
            (10, 37, False),
        ]

        self.assertEqual(process_id_to_prune_from_meta(meta), 1)

    def test_process_pruning_protects_recent_processes_even_if_exited(self) -> None:
        meta = [
            (1, 10, False),
            (2, 20, False),
            (3, 30, True),
            (4, 31, False),
            (5, 32, False),
            (6, 33, False),
            (7, 34, False),
            (8, 35, False),
            (9, 36, False),
            (10, 37, True),
        ]

        self.assertEqual(process_id_to_prune_from_meta(meta), 1)

    def test_process_pruning_empty_or_all_protected_has_no_candidate(self) -> None:
        self.assertIsNone(process_id_to_prune_from_meta([]))
        self.assertIsNone(process_id_to_prune_from_meta([(1, 10, True), (2, 20, False)]))

    def test_unified_exec_process_manager_allocates_deterministic_ids(self) -> None:
        manager = UnifiedExecProcessManager()

        first = manager.allocate_process_id()
        second = manager.allocate_process_id()

        self.assertEqual(first, 1000)
        self.assertEqual(second, 1001)
        self.assertEqual(manager.reserved_process_ids(), frozenset({1000, 1001}))

    def test_unified_exec_process_manager_release_removes_reserved_and_entry(self) -> None:
        manager = UnifiedExecProcessManager()
        process_id = manager.allocate_process_id()
        process = FakeUnifiedExecProcess(False)
        manager.store_process(process_id, process, call_id="call-1", last_used=10)

        entry = manager.release_process_id(process_id)

        self.assertIsInstance(entry, ProcessEntry)
        self.assertIs(entry.process, process)
        self.assertIsNone(manager.get_process(process_id))
        self.assertEqual(manager.reserved_process_ids(), frozenset())

    def test_unified_exec_process_manager_prunes_exited_process_when_full(self) -> None:
        manager = UnifiedExecProcessManager(max_processes=10)
        ids = [manager.allocate_process_id() for _ in range(10)]
        pruned = None
        for index, process_id in enumerate(ids):
            pruned = manager.store_process(
                process_id,
                FakeUnifiedExecProcess(index == 1),
                last_used=10 + index,
            )

        self.assertIsNotNone(pruned)
        assert pruned is not None
        self.assertEqual(pruned.process_id, ids[1])
        self.assertIsNone(manager.get_process(ids[1]))
        self.assertEqual(manager.process_count(), 9)

    def test_unified_exec_process_manager_protects_recent_entries_when_pruning(self) -> None:
        manager = UnifiedExecProcessManager(max_processes=10)
        ids = [manager.allocate_process_id() for _ in range(10)]
        for index, process_id in enumerate(ids):
            manager.store_process(
                process_id,
                FakeUnifiedExecProcess(index in {2, 9}),
                last_used=10 + index,
            )

        self.assertIsNotNone(manager.get_process(ids[9]))
        self.assertIsNone(manager.get_process(ids[0]))
        self.assertEqual(manager.process_count(), 9)

    def test_unified_exec_process_manager_terminate_all_processes_clears_store(self) -> None:
        manager = UnifiedExecProcessManager(max_processes=4)
        first = manager.allocate_process_id()
        second = manager.allocate_process_id()
        first_process = FakeUnifiedExecProcess(False)
        second_process = FakeUnifiedExecProcess(False)
        manager.store_process(first, first_process, last_used=10)
        manager.store_process(second, second_process, last_used=20)

        entries = manager.terminate_all_processes()

        self.assertEqual({entry.process_id for entry in entries}, {first, second})
        self.assertTrue(first_process.terminated)
        self.assertTrue(second_process.terminated)
        self.assertEqual(manager.process_count(), 0)
        self.assertEqual(manager.reserved_process_ids(), frozenset())

    def test_unified_exec_process_manager_exec_command_returns_completed_output(self) -> None:
        manager = UnifiedExecProcessManager()
        process_id = manager.allocate_process_id()

        output = manager.exec_command(
            SimpleNamespace(
                command=(sys.executable, "-c", "print('managed hello')"),
                process_id=process_id,
                yield_time_ms=1_000,
                max_output_tokens=None,
                cwd=None,
                environment=None,
                hook_command="python quick",
                tty=False,
                truncation_policy=TruncationPolicyConfig.tokens(10_000),
            )
        )

        self.assertIsNone(output.process_id)
        self.assertEqual(output.exit_code, 0)
        self.assertIn(b"managed hello", output.raw_output)
        self.assertIsNone(manager.get_process(process_id))
        self.assertNotIn(process_id, manager.reserved_process_ids())

    def test_unified_exec_process_manager_write_stdin_completes_live_session(self) -> None:
        manager = UnifiedExecProcessManager()
        process_id = manager.allocate_process_id()
        script = (
            "import sys; "
            "print('ready', flush=True); "
            "line = sys.stdin.readline(); "
            "print('got:' + line.strip(), flush=True)"
        )

        initial = manager.exec_command(
            SimpleNamespace(
                command=(sys.executable, "-c", script),
                process_id=process_id,
                yield_time_ms=250,
                max_output_tokens=None,
                cwd=None,
                environment=None,
                hook_command="python interactive",
                tty=True,
                truncation_policy=TruncationPolicyConfig.tokens(10_000),
            )
        )

        self.assertEqual(initial.process_id, process_id)
        self.assertIn(b"ready", initial.raw_output)
        self.assertIsNotNone(manager.get_process(process_id))

        followup = manager.write_stdin(
            SimpleNamespace(
                process_id=process_id,
                input="hello\n",
                yield_time_ms=1_000,
                max_output_tokens=None,
            )
        )

        self.assertIsNone(followup.process_id)
        self.assertEqual(followup.exit_code, 0)
        self.assertIn(b"got:hello", followup.raw_output)
        self.assertIsNone(manager.get_process(process_id))

    def test_write_stdin_to_recently_exited_session_returns_final_output(self) -> None:
        manager = UnifiedExecProcessManager()
        process_id = manager.allocate_process_id()
        script = (
            "import sys, time; "
            "print('ready', flush=True); "
            "time.sleep(0.2); "
            "print('late', flush=True)"
        )

        initial = manager.exec_command(
            SimpleNamespace(
                command=(sys.executable, "-c", script),
                process_id=process_id,
                yield_time_ms=250,
                max_output_tokens=None,
                cwd=None,
                environment=None,
                hook_command="python short-lived interactive",
                tty=True,
                truncation_policy=TruncationPolicyConfig.tokens(10_000),
            )
        )

        self.assertEqual(initial.process_id, process_id)
        self.assertIn(b"ready", initial.raw_output)
        time.sleep(0.5)

        followup = manager.write_stdin(
            SimpleNamespace(
                process_id=process_id,
                input="hello after exit\n",
                yield_time_ms=250,
                max_output_tokens=None,
            )
        )

        self.assertIsNone(followup.process_id)
        self.assertEqual(followup.exit_code, 0)
        self.assertIn(b"late", followup.raw_output)
        self.assertIsNone(manager.get_process(process_id))


class FakeUnifiedExecProcess:
    def __init__(self, exited: bool) -> None:
        self.exited = exited
        self.terminated = False

    def has_exited(self) -> bool:
        return self.exited

    def terminate(self) -> None:
        self.terminated = True


if __name__ == "__main__":
    unittest.main()
