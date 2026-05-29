import json
import unittest

from pycodex.core.http_transport import (
    HttpTransportConfig,
    http_transport_config_from_provider,
    model_client_http_sampler,
    response_items_from_responses_payload,
    run_user_turn_http_sampling_from_session,
    send_prepared_http_sampling_request,
)
from pycodex.core.client import ModelClient
from pycodex.core.turn_sampler import PreparedSamplingRequest
from pycodex.core.turn_runtime import UserTurnSamplingRequest, run_user_turn_sampling_from_session
from pycodex.protocol import BaseInstructions, ContentItem, ResponseItem, UserInput


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        return None


class History:
    def __init__(self, items: list[ResponseItem]) -> None:
        self.items = items

    def for_prompt(self, _modalities: object) -> list[ResponseItem]:
        return list(self.items)


class Router:
    def model_visible_specs(self) -> list[dict[str, str]]:
        return []


class Session:
    def __init__(self) -> None:
        self.turn_context = type("TurnContext", (), {"model_info": None, "user_instructions": None, "cwd": "C:/work"})()
        self.history: list[ResponseItem] = []
        self.recorded: list[tuple[ResponseItem, ...]] = []

    async def new_default_turn(self):
        return self.turn_context

    async def record_context_updates_and_set_reference_context_item(self, _turn_context) -> None:
        return None

    async def record_conversation_items(self, _turn_context, items: tuple[ResponseItem, ...]) -> None:
        self.recorded.append(items)
        self.history.extend(items)

    async def clone_history(self) -> History:
        return History(self.history)

    async def get_base_instructions(self) -> BaseInstructions:
        return BaseInstructions("base")


class HttpTransportTests(unittest.TestCase):
    def test_response_items_from_responses_payload_reads_output_items(self) -> None:
        items = response_items_from_responses_payload(
            {"output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "done"}]}]}
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].role, "assistant")
        self.assertEqual(items[0].content[0].text, "done")

    def test_send_prepared_http_sampling_request_posts_json_and_returns_items(self) -> None:
        seen = {}

        def opener(request):
            seen["url"] = request.full_url
            seen["method"] = request.get_method()
            seen["body"] = json.loads(request.data.decode("utf-8"))
            seen["content_type"] = request.headers["Content-type"]
            seen["authorization"] = request.headers["Authorization"]
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "done"}],
                        }
                    ]
                }
            )

        prepared = PreparedSamplingRequest(
            sampling_request=UserTurnSamplingRequest(session=None, turn_context=None, request_plan=None),
            prepared_request={"model": "gpt-test", "input": []},
        )

        result = send_prepared_http_sampling_request(
            prepared,
            HttpTransportConfig("https://api.example.test/responses", headers={"Authorization": "Bearer test"}),
            opener=opener,
        )

        self.assertEqual(seen["url"], "https://api.example.test/responses")
        self.assertEqual(seen["method"], "POST")
        self.assertEqual(seen["body"], {"model": "gpt-test", "input": []})
        self.assertEqual(seen["content_type"], "application/json")
        self.assertEqual(seen["authorization"], "Bearer test")
        self.assertEqual(result.response_items[0].content[0].text, "done")

    def test_http_transport_config_from_provider_combines_endpoint_auth_and_client_headers(self) -> None:
        client = ModelClient(
            session_id="session",
            thread_id="thread",
            installation_id="install",
            beta_features_header="feature-a",
            include_timing_metrics=True,
        )
        provider = {"base_url": "https://api.example.test/v1"}

        config = http_transport_config_from_provider(
            client,
            provider,
            auth={"api_key": "sk-test"},
            turn_metadata_header="turn-meta",
        )

        self.assertEqual(config.endpoint, "https://api.example.test/v1/responses")
        self.assertEqual(config.headers["Authorization"], "Bearer sk-test")
        self.assertEqual(config.headers["x-codex-beta-features"], "feature-a")
        self.assertEqual(config.headers["x-codex-turn-metadata"], "turn-meta")
        self.assertEqual(config.headers["x-codex-window-id"], "thread:0")
        self.assertEqual(config.headers["x-responsesapi-include-timing-metrics"], "true")

    def test_model_client_http_sampler_can_run_user_turn_runtime(self) -> None:
        seen = {}

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "done"}],
                        }
                    ]
                }
            )

        async def run():
            client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
            session = Session()
            sampler = model_client_http_sampler(
                client.new_session(),
                HttpTransportConfig("https://api.example.test/responses"),
                opener=opener,
            )
            provider = type("Provider", (), {"is_azure_responses_endpoint": lambda _self: False})()
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
            return await run_user_turn_sampling_from_session(
                session,
                (UserInput.text_input("hello"),),
                client,
                provider,
                model_info,
                sampler,
                built_tools=lambda _sess, _turn: Router(),
            )

        import asyncio

        result = asyncio.run(run())

        self.assertEqual(seen["body"]["model"], "gpt-test")
        self.assertEqual(seen["body"]["instructions"], "base")
        self.assertEqual(result.response_items[0].content[0].text, "done")

    def test_run_user_turn_http_sampling_from_session_wraps_full_http_path(self) -> None:
        seen = {}

        def opener(request):
            seen["url"] = request.full_url
            seen["authorization"] = request.headers["Authorization"]
            seen["window"] = request.headers["X-codex-window-id"]
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "done"}],
                        }
                    ]
                }
            )

        async def run():
            client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
            session = Session()
            provider = {
                "base_url": "https://api.example.test/v1",
                "is_azure_responses_endpoint": lambda: False,
            }
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
            return await run_user_turn_http_sampling_from_session(
                session,
                (UserInput.text_input("hello"),),
                client,
                provider,
                model_info,
                auth="sk-test",
                opener=opener,
                built_tools=lambda _sess, _turn: Router(),
            )

        import asyncio

        result = asyncio.run(run())

        self.assertEqual(seen["url"], "https://api.example.test/v1/responses")
        self.assertEqual(seen["authorization"], "Bearer sk-test")
        self.assertEqual(seen["window"], "thread:0")
        self.assertEqual(seen["body"]["model"], "gpt-test")
        self.assertEqual(result.response_items[0].content[0].text, "done")


if __name__ == "__main__":
    unittest.main()
