import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from pycodex.core.client import ModelClient
from pycodex.core.handler_utils import apply_granted_turn_permissions, record_granted_request_permissions
from pycodex.core.http_transport import run_user_turn_http_sampling_from_session
from pycodex.core.session_runtime import InMemoryCodexSession
from pycodex.core.codex_thread import SessionSettingsUpdate
from pycodex.core.tool_orchestrator import build_tool_orchestrator_plan_for_session, OrchestratorApprovalKind
from pycodex.core.tool_sandboxing import ExecApprovalRequirement
from pycodex.protocol import (
    AdditionalPermissionProfile,
    ApprovalsReviewer,
    AskForApproval,
    CollaborationMode,
    ContentItem,
    FileSystemAccessMode,
    FileSystemPermissions,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    FileSystemSpecialPath,
    NetworkPermissions,
    PermissionGrantScope,
    RequestPermissionProfile,
    RequestPermissionsArgs,
    RequestPermissionsResponse,
    ResponseItem,
    ReasoningEffort,
    ReasoningSummary,
    SandboxPermissions,
    SandboxPolicy,
    SERVICE_TIER_DEFAULT_REQUEST_VALUE,
    ServiceTier,
    ModeKind,
    Settings,
    ThreadSettingsOverrides,
    TurnEnvironmentSelection,
    TurnContextNetworkItem,
    UserInput,
)


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


class ModelMessages:
    def __init__(self, messages):
        self._messages = messages

    def get_personality_message(self, personality):
        return self._messages.get(personality)


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
        self.assertEqual(len(session.recorded_batches), 3)
        self.assertEqual(session.history[-1], result.response_items[0])
        self.assertEqual(session.history[-1].content[0].text, "done")
        self.assertEqual(seen["body"]["instructions"], "base")
        self.assertEqual(seen["body"]["input"][0]["role"], "developer")
        self.assertEqual(seen["body"]["input"][1]["role"], "developer")
        self.assertIn("<permissions instructions>", seen["body"]["input"][1]["content"][0]["text"])
        self.assertEqual(seen["body"]["input"][2]["role"], "user")
        self.assertIn("<environment_context>", seen["body"]["input"][2]["content"][0]["text"])
        self.assertIn("project instructions", seen["body"]["input"][3]["content"][0]["text"])
        self.assertEqual(seen["body"]["input"][4]["content"][0]["text"], "hello")

    async def test_in_memory_session_records_context_update_items_from_reference_context(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            current_date="2026-05-30",
            timezone="Asia/Shanghai",
        )

        first_turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(first_turn)
        session.cwd = Path("C:/work/other")
        second_turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(second_turn)

        self.assertEqual(session.context_updates_recorded, 2)
        self.assertEqual(len(session.recorded_batches), 2)
        self.assertEqual(session.recorded_batches[0][0].role, "developer")
        self.assertIn("<permissions instructions>", session.recorded_batches[0][0].content[0].text)
        self.assertEqual(session.recorded_batches[0][1].role, "user")
        self.assertIn("<environment_context>", session.recorded_batches[0][1].content[0].text)
        item = session.recorded_batches[1][0]
        self.assertEqual(item.role, "user")
        self.assertIn("<environment_context>", item.content[0].text)
        self.assertIn(f"<cwd>{Path('C:/work/other')}</cwd>", item.content[0].text)
        self.assertEqual(session.history[-1], item)

    async def test_in_memory_session_reasoning_settings_feed_http_sampling_request(self) -> None:
        seen = {}

        def opener(request):
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": True,
                "support_verbosity": False,
                "default_reasoning_level": "medium",
                "service_tier_for_request": lambda _self, tier: tier,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            reasoning_effort="high",
            reasoning_summary="concise",
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")

        await run_user_turn_http_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(seen["body"]["reasoning"], {"effort": "high", "summary": "concise"})

    async def test_in_memory_session_service_tier_feeds_http_sampling_request(self) -> None:
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
            service_tier="priority",
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")

        await run_user_turn_http_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(seen["body"]["service_tier"], "priority")

    async def test_in_memory_session_service_tier_enum_feeds_http_sampling_request(self) -> None:
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
                "service_tier_for_request": lambda _self, tier: tier if tier == "priority" else None,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            service_tier=ServiceTier.FAST,
        )
        client = ModelClient(session_id="session", thread_id="thread", installation_id="install")

        await run_user_turn_http_sampling_from_session(
            session,
            (UserInput.text_input("hello"),),
            client,
            {"base_url": "https://api.example.test/v1"},
            model_info,
            auth="sk-test",
            opener=opener,
            built_tools=lambda _sess, _turn: Router(),
        )

        self.assertEqual(seen["body"]["service_tier"], "priority")

    async def test_in_memory_session_turn_config_inherits_service_tier(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project", service_tier="priority")

        turn = await session.new_default_turn()

        self.assertEqual(turn.config.service_tier, "priority")

    async def test_in_memory_session_update_settings_applies_turn_local_environments_once(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            environments=(TurnEnvironmentSelection("sticky", Path("C:/work/project")),),
        )
        environments = (TurnEnvironmentSelection("env-1", Path("C:/work/project")),)

        await session.update_settings(SessionSettingsUpdate(environments=environments))
        override_turn = await session.new_default_turn()
        sticky_turn = await session.new_default_turn()

        self.assertEqual(session.environments, (TurnEnvironmentSelection("sticky", Path("C:/work/project")),))
        self.assertEqual(override_turn.environments, environments)
        self.assertEqual(sticky_turn.environments, session.environments)

    async def test_in_memory_session_default_turn_overlays_cwd_onto_sticky_primary_environment(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            environments=(TurnEnvironmentSelection("sticky", Path("C:/work/selected")),),
        )

        turn = await session.new_default_turn()

        self.assertEqual(session.environments, (TurnEnvironmentSelection("sticky", Path("C:/work/selected")),))
        self.assertEqual(turn.environments, (TurnEnvironmentSelection("sticky", Path("C:/work/project")),))
        self.assertEqual(turn.cwd, Path("C:/work/project"))
        self.assertEqual(turn.config.cwd, Path("C:/work/project"))

    async def test_in_memory_session_turn_local_environment_preserves_selected_cwd(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            environments=(TurnEnvironmentSelection("sticky", Path("C:/work/selected")),),
        )
        environments = (TurnEnvironmentSelection("env-1", Path("C:/work/explicit")),)

        await session.update_settings(SessionSettingsUpdate(environments=environments))
        turn = await session.new_default_turn()

        self.assertEqual(turn.environments, environments)
        self.assertEqual(turn.cwd, Path("C:/work/explicit"))
        self.assertEqual(turn.config.cwd, Path("C:/work/explicit"))

    async def test_in_memory_session_environment_context_renders_multiple_turn_environments(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            environments=(
                TurnEnvironmentSelection("local", Path("C:/work/local")),
                TurnEnvironmentSelection("remote", Path("C:/work/remote")),
            ),
            current_date="2026-05-30",
            timezone="Asia/Shanghai",
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        context_item = session.recorded_batches[0][1]
        context_text = context_item.content[0].text
        self.assertIn("<environments>", context_text)
        self.assertIn('<environment id="local">', context_text)
        self.assertIn(f"<cwd>{Path('C:/work/project')}</cwd>", context_text)
        self.assertIn('<environment id="remote">', context_text)
        self.assertIn(f"<cwd>{Path('C:/work/remote')}</cwd>", context_text)
        self.assertIn("<current_date>2026-05-30</current_date>", context_text)

    async def test_in_memory_session_default_turn_supplies_local_time_context(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        self.assertRegex(turn.current_date, r"^\d{4}-\d{2}-\d{2}$")
        self.assertIsInstance(turn.timezone, str)
        self.assertTrue(turn.timezone)
        context_text = session.recorded_batches[0][1].content[0].text
        self.assertIn("<current_date>", context_text)
        self.assertIn("<timezone>", context_text)

    async def test_in_memory_session_update_settings_applies_final_output_json_schema(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}

        await session.update_settings(SessionSettingsUpdate(final_output_json_schema=schema))
        turn_with_schema = await session.new_default_turn()
        await session.update_settings(SessionSettingsUpdate(final_output_json_schema=None))
        turn_without_schema = await session.new_default_turn()

        self.assertEqual(turn_with_schema.final_output_json_schema, schema)
        self.assertIsNone(turn_without_schema.final_output_json_schema)

    async def test_in_memory_session_turn_config_inherits_reasoning_settings(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            reasoning_effort="high",
            reasoning_summary="concise",
        )

        turn = await session.new_default_turn()

        self.assertEqual(turn.config.model_reasoning_effort, "high")
        self.assertEqual(turn.config.model_reasoning_summary, "concise")

    async def test_in_memory_session_turn_inherits_collaboration_reasoning_effort(self) -> None:
        collaboration_mode = SimpleNamespace(
            mode="default",
            settings=SimpleNamespace(model="gpt-5.2-codex", reasoning_effort=ReasoningEffort.HIGH),
        )
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            collaboration_mode=collaboration_mode,
        )

        turn = await session.new_default_turn()

        self.assertEqual(turn.reasoning_effort, ReasoningEffort.HIGH)
        self.assertEqual(turn.config.model_reasoning_effort, ReasoningEffort.HIGH)

    async def test_in_memory_session_turn_inherits_collaboration_model(self) -> None:
        base_model_info = SimpleNamespace(
            slug="gpt-old",
            input_modalities=("text",),
            supports_reasoning_summaries=True,
        )
        collaboration_mode = SimpleNamespace(
            mode="default",
            settings=SimpleNamespace(model="gpt-5.2-codex"),
        )
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=base_model_info,
            collaboration_mode=collaboration_mode,
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)
        reference = await session.reference_context_item()

        self.assertEqual(turn.model_info.slug, "gpt-5.2-codex")
        self.assertEqual(turn.model_info.input_modalities, ("text",))
        self.assertEqual(turn.config.model, "gpt-5.2-codex")
        self.assertIsNotNone(reference)
        self.assertEqual(reference.model, "gpt-5.2-codex")

    async def test_in_memory_session_preview_and_update_settings(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=SimpleNamespace(slug="gpt-base"),
        )
        collaboration_mode = SimpleNamespace(
            mode="default",
            settings=SimpleNamespace(model="gpt-next", reasoning_effort=ReasoningEffort.HIGH),
        )
        updates = SessionSettingsUpdate(
            collaboration_mode=collaboration_mode,
            reasoning_summary=ReasoningSummary.CONCISE,
            service_tier="priority",
        )

        preview = await session.preview_settings(updates)
        self.assertEqual(preview.model, "gpt-next")
        self.assertEqual(preview.reasoning_effort, ReasoningEffort.HIGH)
        self.assertEqual(preview.reasoning_summary, ReasoningSummary.CONCISE)
        self.assertEqual(preview.service_tier, "priority")
        self.assertIsNone(session.collaboration_mode)

        applied = await session.update_settings(updates)
        self.assertEqual(applied.model, "gpt-next")
        self.assertIs(session.collaboration_mode, collaboration_mode)
        self.assertEqual(session.reasoning_effort, ReasoningEffort.HIGH)
        self.assertEqual(session.reasoning_summary, ReasoningSummary.CONCISE)
        self.assertEqual(session.service_tier, "priority")

    async def test_in_memory_session_settings_normalize_service_tier_values(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")

        preview = await session.preview_settings(SessionSettingsUpdate(service_tier=ServiceTier.FAST))
        self.assertEqual(preview.service_tier, "priority")

        applied = await session.update_settings(SessionSettingsUpdate(service_tier="fast"))
        self.assertEqual(applied.service_tier, "priority")
        self.assertEqual(session.service_tier, "priority")

        defaulted = await session.update_settings(SessionSettingsUpdate(service_tier=None))
        self.assertEqual(defaulted.service_tier, SERVICE_TIER_DEFAULT_REQUEST_VALUE)
        self.assertEqual(session.service_tier, SERVICE_TIER_DEFAULT_REQUEST_VALUE)

        unchanged = await session.update_settings(SessionSettingsUpdate())
        self.assertEqual(unchanged.service_tier, SERVICE_TIER_DEFAULT_REQUEST_VALUE)
        self.assertEqual(session.service_tier, SERVICE_TIER_DEFAULT_REQUEST_VALUE)

    async def test_in_memory_session_applies_protocol_thread_settings_overrides(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=SimpleNamespace(slug="gpt-base"),
            collaboration_mode=CollaborationMode(
                mode=ModeKind.DEFAULT,
                settings=Settings(
                    model="gpt-current",
                    reasoning_effort=ReasoningEffort.HIGH,
                    developer_instructions="keep this",
                ),
            ),
            service_tier="priority",
        )
        preview = await session.preview_thread_settings_overrides(ThreadSettingsOverrides.default())

        self.assertEqual(preview.model, "gpt-current")
        self.assertEqual(preview.reasoning_effort, ReasoningEffort.HIGH)
        self.assertEqual(preview.service_tier, "priority")

        applied = await session.apply_thread_settings_overrides(
            ThreadSettingsOverrides(
                model="gpt-next",
                effort=None,
                service_tier=None,
            )
        )

        self.assertEqual(applied.model, "gpt-next")
        self.assertIsNone(applied.reasoning_effort)
        self.assertEqual(applied.service_tier, SERVICE_TIER_DEFAULT_REQUEST_VALUE)
        self.assertEqual(session.collaboration_mode.settings.model, "gpt-next")
        self.assertIsNone(session.collaboration_mode.settings.reasoning_effort)
        self.assertEqual(session.collaboration_mode.settings.developer_instructions, "keep this")
        self.assertEqual(session.service_tier, SERVICE_TIER_DEFAULT_REQUEST_VALUE)

    async def test_in_memory_session_thread_config_snapshot_reflects_current_settings(self) -> None:
        collaboration_mode = SimpleNamespace(
            mode="default",
            settings=SimpleNamespace(model="gpt-current", reasoning_effort=ReasoningEffort.HIGH),
        )
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=SimpleNamespace(slug="gpt-base"),
            model_provider_id="openai",
            collaboration_mode=collaboration_mode,
            reasoning_summary=ReasoningSummary.CONCISE,
            service_tier="priority",
        )

        snapshot = await session.thread_config_snapshot()

        self.assertEqual(snapshot.model, "gpt-current")
        self.assertEqual(snapshot.model_provider_id, "openai")
        self.assertEqual(snapshot.reasoning_effort, ReasoningEffort.HIGH)
        self.assertEqual(snapshot.reasoning_summary, ReasoningSummary.CONCISE)
        self.assertEqual(snapshot.service_tier, "priority")
        self.assertIs(snapshot.collaboration_mode, collaboration_mode)

    async def test_in_memory_session_settings_snapshot_tracks_workspace_roots(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=SimpleNamespace(slug="gpt-base"),
            workspace_roots=("C:/work/project", "C:/work/shared"),
            profile_workspace_roots=("C:/profile/root",),
            active_permission_profile="active-profile",
        )

        preview = await session.preview_settings(SessionSettingsUpdate(cwd="D:/next/project"))
        self.assertEqual(preview.cwd, Path("D:/next/project"))
        self.assertEqual(preview.workspace_roots, (Path("D:/next/project"), Path("C:/work/shared")))
        self.assertEqual(preview.profile_workspace_roots, (Path("C:/profile/root"),))
        self.assertEqual(preview.active_permission_profile, "active-profile")
        self.assertEqual(session.cwd, Path("C:/work/project"))

        applied = await session.update_settings(
            SessionSettingsUpdate(
                cwd="D:/next/project",
                workspace_roots=("D:/explicit/root",),
                profile_workspace_roots=("D:/profile/root",),
                active_permission_profile="next-profile",
            )
        )

        self.assertEqual(applied.workspace_roots, (Path("D:/explicit/root"),))
        self.assertEqual(session.cwd, Path("D:/next/project"))
        self.assertEqual(session.workspace_roots, (Path("D:/explicit/root"),))
        self.assertEqual(session.profile_workspace_roots, (Path("D:/profile/root"),))
        self.assertEqual(session.active_permission_profile, "next-profile")

    async def test_in_memory_session_turn_inherits_session_features(self) -> None:
        features = object()
        session = InMemoryCodexSession(cwd="C:/work/project", features=features)

        turn = await session.new_default_turn()

        self.assertIs(turn.features, features)

    async def test_in_memory_session_turn_inherits_approvals_reviewer(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            approvals_reviewer=ApprovalsReviewer.AUTO_REVIEW,
        )

        turn = await session.new_default_turn()

        self.assertEqual(turn.config.approvals_reviewer, ApprovalsReviewer.AUTO_REVIEW)

    async def test_in_memory_session_reference_context_preserves_turn_id(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project", turn_id="turn-123")

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(reference.turn_id, "turn-123")

    async def test_in_memory_session_reference_context_preserves_reasoning_effort_and_auto_summary(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            reasoning_effort="high",
            reasoning_summary="concise",
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(reference.effort, "high")
        self.assertEqual(reference.summary, "auto")

    async def test_in_memory_session_reference_context_writes_auto_summary_compat_field(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            reasoning_summary=ReasoningSummary.CONCISE,
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(reference.summary, "auto")

    async def test_in_memory_session_reference_context_serializes_reasoning_effort_enum(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            reasoning_effort=ReasoningEffort.HIGH,
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(reference.effort, "high")

    async def test_in_memory_session_reference_context_preserves_sandbox_policies(self) -> None:
        sandbox_policy = SandboxPolicy.read_only()
        file_system_policy = FileSystemSandboxPolicy.default()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            sandbox_policy=sandbox_policy,
            file_system_sandbox_policy=file_system_policy,
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(reference.sandbox_policy, sandbox_policy)
        self.assertEqual(reference.file_system_sandbox_policy, file_system_policy)

    async def test_in_memory_session_reference_context_normalizes_network_item(self) -> None:
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            network=SimpleNamespace(
                allowed_domains=("api.example.com",),
                denied_domains=("bad.example.com",),
            ),
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(
            reference.network,
            TurnContextNetworkItem(
                allowed_domains=("api.example.com",),
                denied_domains=("bad.example.com",),
            ),
        )

    async def test_in_memory_session_initial_context_prepends_model_switch_message(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-new",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "get_model_instructions": lambda _self, _personality: "Use the new model policy.",
            },
        )()
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)
        await session.set_previous_turn_settings(SimpleNamespace(model="gpt-old", realtime_active=False))

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        self.assertEqual(session.recorded_batches[0][0].role, "developer")
        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertIn("<model_switch>", developer_sections[0])
        self.assertIn("Use the new model policy.", developer_sections[0])
        self.assertIn("<permissions instructions>", developer_sections[1])
        self.assertEqual((await session.previous_turn_settings()).model, "gpt-new")

    async def test_in_memory_session_initial_context_includes_collaboration_mode_after_permissions(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            collaboration_mode=SimpleNamespace(
                settings=SimpleNamespace(developer_instructions="Plan before editing.")
            ),
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertIn("<permissions instructions>", developer_sections[0])
        self.assertEqual(developer_sections[1], "<collaboration_mode>Plan before editing.</collaboration_mode>")

    async def test_in_memory_session_reference_context_jsonifies_collaboration_mode(self) -> None:
        collaboration_mode = SimpleNamespace(
            mode="default",
            settings=SimpleNamespace(developer_instructions="Plan before editing."),
        )
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            collaboration_mode=collaboration_mode,
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(
            reference.collaboration_mode,
            {
                "mode": "default",
                "settings": {"developer_instructions": "Plan before editing."},
            },
        )

    async def test_in_memory_session_reference_context_defaults_collaboration_mode(self) -> None:
        model_info = type("ModelInfo", (), {"slug": "gpt-5.2-codex"})()
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        reference = await session.reference_context_item()
        self.assertIsNotNone(reference)
        self.assertEqual(
            reference.collaboration_mode,
            {"mode": "default", "settings": {"model": "gpt-5.2-codex"}},
        )

    async def test_in_memory_session_initial_context_includes_developer_instructions_after_permissions(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            developer_instructions="Follow the project policy.",
            collaboration_mode=SimpleNamespace(
                settings=SimpleNamespace(developer_instructions="Plan before editing.")
            ),
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertIn("<permissions instructions>", developer_sections[0])
        self.assertEqual(developer_sections[1], "Follow the project policy.")
        self.assertEqual(developer_sections[2], "<collaboration_mode>Plan before editing.</collaboration_mode>")

    async def test_in_memory_session_initial_context_includes_realtime_start(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            realtime_active=True,
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertIn("<permissions instructions>", developer_sections[0])
        self.assertIn("<realtime_conversation>", developer_sections[1])
        self.assertIn("Realtime conversation started.", developer_sections[1])

    async def test_in_memory_session_initial_context_includes_custom_realtime_start(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            realtime_active=True,
            experimental_realtime_start_instructions="Use short spoken replies.",
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertIn("<permissions instructions>", developer_sections[0])
        self.assertIn("<realtime_conversation>", developer_sections[1])
        self.assertIn("Use short spoken replies.", developer_sections[1])

    async def test_in_memory_session_initial_context_uses_previous_turn_settings_for_realtime_end(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)
        await session.set_previous_turn_settings(SimpleNamespace(model="gpt-test", realtime_active=True))

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertIn("<permissions instructions>", developer_sections[0])
        self.assertIn("<realtime_conversation>", developer_sections[1])
        self.assertIn("Realtime conversation ended.", developer_sections[1])

    async def test_in_memory_session_initial_context_includes_personality_spec(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "model_messages": ModelMessages({"friendly": "Be warm."}),
                "supports_personality": lambda _self: False,
                "get_model_instructions": lambda _self, _personality: "base",
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            personality="friendly",
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertIn("<permissions instructions>", developer_sections[0])
        self.assertIn("<personality_spec>", developer_sections[1])
        self.assertIn("Be warm.", developer_sections[1])

    async def test_in_memory_session_initial_context_skips_baked_personality_spec(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "model_messages": ModelMessages({"friendly": "Be warm."}),
                "supports_personality": lambda _self: True,
                "get_model_instructions": lambda _self, _personality: "base",
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            personality="friendly",
            base_instructions="base",
        )

        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)

        developer_sections = [content.text for content in session.recorded_batches[0][0].content]
        self.assertEqual(len(developer_sections), 1)
        self.assertIn("<permissions instructions>", developer_sections[0])

    async def test_in_memory_session_records_personality_update_from_reference_context(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
                "model_messages": ModelMessages(
                    {
                        "friendly": "Be warm.",
                        "terse": "Be concise.",
                    }
                ),
            },
        )()
        session = InMemoryCodexSession(
            cwd="C:/work/project",
            model_info=model_info,
            personality="friendly",
        )

        first_turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(first_turn)
        session.personality = "terse"
        second_turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(second_turn)

        self.assertEqual(len(session.recorded_batches), 2)
        item = session.recorded_batches[1][0]
        self.assertEqual(item.role, "developer")
        self.assertIn("<personality_spec>", item.content[0].text)
        self.assertIn("Be concise.", item.content[0].text)

    async def test_in_memory_session_exposes_reference_context_item(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)

        self.assertIsNone(await session.reference_context_item())
        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)
        reference = await session.reference_context_item()

        self.assertIsNotNone(reference)
        self.assertEqual(reference.cwd, Path("C:/work/project"))
        self.assertEqual(reference.model, "gpt-test")

    async def test_in_memory_session_can_set_and_replace_reference_context_item(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)
        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)
        reference = await session.reference_context_item()
        replacement = {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "compacted"}],
        }

        await session.set_reference_context_item(None)
        self.assertIsNone(await session.reference_context_item())
        await session.replace_history([replacement], reference)

        self.assertEqual(await session.reference_context_item(), reference)
        self.assertEqual(len(session.history), 1)
        self.assertEqual(session.history[0].role, "assistant")
        self.assertEqual(session.history[0].content[0].text, "compacted")

    async def test_in_memory_session_replace_compacted_history_records_compacted_item(self) -> None:
        model_info = type(
            "ModelInfo",
            (),
            {
                "slug": "gpt-test",
                "supports_reasoning_summaries": False,
                "support_verbosity": False,
            },
        )()
        session = InMemoryCodexSession(cwd="C:/work/project", model_info=model_info)
        turn = await session.new_default_turn()
        await session.record_context_updates_and_set_reference_context_item(turn)
        reference = await session.reference_context_item()
        replacement = {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "summarized"}],
        }
        compacted_item = {
            "message": "summary",
            "replacement_history": [replacement],
        }

        await session.replace_compacted_history([replacement], reference, compacted_item)

        self.assertEqual(await session.reference_context_item(), reference)
        self.assertEqual(session.history[0].content[0].text, "summarized")
        self.assertEqual(len(session.compacted_items), 1)
        self.assertEqual(session.compacted_items[0].message, "summary")
        self.assertEqual(session.compacted_items[0].replacement_history, (replacement,))

    async def test_in_memory_session_inject_no_new_turn_records_items_and_flushes(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        item = {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "outside turn"}],
        }

        await session.inject_no_new_turn([item], None)
        await session.flush_rollout()

        self.assertEqual(len(session.recorded_batches), 1)
        self.assertEqual(session.recorded_batches[0][0].role, "user")
        self.assertEqual(session.history[-1].content[0].text, "outside turn")
        self.assertEqual(session.flush_rollout_count, 1)

    async def test_in_memory_session_records_session_and_turn_permission_grants(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        session_response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.SESSION,
        )
        turn_response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.TURN,
            strict_auto_review=True,
        )

        await record_granted_request_permissions(session_response, session=session)
        await record_granted_request_permissions(turn_response, turn_state=session)

        expected = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        self.assertEqual(await session.granted_session_permissions(), expected)
        self.assertEqual(await session.granted_turn_permissions(), expected)
        self.assertTrue(session.strict_auto_review_enabled)
        self.assertTrue(await session.strict_auto_review())

    async def test_in_memory_session_new_turn_clears_turn_grants_but_keeps_session_grants(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        session_response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.SESSION,
        )
        turn_response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.TURN,
            strict_auto_review=True,
        )

        await record_granted_request_permissions(session_response, session=session)
        await record_granted_request_permissions(turn_response, turn_state=session)
        await session.new_default_turn()

        self.assertEqual(
            await session.granted_session_permissions(),
            AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )
        self.assertIsNone(await session.granted_turn_permissions())
        self.assertFalse(session.strict_auto_review_enabled)
        self.assertFalse(await session.strict_auto_review())

    async def test_in_memory_session_request_permissions_normalizes_and_records_response(self) -> None:
        def callback(parent_ctx, call_id, args, cwd, cancel_token):
            return RequestPermissionsResponse(
                RequestPermissionProfile(
                    network=NetworkPermissions(enabled=True),
                    file_system=FileSystemPermissions.from_read_write_roots(None, (cwd,)),
                ),
                scope=PermissionGrantScope.SESSION,
            )

        session = InMemoryCodexSession(cwd="C:/work/project", request_permissions_callback=callback)
        requested_child = session.cwd / "child"
        args = RequestPermissionsArgs(
            RequestPermissionProfile(
                network=NetworkPermissions(enabled=True),
                file_system=FileSystemPermissions.from_read_write_roots(None, (requested_child,)),
            )
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, session.cwd, None)

        expected = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        self.assertEqual(response.permissions.to_additional_permission_profile(), expected)
        self.assertEqual(await session.granted_session_permissions(), expected)
        self.assertIsNone(await session.granted_turn_permissions())

    async def test_in_memory_session_request_permissions_passes_session_cwd_when_cwd_missing(self) -> None:
        seen = {}

        def callback(parent_ctx, call_id, args, cwd, cancel_token):
            seen["cwd"] = cwd
            return RequestPermissionsResponse(
                RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
                scope=PermissionGrantScope.TURN,
            )

        session = InMemoryCodexSession(cwd="C:/work/project", request_permissions_callback=callback)
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, None, None)

        self.assertEqual(seen["cwd"], session.cwd)
        self.assertEqual(
            response.permissions.to_additional_permission_profile(),
            AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )

    async def test_in_memory_session_request_permissions_records_turn_scope_and_strict_auto_review(self) -> None:
        def callback(parent_ctx, call_id, args, cwd, cancel_token):
            return RequestPermissionsResponse(
                RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
                scope=PermissionGrantScope.TURN,
                strict_auto_review=True,
            )

        session = InMemoryCodexSession(cwd="C:/work/project", request_permissions_callback=callback)
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, session.cwd, None)

        expected = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        self.assertEqual(response.permissions.to_additional_permission_profile(), expected)
        self.assertIsNone(await session.granted_session_permissions())
        self.assertEqual(await session.granted_turn_permissions(), expected)
        self.assertTrue(session.strict_auto_review_enabled)

    async def test_in_memory_session_empty_strict_turn_response_records_no_strict_state(self) -> None:
        def callback(parent_ctx, call_id, args, cwd, cancel_token):
            return RequestPermissionsResponse(
                RequestPermissionProfile(),
                scope=PermissionGrantScope.TURN,
                strict_auto_review=True,
            )

        session = InMemoryCodexSession(cwd="C:/work/project", request_permissions_callback=callback)
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, session.cwd, None)

        self.assertEqual(
            response,
            RequestPermissionsResponse(
                RequestPermissionProfile(),
                scope=PermissionGrantScope.TURN,
                strict_auto_review=True,
            ),
        )
        self.assertIsNone(await session.granted_session_permissions())
        self.assertIsNone(await session.granted_turn_permissions())
        self.assertFalse(session.strict_auto_review_enabled)

    async def test_in_memory_session_strict_turn_grant_feeds_orchestrator_plan(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.TURN,
            strict_auto_review=True,
        )

        await record_granted_request_permissions(response, turn_state=session)
        plan = await build_tool_orchestrator_plan_for_session(
            session,
            explicit_requirement=ExecApprovalRequirement.skip(),
            approval_policy=AskForApproval.NEVER,
            file_system_sandbox_policy=FileSystemSandboxPolicy.default(),
            sandbox_permissions=SandboxPermissions.USE_DEFAULT,
            managed_network_active=False,
        )

        self.assertEqual(plan.approval.kind, OrchestratorApprovalKind.REQUESTED)
        self.assertTrue(plan.approval.strict_auto_review)
        self.assertTrue(plan.approval.guardian_review_id_required)

    async def test_in_memory_session_request_permissions_rejects_strict_auto_review_session_scope(self) -> None:
        def callback(parent_ctx, call_id, args, cwd, cancel_token):
            return RequestPermissionsResponse(
                RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
                scope=PermissionGrantScope.SESSION,
                strict_auto_review=True,
            )

        session = InMemoryCodexSession(cwd="C:/work/project", request_permissions_callback=callback)
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, session.cwd, None)

        self.assertEqual(response, RequestPermissionsResponse(RequestPermissionProfile()))
        self.assertIsNone(await session.granted_session_permissions())
        self.assertIsNone(await session.granted_turn_permissions())
        self.assertFalse(session.strict_auto_review_enabled)

    async def test_in_memory_session_request_permissions_accepts_async_mapping_response(self) -> None:
        async def callback(parent_ctx, call_id, args, cwd, cancel_token):
            return {
                "permissions": {"network": {"enabled": True}},
                "scope": "turn",
                "strict_auto_review": True,
            }

        session = InMemoryCodexSession(cwd="C:/work/project", request_permissions_callback=callback)
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, session.cwd, None)

        expected = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        self.assertEqual(response.permissions.to_additional_permission_profile(), expected)
        self.assertEqual(await session.granted_turn_permissions(), expected)
        self.assertTrue(session.strict_auto_review_enabled)

    async def test_in_memory_session_request_permissions_without_callback_records_no_grants(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, session.cwd, None)

        self.assertEqual(response, RequestPermissionsResponse(RequestPermissionProfile()))
        self.assertIsNone(await session.granted_session_permissions())
        self.assertIsNone(await session.granted_turn_permissions())
        self.assertFalse(session.strict_auto_review_enabled)

    async def test_in_memory_session_request_permissions_none_callback_response_records_no_grants(self) -> None:
        def callback(parent_ctx, call_id, args, cwd, cancel_token):
            return None

        session = InMemoryCodexSession(cwd="C:/work/project", request_permissions_callback=callback)
        args = RequestPermissionsArgs(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True))
        )

        response = await session.request_permissions_for_cwd(None, "call-1", args, session.cwd, None)

        self.assertEqual(response, RequestPermissionsResponse(RequestPermissionProfile()))
        self.assertIsNone(await session.granted_session_permissions())
        self.assertIsNone(await session.granted_turn_permissions())
        self.assertFalse(session.strict_auto_review_enabled)

    async def test_in_memory_session_grants_feed_later_permission_application(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.SESSION,
        )

        await record_granted_request_permissions(response, session=session)
        effective = await apply_granted_turn_permissions(
            session,
            session.cwd,
            SandboxPermissions.USE_DEFAULT,
            None,
        )

        self.assertEqual(effective.sandbox_permissions, SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS)
        self.assertEqual(
            effective.additional_permissions,
            AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )

    async def test_in_memory_session_turn_grants_feed_later_permission_application(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.TURN,
        )

        await record_granted_request_permissions(response, turn_state=session)
        effective = await apply_granted_turn_permissions(
            session,
            session.cwd,
            SandboxPermissions.USE_DEFAULT,
            None,
        )

        self.assertEqual(effective.sandbox_permissions, SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS)
        self.assertEqual(
            effective.additional_permissions,
            AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )
        self.assertIsNone(await session.granted_session_permissions())

    async def test_in_memory_session_recorded_grant_preapproves_matching_inline_permissions(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        granted = AdditionalPermissionProfile(network=NetworkPermissions(enabled=True))
        response = RequestPermissionsResponse(
            RequestPermissionProfile.from_additional_permission_profile(granted),
            scope=PermissionGrantScope.SESSION,
        )

        await record_granted_request_permissions(response, session=session)
        effective = await apply_granted_turn_permissions(
            session,
            session.cwd,
            SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
            granted,
        )

        self.assertEqual(effective.sandbox_permissions, SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS)
        self.assertEqual(effective.additional_permissions, granted)
        self.assertTrue(effective.permissions_preapproved)

    async def test_in_memory_session_recorded_grant_does_not_preapprove_broader_inline_permissions(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        granted = AdditionalPermissionProfile(
            file_system=FileSystemPermissions.from_read_write_roots(None, (session.cwd / "child",))
        )
        requested = AdditionalPermissionProfile(
            file_system=FileSystemPermissions.from_read_write_roots(None, (session.cwd,))
        )
        response = RequestPermissionsResponse(
            RequestPermissionProfile.from_additional_permission_profile(granted),
            scope=PermissionGrantScope.SESSION,
        )

        await record_granted_request_permissions(response, session=session)
        effective = await apply_granted_turn_permissions(
            session,
            session.cwd,
            SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
            requested,
        )

        self.assertEqual(effective.sandbox_permissions, SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS)
        self.assertEqual(effective.additional_permissions, requested)
        self.assertFalse(effective.permissions_preapproved)

    async def test_in_memory_session_relative_deny_glob_grant_preapproves_matching_inline_permissions(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        requested = AdditionalPermissionProfile(
            file_system=FileSystemPermissions(
                entries=(
                    FileSystemSandboxEntry(
                        FileSystemPath.special(FileSystemSpecialPath.project_roots()),
                        FileSystemAccessMode.WRITE,
                    ),
                    FileSystemSandboxEntry(
                        FileSystemPath.glob_pattern("**/*.env"),
                        FileSystemAccessMode.DENY,
                    ),
                )
            )
        )
        response = RequestPermissionsResponse(
            RequestPermissionProfile.from_additional_permission_profile(requested),
            scope=PermissionGrantScope.SESSION,
        )

        await record_granted_request_permissions(response, session=session)
        effective = await apply_granted_turn_permissions(
            session,
            session.cwd,
            SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
            requested,
        )

        self.assertTrue(effective.permissions_preapproved)

    async def test_in_memory_session_new_turn_stops_turn_grant_application(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.TURN,
        )

        await record_granted_request_permissions(response, turn_state=session)
        await session.new_default_turn()
        effective = await apply_granted_turn_permissions(
            session,
            session.cwd,
            SandboxPermissions.USE_DEFAULT,
            None,
        )

        self.assertEqual(effective.sandbox_permissions, SandboxPermissions.USE_DEFAULT)
        self.assertIsNone(effective.additional_permissions)

    async def test_in_memory_session_session_grant_applies_after_new_turn(self) -> None:
        session = InMemoryCodexSession(cwd="C:/work/project")
        response = RequestPermissionsResponse(
            RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
            scope=PermissionGrantScope.SESSION,
        )

        await record_granted_request_permissions(response, session=session)
        await session.new_default_turn()
        effective = await apply_granted_turn_permissions(
            session,
            session.cwd,
            SandboxPermissions.USE_DEFAULT,
            None,
        )

        self.assertEqual(effective.sandbox_permissions, SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS)
        self.assertEqual(
            effective.additional_permissions,
            AdditionalPermissionProfile(network=NetworkPermissions(enabled=True)),
        )


if __name__ == "__main__":
    unittest.main()
