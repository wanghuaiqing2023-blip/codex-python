import json
import unittest
from types import SimpleNamespace

from pycodex.core.tools.handlers.multi_agents_common import (
    apply_spawn_agent_overrides,
    build_wait_agent_statuses,
    collab_agent_error,
    collab_spawn_error,
    find_spawn_agent_model_name,
    function_arguments,
    parse_collab_input,
    reject_full_fork_spawn_overrides,
    select_spawn_agent_service_tier,
    thread_spawn_source,
    tool_output_code_mode_result,
    tool_output_json_text,
    tool_output_response_item,
    validate_spawn_agent_reasoning_effort,
)
from pycodex.features import Feature, Features
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import (
    AgentPath,
    AgentStatus,
    CodexErr,
    CollabAgentRef,
    ModelPreset,
    ModelServiceTier,
    ReasoningEffort,
    ReasoningEffortPreset,
    SessionSource,
    SubAgentSource,
    ThreadId,
    UserInput,
)


class CoreMultiAgentsCommonTests(unittest.TestCase):
    def test_function_arguments_accepts_only_function_payloads(self) -> None:
        self.assertEqual(function_arguments(ToolPayload.function("{}")), "{}")
        with self.assertRaisesRegex(FunctionCallError, "unsupported payload"):
            function_arguments(ToolPayload.custom("raw"))
        with self.assertRaises(TypeError):
            function_arguments(object())

    def test_tool_output_json_text_serializes_mapping_dataclasses(self) -> None:
        status = AgentStatus.completed("done")
        self.assertEqual(tool_output_json_text(status, "wait_agent"), '{"completed":"done"}')
        self.assertEqual(tool_output_code_mode_result(status, "wait_agent"), {"completed": "done"})

    def test_tool_output_response_item_returns_function_output(self) -> None:
        item = tool_output_response_item(
            "call-1",
            ToolPayload.function("{}"),
            {"ok": True},
            True,
            "send_message",
        )
        self.assertEqual(item.type, "function_call_output")

    def test_build_wait_agent_statuses_preserves_receiver_order_then_sorts_extras(self) -> None:
        first = ThreadId.new()
        second = ThreadId.new()
        extra = ThreadId.new()
        statuses = {
            extra: AgentStatus.errored("boom"),
            second: AgentStatus.completed("done"),
            first: AgentStatus.running(),
        }
        entries = build_wait_agent_statuses(
            statuses,
            (
                CollabAgentRef(thread_id=second, agent_nickname="B", agent_role="worker"),
                CollabAgentRef(thread_id=first, agent_nickname="A"),
            ),
        )
        self.assertEqual([entry.thread_id for entry in entries[:2]], [second, first])
        self.assertEqual(entries[0].agent_nickname, "B")
        self.assertEqual(entries[0].agent_role, "worker")
        self.assertEqual(entries[2].thread_id, extra)

    def test_parse_collab_input_accepts_message_or_items_but_not_both(self) -> None:
        self.assertEqual(parse_collab_input("hello", None), (UserInput.text_input("hello"),))
        items = parse_collab_input(None, ({"type": "text", "text": "hi"},))
        self.assertEqual(items, (UserInput.text_input("hi"),))

        with self.assertRaisesRegex(FunctionCallError, "either message or items"):
            parse_collab_input("hello", (UserInput.text_input("hi"),))
        with self.assertRaisesRegex(FunctionCallError, "Provide one of"):
            parse_collab_input(None, None)
        with self.assertRaisesRegex(FunctionCallError, "Empty message"):
            parse_collab_input(" ", None)
        with self.assertRaisesRegex(FunctionCallError, "Items can't be empty"):
            parse_collab_input(None, ())

    def test_collab_error_helpers_match_rust_model_messages(self) -> None:
        thread_id = ThreadId.new()

        self.assertEqual(str(collab_spawn_error(CodexErr.unsupported_operation("thread manager dropped"))), "collab manager unavailable")
        self.assertEqual(str(collab_spawn_error(CodexErr.unsupported_operation("nope"))), "nope")
        self.assertIn("collab spawn failed:", str(collab_spawn_error(CodexErr.fatal("boom"))))
        self.assertEqual(str(collab_agent_error(thread_id, CodexErr.thread_not_found(str(thread_id)))), f"agent with id {thread_id} not found")
        self.assertEqual(str(collab_agent_error(thread_id, CodexErr.simple("internal_agent_died"))), f"agent with id {thread_id} is closed")
        self.assertEqual(str(collab_agent_error(thread_id, CodexErr.unsupported_operation("anything"))), "collab manager unavailable")
        self.assertIn("collab tool failed:", str(collab_agent_error(thread_id, CodexErr.fatal("boom"))))

    def test_thread_spawn_source_uses_parent_agent_path_or_root_like_rust(self) -> None:
        parent_id = ThreadId.new()
        root_child = thread_spawn_source(parent_id, SessionSource.exec(), 1, "worker", "task_1")
        self.assertEqual(root_child.type, "subagent")
        self.assertEqual(root_child.subagent_source.parent_thread_id, parent_id)
        self.assertEqual(root_child.subagent_source.depth, 1)
        self.assertEqual(root_child.subagent_source.agent_path, AgentPath.from_string("/root/task_1"))
        self.assertEqual(root_child.subagent_source.agent_role, "worker")

        parent_source = SessionSource.subagent(
            SubAgentSource.thread_spawn(
                parent_thread_id=parent_id,
                depth=1,
                agent_path=AgentPath.from_string("/root/parent"),
            )
        )
        nested = thread_spawn_source(parent_id, parent_source, 2, None, "child")
        self.assertEqual(nested.subagent_source.agent_path, AgentPath.from_string("/root/parent/child"))

        without_task = thread_spawn_source(parent_id, parent_source, 2)
        self.assertIsNone(without_task.subagent_source.agent_path)

        with self.assertRaisesRegex(FunctionCallError, "agent_name"):
            thread_spawn_source(parent_id, SessionSource.exec(), 1, None, "bad-name")

    def test_reject_full_fork_spawn_overrides_matches_rust_message(self) -> None:
        reject_full_fork_spawn_overrides(None, None, None)
        with self.assertRaisesRegex(FunctionCallError, "Full-history forked agents inherit"):
            reject_full_fork_spawn_overrides("worker", None, None)
        with self.assertRaises(TypeError):
            reject_full_fork_spawn_overrides(None, 1, None)

    def test_spawn_model_name_lookup_matches_rust_error(self) -> None:
        models = (
            _model_preset("gpt-a"),
            _model_preset("gpt-b"),
        )
        self.assertEqual(find_spawn_agent_model_name(models, "gpt-b"), "gpt-b")
        with self.assertRaisesRegex(FunctionCallError, r"Unknown model `gpt-c`.*Available models: gpt-a, gpt-b"):
            find_spawn_agent_model_name(models, "gpt-c")

    def test_spawn_reasoning_effort_validation_matches_rust_error(self) -> None:
        presets = (
            ReasoningEffortPreset(ReasoningEffort.LOW, "Low"),
            ReasoningEffortPreset(ReasoningEffort.HIGH, "High"),
        )
        validate_spawn_agent_reasoning_effort("gpt-a", presets, ReasoningEffort.HIGH)
        validate_spawn_agent_reasoning_effort("gpt-a", presets, "low")
        with self.assertRaisesRegex(
            FunctionCallError,
            r"Reasoning effort `medium` is not supported for model `gpt-a`. Supported reasoning efforts: low, high",
        ):
            validate_spawn_agent_reasoning_effort("gpt-a", presets, ReasoningEffort.MEDIUM)

    def test_spawn_service_tier_selection_matches_rust_candidate_order(self) -> None:
        model_info = _model_info_with_service_tiers("priority", "flex")
        self.assertIsNone(select_spawn_agent_service_tier("gpt-a", model_info))
        self.assertEqual(
            select_spawn_agent_service_tier(
                "gpt-a",
                model_info,
                config_service_tier="flex",
                requested_service_tier="priority",
                parent_service_tier="priority",
            ),
            "flex",
        )
        self.assertEqual(
            select_spawn_agent_service_tier(
                "gpt-a",
                model_info,
                parent_service_tier="priority",
            ),
            "priority",
        )
        self.assertIsNone(
            select_spawn_agent_service_tier(
                "gpt-a",
                model_info,
                config_service_tier="unsupported",
                parent_service_tier="also-unsupported",
            )
        )
        with self.assertRaisesRegex(
            FunctionCallError,
            r"Service tier `turbo` is not supported for model `gpt-a`. Supported service tiers: priority, flex",
        ):
            select_spawn_agent_service_tier("gpt-a", model_info, requested_service_tier="turbo")
        with self.assertRaisesRegex(
            FunctionCallError,
            r"Service tier `priority` is not supported for model `gpt-b`. Supported service tiers: none",
        ):
            select_spawn_agent_service_tier("gpt-b", _model_info_with_service_tiers(), requested_service_tier="priority")

    def test_apply_spawn_agent_overrides_disables_legacy_child_tools_at_depth_limit(self) -> None:
        features = Features().enable(Feature.COLLAB).enable(Feature.SPAWN_CSV)
        config = SimpleNamespace(agent_max_depth=2, features=features)

        apply_spawn_agent_overrides(config, 2)

        self.assertFalse(features.enabled(Feature.COLLAB))
        self.assertFalse(features.enabled(Feature.SPAWN_CSV))

    def test_apply_spawn_agent_overrides_keeps_tools_below_limit_or_for_multi_agent_v2(self) -> None:
        below = Features().enable(Feature.COLLAB).enable(Feature.SPAWN_CSV)
        apply_spawn_agent_overrides(SimpleNamespace(agent_max_depth=2, features=below), 1)
        self.assertTrue(below.enabled(Feature.COLLAB))
        self.assertTrue(below.enabled(Feature.SPAWN_CSV))

        v2 = Features().enable(Feature.COLLAB).enable(Feature.SPAWN_CSV).enable(Feature.MULTI_AGENT_V2)
        apply_spawn_agent_overrides(SimpleNamespace(agent_max_depth=2, features=v2), 2)
        self.assertTrue(v2.enabled(Feature.COLLAB))
        self.assertTrue(v2.enabled(Feature.SPAWN_CSV))

    def test_apply_spawn_agent_overrides_supports_mapping_feature_sets(self) -> None:
        features = {
            Feature.COLLAB.key(): True,
            Feature.SPAWN_CSV.key(): True,
            Feature.MULTI_AGENT_V2.key(): False,
        }
        apply_spawn_agent_overrides({"agent_max_depth": 1, "features": features}, 1)
        self.assertFalse(features[Feature.COLLAB.key()])
        self.assertFalse(features[Feature.SPAWN_CSV.key()])

    def test_json_text_falls_back_to_string_error_for_unserializable_values(self) -> None:
        text = tool_output_json_text({"bad": object()}, "wait_agent")
        self.assertIsInstance(json.loads(text), str)
        self.assertIn("failed to serialize wait_agent result", json.loads(text))


def _model_preset(model: str) -> ModelPreset:
    return ModelPreset(
        id=model,
        model=model,
        display_name=model,
        description="",
        default_reasoning_effort=ReasoningEffort.MEDIUM,
        supported_reasoning_efforts=(ReasoningEffortPreset(ReasoningEffort.MEDIUM, "Medium"),),
        is_default=False,
        upgrade=None,
        show_in_picker=True,
        availability_nux=None,
        supported_in_api=True,
    )


def _model_info_with_service_tiers(*ids: str):
    tiers = tuple(ModelServiceTier(tier_id, tier_id.title(), tier_id) for tier_id in ids)
    return type(
        "ModelInfoForTest",
        (),
        {
            "service_tiers": tiers,
            "supports_service_tier": lambda self, tier: any(service_tier.id == tier for service_tier in tiers),
        },
    )()


if __name__ == "__main__":
    unittest.main()
