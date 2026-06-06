import unittest

from pycodex.core.tools.handlers.unified_exec import (
    DEFAULT_EXEC_YIELD_TIME_MS,
    DEFAULT_WRITE_STDIN_YIELD_TIME_MS,
    I32_MAX,
    I32_MIN,
    ExecCommandArgs,
    WriteStdinArgs,
)
from pycodex.protocol import SandboxPermissions


class CoreUnifiedExecHandlerArgsContractTests(unittest.TestCase):
    def test_exec_command_args_use_rust_deserialize_defaults(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/unified_exec.rs
        # Behavior anchor: ExecCommandArgs serde defaults:
        # workdir/shell/login/max_output_tokens/additional permissions/
        # justification/prefix_rule default to None, tty defaults false,
        # yield_time_ms defaults to default_exec_yield_time_ms(), and
        # sandbox_permissions defaults to SandboxPermissions::UseDefault.
        args = ExecCommandArgs.from_json('{"cmd":"echo hello"}')

        self.assertEqual(args.cmd, "echo hello")
        self.assertIsNone(args.workdir)
        self.assertIsNone(args.shell)
        self.assertIsNone(args.login)
        self.assertFalse(args.tty)
        self.assertEqual(args.yield_time_ms, DEFAULT_EXEC_YIELD_TIME_MS)
        self.assertIsNone(args.max_output_tokens)
        self.assertEqual(args.sandbox_permissions, SandboxPermissions.USE_DEFAULT)
        self.assertIsNone(args.additional_permissions)
        self.assertIsNone(args.justification)
        self.assertIsNone(args.prefix_rule)

    def test_exec_command_args_preserve_zero_max_output_tokens_and_prefix_rule(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/unified_exec.rs
        # Behavior anchor: max_output_tokens is Option<usize>; explicit zero
        # is preserved, and prefix_rule is Option<Vec<String>>.
        args = ExecCommandArgs.from_json(
            '{"cmd":"pwd","max_output_tokens":0,"prefix_rule":["pwd"]}'
        )

        self.assertEqual(args.max_output_tokens, 0)
        self.assertEqual(args.prefix_rule, ("pwd",))

    def test_exec_command_args_reject_out_of_range_u64_and_usize(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/unified_exec.rs
        # Behavior anchor: yield_time_ms is u64 and max_output_tokens is usize.
        with self.assertRaisesRegex(ValueError, "yield_time_ms must fit in u64"):
            ExecCommandArgs.from_json('{"cmd":"pwd","yield_time_ms":-1}')

        with self.assertRaisesRegex(ValueError, "max_output_tokens must fit in usize"):
            ExecCommandArgs.from_json('{"cmd":"pwd","max_output_tokens":-1}')

    def test_write_stdin_args_use_rust_deserialize_defaults(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/unified_exec/write_stdin.rs
        # Behavior anchor: WriteStdinArgs serde defaults: chars defaults to
        # empty string, yield_time_ms defaults to
        # default_write_stdin_yield_time_ms(), max_output_tokens defaults None.
        args = WriteStdinArgs.from_json('{"session_id":45}')

        self.assertEqual(args.session_id, 45)
        self.assertEqual(args.chars, "")
        self.assertEqual(args.yield_time_ms, DEFAULT_WRITE_STDIN_YIELD_TIME_MS)
        self.assertIsNone(args.max_output_tokens)

    def test_write_stdin_args_enforce_i32_session_id(self) -> None:
        # Rust source: codex-rs/core/src/tools/handlers/unified_exec/write_stdin.rs
        # Behavior anchor: the model-facing session_id deserializes as i32.
        self.assertEqual(WriteStdinArgs.from_json(f'{{"session_id":{I32_MIN}}}').session_id, I32_MIN)
        self.assertEqual(WriteStdinArgs.from_json(f'{{"session_id":{I32_MAX}}}').session_id, I32_MAX)

        with self.assertRaisesRegex(ValueError, "session_id must fit in i32"):
            WriteStdinArgs.from_json(f'{{"session_id":{I32_MAX + 1}}}')


if __name__ == "__main__":
    unittest.main()
