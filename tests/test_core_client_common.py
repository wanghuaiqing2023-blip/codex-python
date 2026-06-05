import asyncio
import unittest
from pathlib import Path

from pycodex.core.client_common import (
    REVIEW_EXIT_INTERRUPTED_TMPL,
    REVIEW_EXIT_SUCCESS_TMPL,
    REVIEW_PROMPT,
    Prompt,
    ResponseStream,
)
from pycodex.core.tools.network_approval import CancellationToken
from pycodex.protocol import BaseInstructions, ContentItem, Personality, ResponseItem


class ClientCommonTests(unittest.IsolatedAsyncioTestCase):
    def test_review_constants_match_rust_include_files(self) -> None:
        root = Path(__file__).resolve().parents[1] / "codex" / "codex-rs" / "core"

        self.assertEqual(REVIEW_PROMPT, (root / "review_prompt.md").read_text(encoding="utf-8"))
        self.assertEqual(
            REVIEW_EXIT_SUCCESS_TMPL,
            (root / "templates/review/exit_success.xml").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            REVIEW_EXIT_INTERRUPTED_TMPL,
            (root / "templates/review/exit_interrupted.xml").read_text(encoding="utf-8"),
        )

    def test_prompt_default_matches_rust_default(self) -> None:
        prompt = Prompt.default()

        self.assertEqual(prompt.input, [])
        self.assertEqual(prompt.tools, [])
        self.assertFalse(prompt.parallel_tool_calls)
        self.assertEqual(prompt.base_instructions, BaseInstructions.default())
        self.assertIsNone(prompt.personality)
        self.assertIsNone(prompt.output_schema)
        self.assertTrue(prompt.output_schema_strict)

    def test_prompt_get_formatted_input_returns_clone(self) -> None:
        item = ResponseItem.message("user", [ContentItem.input_text("hello")])
        prompt = Prompt(input=[item])

        formatted = prompt.get_formatted_input()
        formatted.append(ResponseItem.other())

        self.assertEqual(prompt.input, [item])
        self.assertEqual(formatted[0], item)

    def test_prompt_validates_rust_shaped_fields(self) -> None:
        with self.assertRaisesRegex(TypeError, "input must be a list of ResponseItem"):
            Prompt(input=["bad"])  # type: ignore[list-item]
        with self.assertRaisesRegex(TypeError, "parallel_tool_calls must be a bool"):
            Prompt(parallel_tool_calls=1)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "base_instructions must be BaseInstructions"):
            Prompt(base_instructions="base")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "personality must be Personality or None"):
            Prompt(personality="friendly")  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "output_schema_strict must be a bool"):
            Prompt(output_schema_strict=1)  # type: ignore[arg-type]

        prompt = Prompt(personality=Personality.FRIENDLY)
        self.assertIs(prompt.personality, Personality.FRIENDLY)

    async def test_response_stream_yields_queue_items_until_terminal_none(self) -> None:
        queue = asyncio.Queue()
        token = CancellationToken()
        stream = ResponseStream(queue, token)
        await queue.put("first")
        await queue.put(None)

        self.assertEqual(await stream.next(), "first")
        self.assertIsNone(await stream.next())
        self.assertTrue(token.is_cancelled())

    async def test_response_stream_async_iterator(self) -> None:
        queue = asyncio.Queue()
        token = CancellationToken()
        stream = ResponseStream(queue, token)
        await queue.put("first")
        await queue.put("second")
        await queue.put(None)

        seen = []
        async for item in stream:
            seen.append(item)

        self.assertEqual(seen, ["first", "second"])
        self.assertTrue(token.is_cancelled())

    async def test_response_stream_close_cancels_consumer_dropped_token(self) -> None:
        token = CancellationToken()
        stream = ResponseStream(consumer_dropped=token)

        self.assertFalse(token.is_cancelled())
        stream.close()
        stream.close()
        self.assertTrue(token.is_cancelled())


if __name__ == "__main__":
    unittest.main()
