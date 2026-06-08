from __future__ import annotations

import unittest
from types import SimpleNamespace

from pycodex.core.review_prompts import ResolvedReviewRequest
from pycodex.core.session.review import (
    review_config_for_review,
    review_features_for_review,
    spawn_review_thread,
)
from pycodex.core.tasks.review import ReviewTask
from pycodex.features import Feature, Features
from pycodex.protocol import ReviewRequest, ReviewTarget, WebSearchMode


class ModelsManager:
    def __init__(self) -> None:
        self.get_model_info_calls: list[tuple[object, object]] = []
        self.list_models_calls = 0

    async def get_model_info(self, model: str, config: object) -> object:
        self.get_model_info_calls.append((model, config))
        return SimpleNamespace(
            slug=model,
            default_reasoning_summary="auto",
            truncation_policy="tokens",
        )

    async def list_models(self, refresh_strategy: object = None) -> tuple[str, ...]:
        self.list_models_calls += 1
        return ("gpt-review", "gpt-parent")


class WebSearchModeCell:
    def __init__(self) -> None:
        self.values: list[object] = []

    def set(self, value: object) -> None:
        self.values.append(value)


class SessionReviewTests(unittest.IsolatedAsyncioTestCase):
    def test_review_features_disable_review_disallowed_tools(self) -> None:
        # Rust source: session/review.rs disables WebSearchRequest, WebSearchCached, and Goals.
        features = Features.with_defaults()
        features.enable(Feature.WEB_SEARCH_REQUEST)
        features.enable(Feature.WEB_SEARCH_CACHED)
        features.enable(Feature.GOALS)

        review_features = review_features_for_review(features)

        self.assertFalse(review_features.enabled(Feature.WEB_SEARCH_REQUEST))
        self.assertFalse(review_features.enabled(Feature.WEB_SEARCH_CACHED))
        self.assertFalse(review_features.enabled(Feature.GOALS))
        self.assertTrue(features.enabled(Feature.WEB_SEARCH_REQUEST))

    def test_review_config_sets_model_features_and_disables_web_search(self) -> None:
        # Rust source: per_turn_config.model, features, and web_search_mode are overridden for review.
        web_search = WebSearchModeCell()
        config = SimpleNamespace(model=None, features=None, web_search_mode=web_search)
        features = Features()

        per_turn = review_config_for_review(config, "gpt-review", features)

        self.assertIsNot(per_turn, config)
        self.assertEqual(per_turn.model, "gpt-review")
        self.assertIs(per_turn.features, features)
        self.assertEqual(config.web_search_mode.values, [])
        self.assertEqual(per_turn.web_search_mode.values, [WebSearchMode.DISABLED])

    async def test_spawn_review_thread_uses_review_model_and_sends_entered_review_mode(self) -> None:
        # Rust source: spawn_review_thread builds a review child turn, spawns ReviewTask, then emits EnteredReviewMode.
        models_manager = ModelsManager()
        events: list[tuple[object, object]] = []
        spawned: list[tuple[object, object, object]] = []
        metadata_calls: list[str] = []

        class MetadataState:
            def spawn_git_enrichment_task(self) -> None:
                metadata_calls.append("spawn_git_enrichment_task")

        async def spawn_task(turn_context: object, input_items: object, task: object) -> None:
            spawned.append((turn_context, input_items, task))

        async def send_event(turn_context: object, msg: object) -> None:
            events.append((turn_context, msg))

        parent = SimpleNamespace(
            sub_id="parent-turn",
            model_info=SimpleNamespace(slug="gpt-parent"),
            cwd="C:/repo",
            compact_prompt="compact",
            collaboration_mode="default",
            personality=None,
            approval_policy="on-request",
            network=None,
            turn_metadata_state=MetadataState(),
            goal_tools_enabled=lambda: True,
        )
        config = SimpleNamespace(
            review_model="gpt-review",
            model=None,
            features=Features.with_defaults(),
            ephemeral=False,
            web_search_mode=WebSearchMode.CACHED,
            to_models_manager_config=lambda: {"catalog": True},
        )
        sess = SimpleNamespace(
            features=config.features,
            services=SimpleNamespace(models_manager=models_manager),
            spawn_task=spawn_task,
            send_event=send_event,
        )
        resolved = ResolvedReviewRequest(
            target=ReviewTarget.custom("look carefully"),
            prompt="review prompt text",
            user_facing_hint="custom review",
        )

        child = await spawn_review_thread(sess, config, parent, "review-sub", resolved)

        self.assertEqual(models_manager.get_model_info_calls, [("gpt-review", {"catalog": True})])
        self.assertEqual(models_manager.list_models_calls, 1)
        self.assertEqual(child.sub_id, "review-sub")
        self.assertEqual(child.model_info.slug, "gpt-review")
        self.assertIsNone(child.developer_instructions)
        self.assertIsNone(child.user_instructions)
        self.assertIsNone(child.final_output_json_schema)
        self.assertTrue(child.goal_tools_supported)
        self.assertEqual(child.available_models, ("gpt-review", "gpt-parent"))
        self.assertFalse(child.features.enabled(Feature.WEB_SEARCH_REQUEST))
        self.assertFalse(child.features.enabled(Feature.WEB_SEARCH_CACHED))
        self.assertFalse(child.features.enabled(Feature.GOALS))
        self.assertEqual(metadata_calls, ["spawn_git_enrichment_task"])

        self.assertEqual(len(spawned), 1)
        self.assertIs(spawned[0][0], child)
        self.assertIsInstance(spawned[0][2], ReviewTask)
        input_item = spawned[0][1][0].items[0]
        self.assertEqual(input_item.type, "text")
        self.assertEqual(input_item.text, "review prompt text")
        self.assertEqual(input_item.text_elements, ())

        self.assertEqual(len(events), 1)
        self.assertIs(events[0][0], child)
        self.assertEqual(events[0][1].type, "entered_review_mode")
        self.assertEqual(
            events[0][1].payload,
            ReviewRequest(ReviewTarget.custom("look carefully"), user_facing_hint="custom review"),
        )

    async def test_spawn_review_thread_falls_back_to_parent_model_and_disables_goals_for_ephemeral_config(self) -> None:
        models_manager = ModelsManager()
        spawned: list[tuple[object, object, object]] = []
        events: list[tuple[object, object]] = []
        parent = SimpleNamespace(
            model_info=SimpleNamespace(slug="gpt-parent"),
            goal_tools_enabled=lambda: True,
            turn_metadata_state=SimpleNamespace(spawn_git_enrichment_task=lambda: None),
        )
        config = SimpleNamespace(
            review_model=None,
            features=Features.with_defaults(),
            ephemeral=True,
            web_search_mode=WebSearchMode.LIVE,
        )
        sess = SimpleNamespace(
            features=config.features,
            services=SimpleNamespace(models_manager=models_manager),
            spawn_task=lambda *args: spawned.append(args),
            send_event=lambda *args: events.append(args),
        )
        resolved = ResolvedReviewRequest(
            target=ReviewTarget.uncommitted_changes(),
            prompt="review current changes",
            user_facing_hint="current changes",
        )

        child = await spawn_review_thread(sess, config, parent, "sub", resolved)

        self.assertEqual(models_manager.get_model_info_calls[0][0], "gpt-parent")
        self.assertFalse(child.goal_tools_supported)
        self.assertEqual(child.config.model, "gpt-parent")
        self.assertEqual(child.config.web_search_mode, WebSearchMode.DISABLED)


if __name__ == "__main__":
    unittest.main()
