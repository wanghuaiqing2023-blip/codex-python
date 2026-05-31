import unittest
from types import SimpleNamespace

from pycodex.core.client import ModelClient
from pycodex.core.codex_thread import SETTINGS_UNSET, SessionSettingsUpdate
from pycodex.core.features import Feature
from pycodex.core.turn_sampler import sample_with_model_client_session
from pycodex.core.turn_runtime import (
    build_user_input_op_responses_request_from_session,
    build_user_turn_responses_request_from_session,
    run_user_input_op_sampling_from_session,
    run_user_turn_sampling_from_session,
)
from pycodex.core.tool_context import FunctionToolOutput
from pycodex.core.tool_registry import ToolRegistry
from pycodex.core.tool_router import ToolRouter
from pycodex.protocol import (
    ApplyPatchToolType,
    BaseInstructions,
    ContentItem,
    Op,
    ReasoningEffort,
    ResponseItem,
    ThreadSettingsOverrides,
    TurnEnvironmentSelection,
    UserInput,
    ToolName,
)


class History:
    def __init__(self, items: list[ResponseItem]) -> None:
        self.items = items

    def for_prompt(self, _modalities: object) -> list[ResponseItem]:
        return list(self.items)


class Router:
    def model_visible_specs(self) -> list[dict[str, str]]:
        return [{"type": "function", "name": "tool"}]


class EchoHandler:
    def __init__(self) -> None:
        self.invocations = []

    def tool_name(self) -> ToolName:
        return ToolName.plain("echo")

    def handle(self, invocation):
        self.invocations.append(invocation)
        return FunctionToolOutput.from_text("tool ok", True)


class FeatureSet:
    def __init__(self, *features) -> None:
        self.features = set(features)

    def enabled(self, feature) -> bool:
        if not isinstance(feature, Feature):
            raise TypeError("feature must be Feature")
        return feature in self.features


class TurnMetadataState:
    def __init__(self) -> None:
        self.responsesapi_client_metadata = None

    def set_responsesapi_client_metadata(self, value) -> None:
        self.responsesapi_client_metadata = dict(value)


class Session:
    def __init__(self) -> None:
        self.turn_metadata_state = TurnMetadataState()
        self.turn_context = SimpleNamespace(
            model_info=None,
            user_instructions="project instructions",
            cwd="C:/work/project",
            turn_metadata_state=self.turn_metadata_state,
        )
        self.history = [ResponseItem.message("developer", (ContentItem.input_text("context"),))]
        self.recorded: list[tuple[ResponseItem, ...]] = []
        self.context_recorded = False
        self.applied_thread_settings = None
        self.environments = None
        self._pending_environments = None
        self.final_output_json_schema = None

    async def new_default_turn(self) -> object:
        environments = self.environments
        if self._pending_environments is not None:
            environments = self._pending_environments
            self._pending_environments = None
        self.turn_context.environments = environments
        self.turn_context.final_output_json_schema = self.final_output_json_schema
        return self.turn_context

    async def update_settings(self, updates: SessionSettingsUpdate) -> None:
        if updates.environments is not None:
            self._pending_environments = tuple(updates.environments)
        if updates.final_output_json_schema is not SETTINGS_UNSET:
            self.final_output_json_schema = updates.final_output_json_schema

    async def apply_thread_settings_overrides(self, thread_settings: ThreadSettingsOverrides) -> None:
        self.applied_thread_settings = thread_settings
        self.turn_context.model_info = SimpleNamespace(
            slug=thread_settings.model or "gpt-test",
            input_modalities=("text",),
            supports_reasoning_summaries=True,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        self.turn_context.config = SimpleNamespace(
            model_reasoning_effort=thread_settings.effort,
            model_reasoning_summary=None,
            service_tier=thread_settings.service_tier,
        )

    async def record_context_updates_and_set_reference_context_item(self, turn_context: object) -> None:
        self.context_recorded = turn_context is self.turn_context

    async def record_conversation_items(self, _turn_context: object, items: tuple[ResponseItem, ...]) -> None:
        self.recorded.append(items)
        self.history.extend(items)

    async def clone_history(self) -> History:
        return History(self.history)

    async def get_base_instructions(self) -> BaseInstructions:
        return BaseInstructions("base")


class TurnRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_user_turn_responses_request_records_turn_and_builds_request(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        plan = await build_user_turn_responses_request_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
            service_tier="auto",
        )

        self.assertTrue(session.context_recorded)
        self.assertEqual(len(session.recorded), 1)
        self.assertEqual(plan.request["model"], "gpt-test")
        self.assertEqual(plan.request["instructions"], "base")
        self.assertEqual(plan.request["tools"], [{"type": "function", "name": "tool"}])
        self.assertEqual(plan.request["service_tier"], "auto")
        self.assertEqual(plan.request["input"][0].role, "developer")
        self.assertIn("project instructions", plan.request["input"][1].content[0].text)
        self.assertEqual(plan.request["input"][2].content[0].text, "hello")

    async def test_build_user_turn_request_uses_turn_config_reasoning_and_service_tier_defaults(self) -> None:
        session = Session()
        session.turn_context.config = SimpleNamespace(
            model_reasoning_effort="high",
            model_reasoning_summary="concise",
            service_tier="priority",
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=True,
            support_verbosity=False,
            default_reasoning_level="medium",
            service_tier_for_request=lambda tier: tier,
        )

        plan = await build_user_turn_responses_request_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(plan.request["reasoning"], {"effort": "high", "summary": "concise"})
        self.assertEqual(plan.request["service_tier"], "priority")

    async def test_build_user_turn_request_applies_thread_settings_before_turn_creation(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-stale",
            supports_reasoning_summaries=True,
            support_verbosity=False,
            default_reasoning_level="medium",
            service_tier_for_request=lambda tier: tier,
        )
        thread_settings = ThreadSettingsOverrides(
            model="gpt-thread",
            effort=ReasoningEffort.HIGH,
            service_tier="priority",
        )

        plan = await build_user_turn_responses_request_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
            thread_settings=thread_settings,
        )

        self.assertIs(session.applied_thread_settings, thread_settings)
        self.assertEqual(plan.request["model"], "gpt-thread")
        self.assertEqual(plan.request["reasoning"], {"effort": ReasoningEffort.HIGH, "summary": None})
        self.assertEqual(plan.request["service_tier"], "priority")

    async def test_build_user_input_op_request_applies_op_thread_settings(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-stale",
            supports_reasoning_summaries=True,
            support_verbosity=False,
            default_reasoning_level="medium",
            service_tier_for_request=lambda tier: tier,
        )
        thread_settings = ThreadSettingsOverrides(
            model="gpt-op",
            effort=ReasoningEffort.HIGH,
            service_tier="priority",
        )
        op = Op.user_input(
            (UserInput.text_input("hello"),),
            final_output_json_schema={"type": "object"},
            thread_settings=thread_settings,
        )

        plan = await build_user_input_op_responses_request_from_session(
            session,
            op,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertIs(session.applied_thread_settings, thread_settings)
        self.assertEqual(plan.request["model"], "gpt-op")
        self.assertEqual(plan.request["service_tier"], "priority")
        self.assertEqual(session.turn_context.final_output_json_schema, {"type": "object"})
        self.assertEqual(plan.request["text"]["format"]["schema"], {"type": "object"})

    async def test_build_user_input_op_request_clears_previous_final_output_json_schema(self) -> None:
        session = Session()
        session.final_output_json_schema = {"type": "object"}
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        plan = await build_user_input_op_responses_request_from_session(
            session,
            Op.user_input((UserInput.text_input("hello"),)),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertIsNone(session.final_output_json_schema)
        self.assertIsNone(session.turn_context.final_output_json_schema)
        self.assertIsNone(plan.request["text"])

    async def test_build_user_input_op_request_records_responsesapi_client_metadata(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        await build_user_input_op_responses_request_from_session(
            session,
            Op.user_input(
                (UserInput.text_input("hello"),),
                responsesapi_client_metadata={"fiber_run_id": "fiber-123"},
            ),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(
            session.turn_metadata_state.responsesapi_client_metadata,
            {"fiber_run_id": "fiber-123"},
        )

    async def test_build_user_input_op_request_records_additional_context_before_user_input(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        plan = await build_user_input_op_responses_request_from_session(
            session,
            Op.user_input(
                (UserInput.text_input("hello"),),
                additional_context={
                    "z_app": {"kind": "application", "value": "trusted context"},
                    "a_note": {"kind": "untrusted", "value": "untrusted context"},
                },
            ),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(session.recorded[0][0].role, "user")
        self.assertEqual(session.recorded[0][0].content[0].text, "<external_a_note>untrusted context</external_a_note>")
        self.assertEqual(session.recorded[0][1].role, "developer")
        self.assertEqual(session.recorded[0][1].content[0].text, "<z_app>trusted context</z_app>")
        self.assertEqual(session.recorded[1][0].content[0].text, "hello")
        self.assertIn("<external_a_note>untrusted context</external_a_note>", plan.request["input"][1].content[0].text)

    async def test_build_user_input_op_request_truncates_large_additional_context_values(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        max_expected_context_text_bytes = 5 * 1024
        long_browser_value = f"browser-head-{'x' * 40_000}-browser-tail"
        long_app_value = f"app-head-{'y' * 40_000}-app-tail"

        plan = await build_user_input_op_responses_request_from_session(
            session,
            Op.user_input(
                (UserInput.text_input("hello"),),
                additional_context={
                    "browser_info": {"kind": "untrusted", "value": long_browser_value},
                    "app": {"kind": "application", "value": long_app_value},
                },
            ),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        developer_text = session.recorded[0][0].content[0].text
        user_text = session.recorded[0][1].content[0].text
        user_request_input = plan.request["input"]

        self.assertIn("tokens truncated", developer_text)
        self.assertIn("tokens truncated", user_text)
        self.assertLess(len(developer_text), len(long_app_value) + len("<app></app>"))
        self.assertLess(len(user_text), len(long_browser_value) + len("<external_browser_info></external_browser_info>"))
        self.assertIn("<app>", developer_text)
        self.assertIn("</app>", developer_text)
        self.assertIn("<external_browser_info>", user_text)
        self.assertIn("</external_browser_info>", user_text)
        request_app_text = None
        request_browser_text = None
        for item in user_request_input:
            text = item.content[0].text
            if "tokens truncated" in text and "<app>" in text:
                request_app_text = text
            if "tokens truncated" in text and "<external_browser_info>" in text:
                request_browser_text = text
        self.assertIsNotNone(request_app_text)
        self.assertIsNotNone(request_browser_text)
        self.assertIn("<app>", request_app_text)
        self.assertIn("</app>", request_app_text)
        self.assertIn("tokens truncated", request_app_text)
        self.assertIn("<external_browser_info>", request_browser_text)
        self.assertIn("</external_browser_info>", request_browser_text)
        self.assertIn("tokens truncated", request_browser_text)
        self.assertLessEqual(len(request_app_text), max_expected_context_text_bytes)
        self.assertLessEqual(len(request_browser_text), max_expected_context_text_bytes)
        self.assertIn(f"<app>app-head-{\"y\" * 1024}", request_app_text)
        self.assertIn(f"<external_browser_info>browser-head-{\"x\" * 1024}", request_browser_text)
        self.assertTrue(request_app_text.endswith("app-tail</app>"))
        self.assertTrue(request_browser_text.endswith("browser-tail</external_browser_info>"))
        self.assertTrue(
            any(item.role == "user" and item.content[0].text == "hello" for item in user_request_input),
            "user input should still appear in request input sequence",
        )

    async def test_build_user_input_op_request_rejects_unknown_additional_context_kind(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        with self.assertRaises(ValueError):
            await build_user_input_op_responses_request_from_session(
                session,
                Op.user_input(
                    (UserInput.text_input("hello"),),
                    additional_context={"app": {"kind": "internal", "value": "bad"}},
                ),
                client,
                provider,
                model_info,
                built_tools=lambda _sess, _turn: Router(),
            )

    async def test_build_user_input_op_request_rejects_non_string_additional_context_value(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        with self.assertRaises(TypeError):
            await build_user_input_op_responses_request_from_session(
                session,
                Op.user_input(
                    (UserInput.text_input("hello"),),
                    additional_context={"app": {"kind": "application", "value": 123}},
                ),
                client,
                provider,
                model_info,
                built_tools=lambda _sess, _turn: Router(),
            )

    async def test_build_user_input_op_request_applies_turn_environments_before_turn_creation(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        environments = (TurnEnvironmentSelection("env-1", "C:/work/project"),)

        await build_user_input_op_responses_request_from_session(
            session,
            Op.user_input((UserInput.text_input("hello"),), environments=environments),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertIsNone(session.environments)
        self.assertEqual(session.turn_context.environments, environments)

    async def test_build_user_turn_request_uses_default_environment_tool_router(self) -> None:
        session = Session()
        session.environments = (
            TurnEnvironmentSelection("local", "C:/work/project"),
            TurnEnvironmentSelection("remote", "C:/work/remote"),
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
            apply_patch_tool_type=ApplyPatchToolType.FREEFORM,
            supports_image_detail_original=True,
        )
        session.turn_context.model_info = model_info
        session.turn_context.features = FeatureSet(Feature.EXEC_PERMISSION_APPROVALS)

        plan = await build_user_turn_responses_request_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
        )

        specs_by_name = {spec["name"]: spec for spec in plan.request["tools"]}
        self.assertIn("environment_id", specs_by_name["exec_command"]["parameters"]["properties"])
        self.assertIn("additional_permissions", specs_by_name["exec_command"]["parameters"]["properties"])
        self.assertIn("Environment ID", specs_by_name["apply_patch"]["format"]["definition"])
        self.assertIn("environment_id", specs_by_name["view_image"]["parameters"]["properties"])
        self.assertEqual(specs_by_name["view_image"]["parameters"]["properties"]["detail"]["enum"], ["high", "original"])

    async def test_build_user_input_op_request_does_not_make_turn_environments_sticky(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        await build_user_input_op_responses_request_from_session(
            session,
            Op.user_input((UserInput.text_input("hello"),), environments=(TurnEnvironmentSelection("env-1", "C:/work/project"),)),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        await build_user_turn_responses_request_from_session(
            session,
            (UserInput.text_input("next"),),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertIsNone(session.turn_context.environments)

    async def test_build_user_input_op_request_records_only_changed_additional_context(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        first = Op.user_input(
            (),
            additional_context={"app": {"kind": "application", "value": "context v1"}},
        )
        same = Op.user_input(
            (),
            additional_context={"app": {"kind": "application", "value": "context v1"}},
        )
        changed = Op.user_input(
            (),
            additional_context={"app": {"kind": "application", "value": "context v2"}},
        )

        await build_user_input_op_responses_request_from_session(
            session,
            first,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        await build_user_input_op_responses_request_from_session(
            session,
            same,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        await build_user_input_op_responses_request_from_session(
            session,
            changed,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(session.recorded), 2)
        self.assertEqual(session.recorded[0][0].content[0].text, "<app>context v1</app>")
        self.assertEqual(session.recorded[1][0].content[0].text, "<app>context v2</app>")

    async def test_additional_context_removes_one_value_while_adding_another(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        first = Op.user_input(
            (UserInput.text_input("first turn"),),
            additional_context={
                "automation_info": {"kind": "untrusted", "value": "run one"},
                "browser_info": {"kind": "untrusted", "value": "tab one"},
            },
        )
        second = Op.user_input(
            (UserInput.text_input("second turn"),),
            additional_context={
                "automation_info": {"kind": "untrusted", "value": "run one"},
                "terminal_info": {"kind": "untrusted", "value": "pty one"},
            },
        )
        third = Op.user_input(
            (UserInput.text_input("third turn"),),
            additional_context={
                "automation_info": {"kind": "untrusted", "value": "run one"},
                "browser_info": {"kind": "untrusted", "value": "tab one"},
                "terminal_info": {"kind": "untrusted", "value": "pty one"},
            },
        )

        first_plan = await build_user_input_op_responses_request_from_session(
            session,
            first,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        second_plan = await build_user_input_op_responses_request_from_session(
            session,
            second,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        third_plan = await build_user_input_op_responses_request_from_session(
            session,
            third,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        def user_texts(plan):
            return [item.content[0].text for item in plan.request["input"] if item.role == "user"]

        self.assertEqual(
            user_texts(first_plan),
            [
                "<external_automation_info>run one</external_automation_info>",
                "<external_browser_info>tab one</external_browser_info>",
                "first turn",
            ],
        )
        self.assertEqual(
            user_texts(second_plan),
            [
                "<external_automation_info>run one</external_automation_info>",
                "<external_browser_info>tab one</external_browser_info>",
                "first turn",
                "<external_terminal_info>pty one</external_terminal_info>",
                "second turn",
            ],
        )
        self.assertEqual(
            user_texts(third_plan),
            [
                "<external_automation_info>run one</external_automation_info>",
                "<external_browser_info>tab one</external_browser_info>",
                "first turn",
                "<external_terminal_info>pty one</external_terminal_info>",
                "second turn",
                "<external_browser_info>tab one</external_browser_info>",
                "third turn",
            ],
        )

    async def test_additional_context_empty_map_clears_then_readds_values(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        with_context = Op.user_input(
            (UserInput.text_input("first"),),
            additional_context={"app": {"kind": "application", "value": "context"}},
        )
        cleared = Op.user_input((UserInput.text_input("cleared"),), additional_context={})
        restored = Op.user_input(
            (UserInput.text_input("restored"),),
            additional_context={"app": {"kind": "application", "value": "context"}},
        )

        first_plan = await build_user_input_op_responses_request_from_session(
            session,
            with_context,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        cleared_plan = await build_user_input_op_responses_request_from_session(
            session,
            cleared,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        restored_plan = await build_user_input_op_responses_request_from_session(
            session,
            restored,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        first_user_texts = [item.content[0].text for item in first_plan.request["input"] if item.role == "user"]
        cleared_user_texts = [item.content[0].text for item in cleared_plan.request["input"] if item.role == "user"]
        restored_user_texts = [item.content[0].text for item in restored_plan.request["input"] if item.role == "user"]

        self.assertEqual(first_user_texts, ["first"])
        self.assertEqual(cleared_user_texts, ["first", "cleared"])
        self.assertEqual(restored_user_texts, ["first", "cleared", "restored"])

        self.assertIn("<app>context</app>", [item.content[0].text for item in first_plan.request["input"] if item.role == "developer"])
        self.assertTrue(any(item.role == "user" and item.content[0].text == "cleared" for item in cleared_plan.request["input"]))
        self.assertFalse(any(
            item.role == "developer" and item.content[0].text == "<app>context</app>"
            for item in cleared_plan.request["input"]
        ))
        self.assertIn("<app>context</app>", [item.content[0].text for item in restored_plan.request["input"] if item.role == "developer"])
        self.assertTrue(any(item.role == "user" and item.content[0].text == "restored" for item in restored_plan.request["input"]))

    async def test_build_user_input_op_request_clears_additional_context_when_absent(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        with_context = Op.user_input(
            (),
            additional_context={"app": {"kind": "application", "value": "context"}},
        )

        await build_user_input_op_responses_request_from_session(
            session,
            with_context,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        first_plan = await build_user_input_op_responses_request_from_session(
            session,
            with_context,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        second_plan = await build_user_input_op_responses_request_from_session(
            session,
            Op.user_input((UserInput.text_input("hello"),)),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        third_plan = await build_user_input_op_responses_request_from_session(
            session,
            Op.user_input(()),
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )
        fourth_plan = await build_user_input_op_responses_request_from_session(
            session,
            with_context,
            client,
            provider,
            model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        def user_texts(plan):
            return [item.content[0].text for item in plan.request["input"] if item.role == "user"]

        self.assertEqual(user_texts(first_plan), [])
        self.assertEqual(user_texts(second_plan), ["hello"])
        self.assertEqual(user_texts(third_plan), ["hello"])
        self.assertEqual(user_texts(fourth_plan), ["hello"])
        self.assertEqual(len(session.recorded), 2)
        self.assertEqual(session.recorded[0][0].content[0].text, "<app>context</app>")
        self.assertEqual(session.recorded[1][0].content[0].text, "<app>context</app>")

    async def test_build_user_turn_request_uses_turn_context_model_info(self) -> None:
        session = Session()
        session.turn_context.model_info = SimpleNamespace(
            slug="gpt-collab",
            input_modalities=("text",),
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        stale_model_info = SimpleNamespace(
            slug="gpt-stale",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )

        plan = await build_user_turn_responses_request_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            stale_model_info,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(plan.request["model"], "gpt-collab")

    async def test_run_user_turn_sampling_records_sampler_response_items(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 1)
        self.assertIs(seen_requests[0].session, session)
        self.assertIs(seen_requests[0].turn_context, session.turn_context)
        self.assertEqual(result.response_items[0].role, "assistant")
        self.assertEqual(session.recorded[-1], result.response_items)
        self.assertEqual(session.history[-1].content[0].text, "done")

    async def test_run_user_turn_sampling_dispatches_and_records_tool_outputs(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        handler = EchoHandler()
        router = ToolRouter.from_parts(ToolRegistry.from_tools([handler]), ())
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            if len(seen_requests) == 1:
                return [ResponseItem.function_call("echo", "{}", "call-echo")]
            return [ResponseItem.message("assistant", (ContentItem.output_text("done after tool"),))]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: router,
        )

        self.assertEqual(len(seen_requests), 2)
        self.assertTrue(
            any(
                item.type == "function_call_output" and item.call_id == "call-echo"
                for item in seen_requests[1].request_plan.request["input"]
            )
        )
        self.assertEqual(len(handler.invocations), 1)
        self.assertIs(handler.invocations[0].session, session)
        self.assertIs(handler.invocations[0].turn, session.turn_context)
        self.assertEqual(result.response_items[0].type, "function_call")
        self.assertEqual(result.response_items[1].content[0].text, "done after tool")
        self.assertEqual(result.tool_response_items[0].type, "function_call_output")
        self.assertEqual(result.tool_response_items[0].call_id, "call-echo")
        self.assertEqual(session.recorded[-2], result.tool_response_items)
        self.assertEqual(session.history[-1].content[0].text, "done after tool")
        self.assertEqual(len(result.request_plans), 2)

    async def test_run_user_turn_sampling_can_limit_tool_followups(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        handler = EchoHandler()
        router = ToolRouter.from_parts(ToolRegistry.from_tools([handler]), ())

        async def sampler(_request):
            return [ResponseItem.function_call("echo", "{}", "call-echo")]

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: router,
            max_tool_followups=0,
        )

        self.assertEqual(len(handler.invocations), 1)
        self.assertEqual(len(result.request_plans), 1)
        self.assertEqual(result.response_items[0].type, "function_call")
        self.assertEqual(result.tool_response_items[0].type, "function_call_output")

    async def test_run_user_input_op_sampling_records_sampler_response_items(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        seen_requests = []

        async def sampler(request):
            seen_requests.append(request)
            return [ResponseItem.message("assistant", (ContentItem.output_text("done"),))]

        result = await run_user_input_op_sampling_from_session(
            session,
            Op.user_input((UserInput.text_input("hello"),)),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(seen_requests), 1)
        self.assertEqual(result.response_items[0].content[0].text, "done")
        self.assertEqual(session.history[-1].content[0].text, "done")

    async def test_run_user_turn_sampling_can_use_model_client_session_sampler(self) -> None:
        session = Session()
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
        model_session = client.new_session()
        provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
        model_info = SimpleNamespace(
            slug="gpt-test",
            supports_reasoning_summaries=False,
            support_verbosity=False,
            service_tier_for_request=lambda tier: tier,
        )
        transported = []

        async def transport(prepared):
            transported.append(prepared)
            self.assertEqual(prepared.prepared_request["model"], "gpt-test")
            self.assertEqual(prepared.prepared_request["instructions"], "base")
            self.assertIn("input", prepared.prepared_request)
            return [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "done"}]}]

        async def sampler(request):
            return await sample_with_model_client_session(request, model_session, transport)

        result = await run_user_turn_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            provider,
            model_info,
            sampler,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(len(transported), 1)
        self.assertEqual(result.response_items[0].content[0].text, "done")
        self.assertEqual(session.history[-1].content[0].text, "done")


if __name__ == "__main__":
    unittest.main()
