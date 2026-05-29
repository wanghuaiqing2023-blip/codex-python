import json
import unittest

from pycodex.core.client import ModelClient
from pycodex.core.http_transport import run_user_turn_http_sampling_from_session
from pycodex.core.session_runtime import InMemoryCodexSession
from pycodex.protocol import ContentItem, ResponseItem, UserInput


class FakeResponse:
    def read(self) -> bytes:
        return json.dumps(
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ]
            }
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class Router:
    def model_visible_specs(self) -> list[dict[str, str]]:
        return []


class SessionRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_in_memory_session_runs_user_turn_http_sampling(self) -> None:
        seen = {}

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            user_instructions="project instructions",
            base_instructions="base",
            history=[ResponseItem.message("developer", (ContentItem.input_text("context"),))],
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = {"base_url": "https://api.example.test/v1"}

        result = await run_user_turn_http_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(session.context_updates_recorded, 1)
        self.assertEqual(len(session.recorded_batches), 2)
        self.assertEqual(session.history[-1], result.response_items[0])
        self.assertEqual(session.history[-1].content[0].text, "done")
        self.assertEqual(seen["body"]["instructions"], "base")
        self.assertEqual(seen["body"]["input"][0]["role"], "developer")
        self.assertIn("project instructions", seen["body"]["input"][1]["content"][0]["text"])
        self.assertEqual(seen["body"]["input"][2]["content"][0]["text"], "hello")


if __name__ == "__main__":
    unittest.main()
