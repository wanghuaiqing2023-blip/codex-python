import unittest

from pycodex.core import (
    DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    HeadTailBuffer,
    MAX_UNIFIED_EXEC_PROCESSES,
    MAX_YIELD_TIME_MS,
    MIN_EMPTY_YIELD_TIME_MS,
    MIN_YIELD_TIME_MS,
    ProcessState,
    UNIFIED_EXEC_OUTPUT_MAX_BYTES,
    UNIFIED_EXEC_OUTPUT_MAX_TOKENS,
    UNIFIED_EXEC_ENV,
    UnifiedExecError,
    apply_unified_exec_env,
    clamp_yield_time,
    env_overlay_for_exec_server,
    exec_server_process_id,
    generate_chunk_id,
    process_id_to_prune_from_meta,
    resolve_max_tokens,
)
from pycodex.protocol import ExecToolCallOutput, StreamOutput


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
        self.assertEqual(MAX_UNIFIED_EXEC_PROCESSES, 64)

    def test_clamp_yield_time_uses_upstream_bounds(self) -> None:
        self.assertEqual(clamp_yield_time(0), MIN_YIELD_TIME_MS)
        self.assertEqual(clamp_yield_time(MIN_YIELD_TIME_MS - 1), MIN_YIELD_TIME_MS)
        self.assertEqual(clamp_yield_time(2_500), 2_500)
        self.assertEqual(clamp_yield_time(MAX_YIELD_TIME_MS + 1), MAX_YIELD_TIME_MS)

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


if __name__ == "__main__":
    unittest.main()
