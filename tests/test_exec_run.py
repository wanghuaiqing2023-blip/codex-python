import io
import tempfile
import unittest
from pathlib import Path

from pycodex.exec import (
    ExecRunError,
    PromptDecodeError,
    build_review_request,
    decode_prompt_bytes,
    load_output_schema,
    parse_exec_args,
    prepare_exec_run_plan,
    prompt_with_stdin_context,
    resolve_prompt,
    resolve_root_prompt,
    review_user_facing_hint,
)
from pycodex.protocol import ReviewRequest, ReviewTarget, UserInput


class ExecRunPreparationTests(unittest.TestCase):
    def test_decode_prompt_bytes_strips_utf8_bom(self):
        self.assertEqual(decode_prompt_bytes(b"\xef\xbb\xbfhi\n"), "hi\n")

    def test_decode_prompt_bytes_decodes_utf16_boms(self):
        self.assertEqual(decode_prompt_bytes(b"\xff\xfeh\x00i\x00\n\x00"), "hi\n")
        self.assertEqual(decode_prompt_bytes(b"\xfe\xff\x00h\x00i\x00\n"), "hi\n")

    def test_decode_prompt_bytes_rejects_invalid_utf16_lengths(self):
        with self.assertRaises(PromptDecodeError) as ctx:
            decode_prompt_bytes(b"\xff\xfeh")

        self.assertEqual(ctx.exception.kind, "invalid_utf16")
        self.assertEqual(ctx.exception.encoding, "UTF-16LE")
        self.assertEqual(
            str(ctx.exception),
            "input looked like UTF-16LE but could not be decoded. Convert it to UTF-8 and retry.",
        )

    def test_decode_prompt_bytes_rejects_utf32_boms(self):
        with self.assertRaises(PromptDecodeError) as ctx:
            decode_prompt_bytes(b"\xff\xfe\x00\x00h\x00\x00\x00")
        self.assertEqual(ctx.exception.kind, "unsupported_bom")
        self.assertEqual(ctx.exception.encoding, "UTF-32LE")

        with self.assertRaises(PromptDecodeError) as ctx:
            decode_prompt_bytes(b"\x00\x00\xfe\xff\x00\x00\x00h")
        self.assertEqual(ctx.exception.kind, "unsupported_bom")
        self.assertEqual(ctx.exception.encoding, "UTF-32BE")

    def test_decode_prompt_bytes_rejects_invalid_utf8(self):
        with self.assertRaises(PromptDecodeError) as ctx:
            decode_prompt_bytes(bytes([0xC3, 0x28]))

        self.assertEqual(ctx.exception.kind, "invalid_utf8")
        self.assertEqual(ctx.exception.valid_up_to, 0)

    def test_prompt_with_stdin_context_wraps_and_normalizes_trailing_newline(self):
        self.assertEqual(
            prompt_with_stdin_context("Summarize this concisely", "my output"),
            "Summarize this concisely\n\n<stdin>\nmy output\n</stdin>",
        )
        self.assertEqual(
            prompt_with_stdin_context("Summarize this concisely", "my output\n"),
            "Summarize this concisely\n\n<stdin>\nmy output\n</stdin>",
        )

    def test_resolve_root_prompt_appends_non_empty_piped_stdin(self):
        stderr = io.StringIO()

        prompt = resolve_root_prompt(
            "Summarize this concisely",
            stdin=b"my output\n",
            stdin_is_terminal=False,
            stderr=stderr,
        )

        self.assertEqual(prompt, "Summarize this concisely\n\n<stdin>\nmy output\n</stdin>")
        self.assertIn("Reading additional input from stdin...", stderr.getvalue())

    def test_resolve_root_prompt_ignores_empty_optional_stdin(self):
        self.assertEqual(
            resolve_root_prompt("Summarize", stdin=b"", stdin_is_terminal=False, stderr=io.StringIO()),
            "Summarize",
        )

    def test_resolve_prompt_reads_dash_or_missing_prompt_from_stdin(self):
        stderr = io.StringIO()

        self.assertEqual(
            resolve_prompt("-", stdin=b"prompt from stdin\n", stdin_is_terminal=False, stderr=stderr),
            "prompt from stdin\n",
        )
        self.assertEqual(
            resolve_prompt(None, stdin=b"prompt from stdin\n", stdin_is_terminal=False, stderr=stderr),
            "prompt from stdin\n",
        )

    def test_resolve_prompt_rejects_missing_terminal_prompt_and_empty_forced_stdin(self):
        with self.assertRaisesRegex(ExecRunError, "Either specify one as an argument"):
            resolve_prompt(None, stdin_is_terminal=True, stderr=io.StringIO())

        with self.assertRaisesRegex(ExecRunError, "No prompt provided via stdin"):
            resolve_prompt("-", stdin=b"", stdin_is_terminal=False, stderr=io.StringIO())

    def test_build_review_request_matches_upstream_targets(self):
        uncommitted = parse_exec_args(["review", "--uncommitted"]).review
        commit = parse_exec_args(["review", "--commit", "123456789", "--title", "Add review command"]).review
        custom = parse_exec_args(["review", "  custom review instructions  "]).review
        self.assertIsNotNone(uncommitted)
        self.assertIsNotNone(commit)
        self.assertIsNotNone(custom)

        self.assertEqual(build_review_request(uncommitted), ReviewRequest(ReviewTarget.uncommitted_changes()))
        self.assertEqual(
            build_review_request(commit),
            ReviewRequest(ReviewTarget.commit("123456789", "Add review command")),
        )
        self.assertEqual(
            build_review_request(custom),
            ReviewRequest(ReviewTarget.custom("custom review instructions")),
        )

    def test_build_review_request_reads_dash_prompt_from_stdin_and_trims(self):
        review = parse_exec_args(["review", "-"]).review
        self.assertIsNotNone(review)

        request = build_review_request(
            review,
            stdin=b"  review stdin instructions  \n",
            stdin_is_terminal=False,
            stderr=io.StringIO(),
        )

        self.assertEqual(request, ReviewRequest(ReviewTarget.custom("review stdin instructions")))

    def test_build_review_request_requires_target(self):
        review = parse_exec_args(["review"]).review
        self.assertIsNotNone(review)

        with self.assertRaisesRegex(ExecRunError, "Specify --uncommitted"):
            build_review_request(review)

    def test_prepare_exec_run_plan_review_ignores_output_schema_like_upstream(self):
        cli = parse_exec_args(["--output-schema", "missing-schema.json", "review", "--uncommitted"])

        plan = prepare_exec_run_plan(cli, stdin_is_terminal=True, stderr=io.StringIO())

        self.assertEqual(plan.initial_operation.kind, "review")
        self.assertEqual(plan.initial_operation.review_request, ReviewRequest(ReviewTarget.uncommitted_changes()))
        self.assertEqual(plan.prompt_summary, "current changes")

    def test_review_user_facing_hint_matches_upstream_text(self):
        self.assertEqual(review_user_facing_hint(ReviewTarget.uncommitted_changes()), "current changes")
        self.assertEqual(review_user_facing_hint(ReviewTarget.base_branch("main")), "changes against 'main'")
        self.assertEqual(review_user_facing_hint(ReviewTarget.commit("123456789", "Fix")), "commit 1234567: Fix")
        self.assertEqual(review_user_facing_hint(ReviewTarget.commit("123456789")), "commit 1234567")
        self.assertEqual(review_user_facing_hint(ReviewTarget.custom("  review this  ")), "review this")

    def test_prepare_exec_run_plan_builds_user_turn_with_images_and_schema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            schema = Path(tmpdir) / "schema.json"
            schema.write_text('{"type":"object","properties":{"ok":{"type":"boolean"}}}', encoding="utf-8")

            cli = parse_exec_args(
                [
                    "--image",
                    "root.png",
                    "--output-schema",
                    str(schema),
                    "Summarize this concisely",
                ]
            )
            plan = prepare_exec_run_plan(cli, stdin=b"my output\n", stdin_is_terminal=False, stderr=io.StringIO())

        self.assertEqual(plan.initial_operation.kind, "user_turn")
        self.assertEqual(
            plan.initial_operation.items,
            (
                UserInput.local_image(Path("root.png")),
                UserInput.text_input("Summarize this concisely\n\n<stdin>\nmy output\n</stdin>"),
            ),
        )
        self.assertEqual(plan.initial_operation.output_schema["properties"]["ok"]["type"], "boolean")
        self.assertEqual(plan.prompt_summary, "Summarize this concisely\n\n<stdin>\nmy output\n</stdin>")

    def test_prepare_exec_run_plan_preserves_full_output_schema_like_upstream_request(self):
        schema_contents = {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            schema = Path(tmpdir) / "schema.json"
            schema.write_text(
                '{"type":"object","properties":{"answer":{"type":"string"}},"required":["answer"],"additionalProperties":false}',
                encoding="utf-8",
            )
            cli = parse_exec_args(["--output-schema", str(schema), "tell me a joke"])

            plan = prepare_exec_run_plan(cli, stdin_is_terminal=True, stderr=io.StringIO())

        self.assertEqual(plan.initial_operation.kind, "user_turn")
        self.assertEqual(plan.initial_operation.output_schema, schema_contents)
        self.assertEqual(plan.initial_operation.items, (UserInput.text_input("tell me a joke"),))
        self.assertEqual(plan.prompt_summary, "tell me a joke")

    def test_load_output_schema_reports_invalid_utf8_as_read_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            schema = Path(tmpdir) / "schema.json"
            schema.write_bytes(b"\xff")

            with self.assertRaisesRegex(ExecRunError, "Failed to read output schema file"):
                load_output_schema(schema)

    def test_load_output_schema_reports_invalid_json_like_upstream(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            schema = Path(tmpdir) / "schema.json"
            schema.write_text("{not json", encoding="utf-8")

            with self.assertRaisesRegex(ExecRunError, "Output schema file .* is not valid JSON"):
                load_output_schema(schema)

    def test_prepare_exec_run_plan_resume_uses_last_session_as_prompt_and_merges_images(self):
        cli = parse_exec_args(["--image", "root.png", "resume", "--last", "--image", "resume.png", "continue"])

        plan = prepare_exec_run_plan(cli, stdin_is_terminal=True, stderr=io.StringIO())

        self.assertEqual(
            plan.initial_operation.items,
            (
                UserInput.local_image(Path("root.png")),
                UserInput.local_image(Path("resume.png")),
                UserInput.text_input("continue"),
            ),
        )
        self.assertEqual(plan.prompt_summary, "continue")

    def test_prepare_exec_run_plan_resume_loads_output_schema_like_upstream(self):
        schema_contents = {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            schema = Path(tmpdir) / "schema.json"
            schema.write_text(
                '{"type":"object","properties":{"answer":{"type":"string"}},"required":["answer"],"additionalProperties":false}',
                encoding="utf-8",
            )
            cli = parse_exec_args(["resume", "session-123", "--output-schema", str(schema), "continue"])

            plan = prepare_exec_run_plan(cli, stdin_is_terminal=True, stderr=io.StringIO())

        self.assertEqual(plan.initial_operation.kind, "user_turn")
        self.assertEqual(plan.initial_operation.output_schema, schema_contents)
        self.assertEqual(plan.prompt_summary, "continue")

    def test_prepare_exec_run_plan_resume_last_single_positional_becomes_prompt(self):
        cli = parse_exec_args(["resume", "--last", "session-123"])

        plan = prepare_exec_run_plan(cli, stdin_is_terminal=True, stderr=io.StringIO())

        self.assertIsNotNone(cli.resume)
        self.assertIsNone(cli.resume.session_id)
        self.assertEqual(cli.resume.prompt, "session-123")
        self.assertEqual(plan.initial_operation.items, (UserInput.text_input("session-123"),))
        self.assertEqual(plan.prompt_summary, "session-123")

    def test_prepare_exec_run_plan_review_uses_review_request_and_hint(self):
        cli = parse_exec_args(["review", "--commit", "123456789", "--title", "Fix"])

        plan = prepare_exec_run_plan(cli, stdin_is_terminal=True, stderr=io.StringIO())

        self.assertEqual(plan.initial_operation.kind, "review")
        self.assertEqual(plan.initial_operation.review_request, ReviewRequest(ReviewTarget.commit("123456789", "Fix")))
        self.assertEqual(plan.prompt_summary, "commit 1234567: Fix")


if __name__ == "__main__":
    unittest.main()
