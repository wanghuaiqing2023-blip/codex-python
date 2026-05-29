import unittest
from types import SimpleNamespace

from pycodex.core.client_common import Prompt
from pycodex.core.prompt_debug import (
    PromptDebugThread,
    build_prompt_input,
    build_prompt_input_from_session,
    mark_config_ephemeral,
)
from pycodex.protocol import BaseInstructions, ContentItem, ResponseItem, UserInput


class History:
    def __init__(self, items: list[ResponseItem]) -> None:
        self.items = items

    def for_prompt(self, _modalities: object) -> list[ResponseItem]:
        return list(self.items)


class Router:
    def model_visible_specs(self) -> list[dict[str, str]]:
        return [{"name": "tool"}]


class Session:
    def __init__(self) -> None:
        self.turn_context = SimpleNamespace(model_info=SimpleNamespace(input_modalities=("text",)))
        self.history = [ResponseItem.message("developer", (ContentItem.input_text("context"),))]
        self.recorded: list[tuple[ResponseItem, ...]] = []
        self.context_recorded = False

    async def new_default_turn(self) -> object:
        return self.turn_context

    async def record_context_updates_and_set_reference_context_item(self, turn_context: object) -> None:
        self.context_recorded = turn_context is self.turn_context

    async def record_conversation_items(self, _turn_context: object, items: tuple[ResponseItem, ...]) -> None:
        self.recorded.append(items)
        self.history.extend(items)

    async def clone_history(self) -> History:
        return History(self.history)

    async def get_base_instructions(self) -> BaseInstructions:
        return BaseInstructions("base")


class PromptDebugTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_prompt_input_from_session_records_user_input_and_formats_prompt(self) -> None:
        session = Session()

        output = await build_prompt_input_from_session(
            session,
            (UserInput.text_input("hello"),),
            built_tools=lambda _sess, _turn: Router(),
            build_prompt=lambda prompt_input, router, _turn, base: Prompt(
                input=prompt_input,
                tools=router.model_visible_specs(),
                base_instructions=base,
            ),
        )

        self.assertTrue(session.context_recorded)
        self.assertEqual(len(session.recorded), 1)
        self.assertEqual(output[-1].role, "user")
        self.assertEqual(output[-1].content[0].text, "hello")

    async def test_build_prompt_input_from_session_injects_user_instructions_before_user_input(self) -> None:
        session = Session()
        session.turn_context.user_instructions = "project instructions"
        session.turn_context.cwd = "C:/work/project"

        output = await build_prompt_input_from_session(session, (UserInput.text_input("hello"),))

        self.assertEqual(output[-2].role, "user")
        self.assertIn("# AGENTS.md instructions for C:/work/project", output[-2].content[0].text)
        self.assertIn("<INSTRUCTIONS>\nproject instructions", output[-2].content[0].text)
        self.assertEqual(output[-1].content[0].text, "hello")

    async def test_build_prompt_input_skips_empty_user_input_recording(self) -> None:
        session = Session()

        output = await build_prompt_input_from_session(session, ())

        self.assertEqual(session.recorded, [])
        self.assertEqual(output, session.history)

    async def test_build_prompt_input_marks_config_ephemeral_and_shuts_down_thread(self) -> None:
        session = Session()
        state = {"shutdown": False, "removed": None}

        async def shutdown() -> None:
            state["shutdown"] = True

        async def remove(thread_id: str | None) -> None:
            state["removed"] = thread_id

        async def factory(config: object, state_db: object | None) -> PromptDebugThread:
            self.assertIsNone(state_db)
            return PromptDebugThread(session=session, thread_id="thread-1", shutdown=shutdown, remove=remove)

        config: dict[str, object] = {}
        output = await build_prompt_input(config, (), session_factory=factory)

        self.assertTrue(config["ephemeral"])
        self.assertEqual(output, session.history)
        self.assertTrue(state["shutdown"])
        self.assertEqual(state["removed"], "thread-1")

    async def test_build_prompt_input_requires_factory(self) -> None:
        with self.assertRaises(RuntimeError):
            await build_prompt_input({}, ())

    def test_mark_config_ephemeral_supports_objects(self) -> None:
        config = SimpleNamespace()

        mark_config_ephemeral(config)

        self.assertTrue(config.ephemeral)


if __name__ == "__main__":
    unittest.main()
