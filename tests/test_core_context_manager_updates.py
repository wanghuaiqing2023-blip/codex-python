"""Parity tests for ``codex-rs/core/src/context_manager/updates.rs``."""

from pathlib import Path
from types import SimpleNamespace

from pycodex.core.context import (
    CollaborationModeInstructions,
    ModelSwitchInstructions,
    PersonalitySpecInstructions,
    RealtimeEndInstructions,
    RealtimeStartInstructions,
)
from pycodex.core.context_manager.updates import (
    build_collaboration_mode_update_item,
    build_contextual_user_message,
    build_developer_update_item,
    build_environment_update_item,
    build_model_instructions_update_item,
    build_personality_update_item,
    build_permissions_update_item,
    build_realtime_update_item,
    build_settings_update_items,
    build_text_message,
    personality_message_for,
)
from pycodex.protocol import (
    ApprovalsReviewer,
    AskForApproval,
    CollaborationMode,
    ContentItem,
    ModeKind,
    NetworkSandboxPolicy,
    PermissionProfile,
    Personality,
    ResponseItem,
    SandboxPolicy,
    Settings,
    TurnContextItem,
)


class _ModelInfo:
    slug = "gpt-next"
    model_messages = None

    def get_model_instructions(self, personality: object = None) -> str:
        return "next model instructions"


class _ModelMessages:
    def get_personality_message(self, personality: object = None) -> str | None:
        if personality == Personality.PRAGMATIC:
            return "Be direct and practical."
        if personality == Personality.FRIENDLY:
            return "Be warm."
        return ""


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        include_environment_context=False,
        include_permissions_instructions=False,
        include_collaboration_mode_instructions=False,
        experimental_realtime_start_instructions=None,
        approvals_reviewer=ApprovalsReviewer.USER,
    )


def _next_context(*, realtime_active: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        config=_config(),
        cwd=Path("/repo"),
        model_info=_ModelInfo(),
        approval_policy=AskForApproval.ON_REQUEST,
        permission_profile=PermissionProfile.read_only(),
        personality=None,
        realtime_active=realtime_active,
    )


def test_build_text_message_returns_none_for_empty_sections() -> None:
    """Rust source contract: ``build_text_message`` emits no message for empty sections."""

    assert build_text_message("developer", []) is None
    assert build_developer_update_item(()) is None
    assert build_contextual_user_message(()) is None


def test_build_text_message_maps_sections_to_input_text_content() -> None:
    """Rust source contract: text update helpers build role messages with one input_text per section."""

    item = build_text_message("developer", ["first", "second"])

    assert item == ResponseItem.message(
        "developer",
        (
            ContentItem.input_text("first"),
            ContentItem.input_text("second"),
        ),
    )


def test_realtime_update_uses_previous_turn_settings_when_no_reference_context() -> None:
    """Rust source contract: previous realtime turn state can emit an inactive update without reference context."""

    previous_turn_settings = SimpleNamespace(realtime_active=True)

    assert build_realtime_update_item(None, previous_turn_settings, _next_context(realtime_active=False)) == (
        RealtimeEndInstructions.new("inactive").render()
    )


def test_realtime_update_starts_when_reference_context_was_inactive() -> None:
    """Rust source contract: inactive-to-active realtime transition emits start instructions."""

    previous = SimpleNamespace(realtime_active=False)

    assert build_realtime_update_item(previous, None, _next_context(realtime_active=True)) == RealtimeStartInstructions().render()


def test_model_instructions_update_requires_model_change_and_non_empty_instructions() -> None:
    """Rust source contract: model switch instructions are emitted only when model slug changes."""

    assert build_model_instructions_update_item(SimpleNamespace(model="gpt-prev"), _next_context()) == (
        ModelSwitchInstructions.new("next model instructions").render()
    )
    assert build_model_instructions_update_item(SimpleNamespace(model="gpt-next"), _next_context()) is None


def test_personality_update_requires_same_model_changed_personality_and_message() -> None:
    """Rust source contract: personality updates do not cross model changes and skip empty messages."""

    model_info = SimpleNamespace(slug="gpt-next", model_messages=_ModelMessages())
    next_context = SimpleNamespace(model_info=model_info, personality=Personality.PRAGMATIC)

    assert personality_message_for(model_info, Personality.PRAGMATIC) == "Be direct and practical."
    assert build_personality_update_item(
        SimpleNamespace(model="gpt-next", personality=Personality.FRIENDLY),
        next_context,
        True,
    ) == PersonalitySpecInstructions.new("Be direct and practical.").render()
    assert build_personality_update_item(
        SimpleNamespace(model="gpt-prev", personality=Personality.FRIENDLY),
        next_context,
        True,
    ) is None
    assert build_personality_update_item(
        SimpleNamespace(model="gpt-next", personality=Personality.PRAGMATIC),
        next_context,
        True,
    ) is None
    assert build_personality_update_item(
        SimpleNamespace(model="gpt-next", personality=Personality.FRIENDLY),
        SimpleNamespace(model_info=model_info, personality=Personality.NONE),
        True,
    ) is None
    assert build_personality_update_item(
        SimpleNamespace(model="gpt-next", personality=Personality.FRIENDLY),
        next_context,
        False,
    ) is None


def test_collaboration_mode_update_skips_empty_developer_instructions() -> None:
    """Rust source contract: changed collaboration mode emits only non-empty developer instructions."""

    previous = SimpleNamespace(
        collaboration_mode=CollaborationMode(
            ModeKind.DEFAULT,
            Settings("gpt-prev", developer_instructions="old instructions"),
        )
    )
    next_context = SimpleNamespace(
        config=SimpleNamespace(include_collaboration_mode_instructions=True),
        collaboration_mode=CollaborationMode(
            ModeKind.PLAN,
            Settings("gpt-next", developer_instructions="Plan before editing."),
        ),
    )
    empty_next_context = SimpleNamespace(
        config=SimpleNamespace(include_collaboration_mode_instructions=True),
        collaboration_mode=CollaborationMode(
            ModeKind.PLAN,
            Settings("gpt-next", developer_instructions=""),
        ),
    )

    assert build_collaboration_mode_update_item(previous, next_context) == (
        CollaborationModeInstructions.from_collaboration_mode(next_context.collaboration_mode).render()
    )
    assert build_collaboration_mode_update_item(previous, empty_next_context) is None
    assert build_collaboration_mode_update_item(None, next_context) is None


def test_environment_update_item_emits_contextual_user_diff_when_context_changes() -> None:
    """Rust source contract: environment updates emit only when the context differs except for shell."""

    previous = TurnContextItem(
        cwd=Path("/repo/old"),
        approval_policy=AskForApproval.ON_REQUEST,
        sandbox_policy=SandboxPolicy.read_only(),
        model="gpt-prev",
        current_date="2026-06-07",
        timezone="Asia/Shanghai",
    )
    next_context = _next_context()
    next_context.config.include_environment_context = True
    next_context.cwd = Path("/repo/new")
    next_context.current_date = "2026-06-07"
    next_context.timezone = "Asia/Shanghai"

    item = build_environment_update_item(previous, next_context, SimpleNamespace(name=lambda: "pwsh"))

    assert item is not None
    assert item.role == "user"
    assert len(item.content) == 1
    assert "<environment_context>" in item.content[0].text
    assert f"<cwd>{Path('/repo/new')}</cwd>" in item.content[0].text
    assert build_environment_update_item(None, next_context, "pwsh") is None


def test_permissions_update_item_emits_when_profile_or_policy_changes() -> None:
    """Rust source contract: permissions updates compare previous profile and approval policy."""

    previous = TurnContextItem(
        cwd=Path("/repo"),
        approval_policy=AskForApproval.ON_REQUEST,
        sandbox_policy=SandboxPolicy.read_only(),
        permission_profile_value=PermissionProfile.read_only(),
        model="gpt-prev",
    )
    next_context = _next_context()
    next_context.config.include_permissions_instructions = True
    next_context.approval_policy = AskForApproval.NEVER
    next_context.permission_profile = PermissionProfile.workspace_write(
        (Path("/repo"),),
        network=NetworkSandboxPolicy.RESTRICTED,
    )
    next_context.features = SimpleNamespace(enabled=lambda _feature: False)

    rendered = build_permissions_update_item(previous, next_context, None)

    assert rendered is not None
    assert "<permissions instructions>" in rendered
    assert "Do not provide the `sandbox_permissions`" in rendered
    assert build_permissions_update_item(None, next_context, None) is None
    next_context.approval_policy = AskForApproval.ON_REQUEST
    next_context.permission_profile = PermissionProfile.read_only()
    assert build_permissions_update_item(previous, next_context, None) is None


def test_build_settings_update_items_orders_developer_before_contextual_user() -> None:
    """Rust source contract: developer updates precede contextual user updates."""

    contextual_user = ResponseItem.message("user", (ContentItem.input_text("<environment_context>diff</environment_context>"),))

    items = build_settings_update_items(
        None,
        SimpleNamespace(model="gpt-prev", realtime_active=None),
        _next_context(realtime_active=True),
        contextual_user_message=contextual_user,
        personality_feature_enabled=False,
    )

    assert len(items) == 2
    assert items[0].role == "developer"
    assert items[0].content == (
        ContentItem.input_text(ModelSwitchInstructions.new("next model instructions").render()),
        ContentItem.input_text(RealtimeStartInstructions().render()),
    )
    assert items[1] is contextual_user
