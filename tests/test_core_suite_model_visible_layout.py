"""Suite parity tests for ``codex-rs/core/tests/suite/model_visible_layout.rs``.

Rust snapshots this through full mocked Responses requests.  The Python port
checks the same model-visible contract at prompt/update boundaries: contextual
updates keep their roles and order, cwd-only AGENTS.md refreshes are not injected
by prompt assembly, resume-style history remains ordered, model override equality
suppresses model-switch developer text, and environment context renders subagent
lists.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pycodex.core.context import EnvironmentContext, EnvironmentContextEnvironment
from pycodex.core.context_manager.updates import (
    build_model_instructions_update_item,
    build_settings_update_items,
)
from pycodex.core.session.turn.prompt import build_turn_prompt, render_turn_user_instructions
from pycodex.features import Feature
from pycodex.protocol import (
    ApprovalsReviewer,
    AskForApproval,
    BaseInstructions,
    ContentItem,
    PermissionProfile,
    Personality,
    ResponseItem,
)


class _FeatureSet:
    def __init__(self, *features: object) -> None:
        self._features = set(features)

    def enabled(self, feature: object) -> bool:
        return feature in self._features


class _ApprovalCell:
    def __init__(self, value: object) -> None:
        self._value = value

    def value(self) -> object:
        return self._value


class _ModelMessages:
    def get_personality_message(self, personality: object) -> str:
        return f"personality update: {personality}"


class _Router:
    def model_visible_specs(self) -> list[dict[str, str]]:
        return []


def _text(item: ResponseItem) -> str:
    return "\n".join(content.text or "" for content in item.content)


def _previous_context(
    cwd: Path,
    *,
    personality: object = Personality.PRAGMATIC,
    model: str = "gpt-5.3-codex",
) -> SimpleNamespace:
    return SimpleNamespace(
        cwd=cwd,
        current_date="2026-06-11",
        timezone="Asia/Shanghai",
        network=None,
        permission_profile=lambda: PermissionProfile.read_only(),
        approval_policy=AskForApproval.NEVER,
        collaboration_mode="default",
        realtime_active=False,
        model=model,
        personality=personality,
    )


def _next_context(cwd: Path, *, personality: object = Personality.FRIENDLY) -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(
            include_environment_context=True,
            include_permissions_instructions=True,
            approvals_reviewer=ApprovalsReviewer.USER,
            include_collaboration_mode_instructions=False,
            experimental_realtime_start_instructions=None,
        ),
        cwd=cwd,
        current_date="2026-06-11",
        timezone="Asia/Shanghai",
        network=None,
        permission_profile=PermissionProfile.read_only(),
        approval_policy=_ApprovalCell(AskForApproval.ON_REQUEST),
        features=_FeatureSet(Feature.EXEC_PERMISSION_APPROVALS, Feature.REQUEST_PERMISSIONS_TOOL),
        collaboration_mode="default",
        realtime_active=False,
        model_info=SimpleNamespace(
            slug="gpt-5.3-codex",
            model_messages=_ModelMessages(),
            get_model_instructions=lambda personality: f"model instructions for {personality}",
        ),
        personality=personality,
    )


def test_snapshot_model_visible_layout_turn_overrides(tmp_path: Path) -> None:
    """Rust test: ``snapshot_model_visible_layout_turn_overrides``."""

    previous = _previous_context(tmp_path)
    next_context = _next_context(tmp_path / "PRETURN_CONTEXT_DIFF_CWD")
    items = build_settings_update_items(
        previous,
        SimpleNamespace(model="gpt-5.3-codex", realtime_active=False),
        next_context,
        personality_feature_enabled=True,
        shell=SimpleNamespace(name=lambda: "bash"),
    )

    assert [item.role for item in items] == ["developer", "user"]
    developer_text = _text(items[0])
    user_text = _text(items[1])
    assert "<permissions instructions>" in developer_text
    assert "personality update" in developer_text
    assert "<model_switch>" not in developer_text
    assert "<environment_context>" in user_text
    assert str(tmp_path / "PRETURN_CONTEXT_DIFF_CWD") in user_text


def test_snapshot_model_visible_layout_cwd_change_does_not_refresh_agents(tmp_path: Path) -> None:
    """Rust test: ``snapshot_model_visible_layout_cwd_change_does_not_refresh_agents``."""

    cwd_one = tmp_path / "agents_one"
    cwd_two = tmp_path / "agents_two"

    assert render_turn_user_instructions(SimpleNamespace(user_instructions=None, cwd=cwd_one)) is None
    assert render_turn_user_instructions(SimpleNamespace(user_instructions=None, cwd=cwd_two)) is None

    explicit = render_turn_user_instructions(SimpleNamespace(user_instructions="Turn one agents instructions.", cwd=cwd_one))
    assert explicit is not None
    assert "# AGENTS.md instructions for" in _text(explicit)
    assert "Turn one agents instructions." in _text(explicit)


def test_snapshot_model_visible_layout_resume_with_personality_change(tmp_path: Path) -> None:
    """Rust test: ``snapshot_model_visible_layout_resume_with_personality_change``."""

    recorded_user = ResponseItem.message("user", (ContentItem.input_text("seed resume history"),))
    recorded_assistant = ResponseItem.message("assistant", (ContentItem.output_text("recorded before resume"),))
    previous = _previous_context(tmp_path, personality=Personality.PRAGMATIC, model="gpt-5.2")
    next_context = _next_context(tmp_path / "PRETURN_CONTEXT_DIFF_CWD", personality=Personality.FRIENDLY)
    update_items = build_settings_update_items(
        previous,
        SimpleNamespace(model="gpt-5.2", realtime_active=False),
        next_context,
        personality_feature_enabled=True,
        shell=SimpleNamespace(name=lambda: "bash"),
    )
    resumed_user = ResponseItem.message("user", (ContentItem.input_text("resume and change personality"),))

    prompt = build_turn_prompt(
        [recorded_user, recorded_assistant, *update_items, resumed_user],
        _Router(),
        SimpleNamespace(personality=Personality.FRIENDLY),
        BaseInstructions("base"),
        has_current_user_input=True,
    )

    assert [item.role for item in prompt.input] == ["user", "assistant", "developer", "user", "user"]
    assert prompt.personality == Personality.FRIENDLY
    assert "<model_switch>" in _text(prompt.input[2])
    assert "personality update" not in _text(prompt.input[2])


def test_snapshot_model_visible_layout_resume_override_matches_rollout_model(tmp_path: Path) -> None:
    """Rust test: ``snapshot_model_visible_layout_resume_override_matches_rollout_model``."""

    previous_turn_settings = SimpleNamespace(model="gpt-5.2", realtime_active=False)
    next_context = _next_context(tmp_path, personality=Personality.PRAGMATIC)
    next_context.model_info.slug = "gpt-5.2"

    assert build_model_instructions_update_item(previous_turn_settings, next_context) is None


def test_snapshot_model_visible_layout_environment_context_includes_one_subagent() -> None:
    """Rust test: ``snapshot_model_visible_layout_environment_context_includes_one_subagent``."""

    context = EnvironmentContext.new(
        (EnvironmentContextEnvironment.legacy("/tmp/example", "bash"),),
        subagents="- agent-1: Atlas",
    )
    text = _text(context.into_response_item())

    assert "<subagents>" in text
    assert "    - agent-1: Atlas" in text
    assert "</subagents>" in text


def test_snapshot_model_visible_layout_environment_context_includes_two_subagents() -> None:
    """Rust test: ``snapshot_model_visible_layout_environment_context_includes_two_subagents``."""

    context = EnvironmentContext.new(
        (EnvironmentContextEnvironment.legacy("/tmp/example", "bash"),),
        subagents="- agent-1: Atlas\n- agent-2: Juniper",
    )
    text = _text(context.into_response_item())

    assert "    - agent-1: Atlas" in text
    assert "    - agent-2: Juniper" in text
