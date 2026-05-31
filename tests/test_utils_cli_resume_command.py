import unittest

from pycodex.utils_cli import resume_command, resume_hint


THREAD_ID = "123e4567-e89b-12d3-a456-426614174000"


class ResumeCommandTests(unittest.TestCase):
    def test_prefers_name_over_id(self) -> None:
        self.assertEqual(resume_command("my-thread", THREAD_ID), "codex resume my-thread")

    def test_formats_thread_id_when_name_is_missing(self) -> None:
        self.assertEqual(resume_command(None, THREAD_ID), f"codex resume {THREAD_ID}")

    def test_returns_none_without_a_resume_target(self) -> None:
        self.assertIsNone(resume_command(None, None))

    def test_quotes_thread_names_when_needed(self) -> None:
        self.assertEqual(resume_command("-starts-with-dash", None), "codex resume -- -starts-with-dash")
        self.assertEqual(resume_command("two words", None), "codex resume 'two words'")
        self.assertEqual(resume_command("quote'case", None), 'codex resume "quote\'case"')

    def test_resume_hint_names_picker_item_with_id(self) -> None:
        self.assertEqual(
            resume_hint("my-thread", THREAD_ID),
            f"codex resume, then select my-thread ({THREAD_ID})",
        )

    def test_resume_hint_uses_direct_id_command_without_name(self) -> None:
        self.assertEqual(resume_hint(None, THREAD_ID), f"codex resume {THREAD_ID}")

    def test_resume_hint_requires_thread_id(self) -> None:
        self.assertIsNone(resume_hint("my-thread", None))


if __name__ == "__main__":
    unittest.main()
