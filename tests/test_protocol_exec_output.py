import unittest
from datetime import timedelta

from pycodex.protocol import ExecToolCallOutput, StreamOutput, bytes_to_string_smart


CYRILLIC_EXAMPLE = "\u043f\u0440\u0438\u043c\u0435\u0440"


class ProtocolExecOutputTests(unittest.TestCase):
    def test_utf8_shell_output(self):
        self.assertEqual(bytes_to_string_smart(CYRILLIC_EXAMPLE.encode("utf-8")), CYRILLIC_EXAMPLE)

    def test_cp1251_shell_output(self):
        self.assertEqual(bytes_to_string_smart(b"\xEF\xF0\xE8\xEC\xE5\xF0"), CYRILLIC_EXAMPLE)

    def test_cp866_shell_output(self):
        self.assertEqual(bytes_to_string_smart(b"\xAF\xE0\xA8\xAC\xA5\xE0"), CYRILLIC_EXAMPLE)

    def test_windows_1252_smart_decoding(self):
        self.assertEqual(bytes_to_string_smart(b"\x93\x94 test \x96 dash"), "\u201c\u201d test \u2013 dash")

    def test_smart_decoding_improves_over_lossy_utf8(self):
        data = b"\x93\x94 test \x96 dash"

        self.assertIn("\ufffd", data.decode("utf-8", errors="replace"))
        self.assertEqual(bytes_to_string_smart(data), "\u201c\u201d test \u2013 dash")

    def test_mixed_ascii_and_legacy_encoding(self):
        self.assertEqual(bytes_to_string_smart(b"Output: caf\xE9"), "Output: caf\u00e9")

    def test_pure_latin1_shell_output(self):
        self.assertEqual(bytes_to_string_smart(b"caf\xE9"), "caf\u00e9")

    def test_invalid_bytes_still_fall_back_to_lossy(self):
        self.assertEqual(bytes_to_string_smart(b"\xFF\xFE\xFD"), b"\xFF\xFE\xFD".decode("utf-8", errors="replace"))

    def test_stream_output_preserves_truncation_metadata_when_decoding(self):
        output = StreamOutput(b"\x93test\x94", truncated_after_lines=3).from_utf8_lossy()

        self.assertEqual(output.text, "\u201ctest\u201d")
        self.assertEqual(output.truncated_after_lines, 3)

    def test_stream_output_rejects_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "text must be a string or bytes"):
            StreamOutput(123)

        with self.assertRaisesRegex(TypeError, "text must be a string"):
            StreamOutput.new(b"bytes")

        with self.assertRaisesRegex(TypeError, "truncated_after_lines must be an int or None"):
            StreamOutput("text", truncated_after_lines=True)

        with self.assertRaisesRegex(ValueError, "truncated_after_lines must fit in u32"):
            StreamOutput("text", truncated_after_lines=-1)

        with self.assertRaisesRegex(ValueError, "truncated_after_lines must fit in u32"):
            StreamOutput("text", truncated_after_lines=2**32)

    def test_exec_tool_call_output_defaults_match_upstream_shape(self):
        output = ExecToolCallOutput()

        self.assertEqual(output.exit_code, 0)
        self.assertEqual(output.stdout, StreamOutput.new(""))
        self.assertEqual(output.stderr, StreamOutput.new(""))
        self.assertEqual(output.aggregated_output, StreamOutput.new(""))
        self.assertEqual(output.duration, timedelta(0))
        self.assertFalse(output.timed_out)

    def test_exec_tool_call_output_rejects_non_rust_shapes(self):
        with self.assertRaisesRegex(TypeError, "exit_code must be an int"):
            ExecToolCallOutput(exit_code=True)

        with self.assertRaisesRegex(ValueError, "exit_code must fit in i32"):
            ExecToolCallOutput(exit_code=2**31)

        with self.assertRaisesRegex(TypeError, "stdout must be a StreamOutput"):
            ExecToolCallOutput(stdout="stdout")

        with self.assertRaisesRegex(TypeError, "stdout.text must be a string"):
            ExecToolCallOutput(stdout=StreamOutput(b"bytes"))

        with self.assertRaisesRegex(TypeError, "duration must be a timedelta"):
            ExecToolCallOutput(duration=0)

        with self.assertRaisesRegex(TypeError, "timed_out must be a bool"):
            ExecToolCallOutput(timed_out=1)

    def test_bytes_to_string_smart_rejects_non_bytes(self):
        with self.assertRaisesRegex(TypeError, "data must be bytes"):
            bytes_to_string_smart("text")


if __name__ == "__main__":
    unittest.main()
