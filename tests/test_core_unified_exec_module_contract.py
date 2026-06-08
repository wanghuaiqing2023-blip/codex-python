import unittest
from types import SimpleNamespace

from pycodex.core.unified_exec import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    MAX_YIELD_TIME_MS,
    MIN_YIELD_TIME_MS,
    ExecCommandRequest,
    ProcessStore,
    UnifiedExecContext,
    WriteStdinRequest,
    clamp_yield_time,
    generate_chunk_id,
    resolve_max_tokens,
)


class CoreUnifiedExecModuleContractTests(unittest.TestCase):
    def test_context_preserves_session_turn_and_call_id(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/mod.rs
        # Behavior anchor: UnifiedExecContext::new stores session, turn, call_id.
        session = object()
        turn = object()

        context = UnifiedExecContext(session=session, turn=turn, call_id="call-1")

        self.assertIs(context.session, session)
        self.assertIs(context.turn, turn)
        self.assertEqual(context.call_id, "call-1")

    def test_exec_command_request_preserves_root_module_fields(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/mod.rs
        # Behavior anchor: ExecCommandRequest root-module data boundary.
        request = ExecCommandRequest(
            command=["bash", "-lc", "echo hi"],
            shell_type="bash",
            hook_command="echo hi",
            process_id=123,
            yield_time_ms=500,
            max_output_tokens=42,
            cwd="/repo",
            sandbox_cwd="/sandbox",
            environment=SimpleNamespace(name="env"),
            network=SimpleNamespace(name="net"),
            tty=False,
            sandbox_permissions="use-default",
            additional_permissions={"network": True},
            additional_permissions_preapproved=True,
            justification="needed",
            prefix_rule=["bash", "-lc"],
        )

        self.assertEqual(request.command, ("bash", "-lc", "echo hi"))
        self.assertEqual(request.shell_type, "bash")
        self.assertEqual(request.hook_command, "echo hi")
        self.assertEqual(request.process_id, 123)
        self.assertEqual(request.yield_time_ms, 500)
        self.assertEqual(request.max_output_tokens, 42)
        self.assertEqual(request.cwd, "/repo")
        self.assertEqual(request.sandbox_cwd, "/sandbox")
        self.assertFalse(request.tty)
        self.assertTrue(request.additional_permissions_preapproved)
        self.assertEqual(request.justification, "needed")
        self.assertEqual(request.prefix_rule, ("bash", "-lc"))

    def test_write_stdin_request_preserves_root_module_fields(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/mod.rs
        # Behavior anchor: WriteStdinRequest root-module data boundary.
        request = WriteStdinRequest(
            process_id=456,
            input="hello\n",
            yield_time_ms=750,
            max_output_tokens=100,
            truncation_policy="tokens",
        )

        self.assertEqual(request.process_id, 456)
        self.assertEqual(request.input, "hello\n")
        self.assertEqual(request.yield_time_ms, 750)
        self.assertEqual(request.max_output_tokens, 100)
        self.assertEqual(request.truncation_policy, "tokens")

    def test_process_store_remove_drops_reserved_and_process_entry(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/mod.rs
        # Behavior anchor: ProcessStore::remove removes both reserved id and
        # process map entry.
        entry = object()
        store = ProcessStore(processes={123: entry}, reserved_process_ids={123, 456})

        removed = store.remove(123)

        self.assertIs(removed, entry)
        self.assertNotIn(123, store.processes)
        self.assertNotIn(123, store.reserved_process_ids)
        self.assertIn(456, store.reserved_process_ids)

    def test_module_helpers_match_root_contract(self) -> None:
        # Rust source: codex-rs/core/src/unified_exec/mod.rs
        # Behavior anchors: clamp_yield_time, resolve_max_tokens,
        # generate_chunk_id.
        self.assertEqual(clamp_yield_time(0), MIN_YIELD_TIME_MS)
        self.assertEqual(clamp_yield_time(MAX_YIELD_TIME_MS + 1), MAX_YIELD_TIME_MS)
        self.assertEqual(resolve_max_tokens(None), DEFAULT_MAX_OUTPUT_TOKENS)
        self.assertEqual(resolve_max_tokens(0), 0)

        chunk_id = generate_chunk_id()
        self.assertEqual(len(chunk_id), 6)
        self.assertTrue(all(ch in "0123456789abcdef" for ch in chunk_id))


if __name__ == "__main__":
    unittest.main()
