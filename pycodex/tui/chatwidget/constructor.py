"""Construction and initial wiring for chat-widget semantic models.

Rust ``constructor.rs`` initializes a very large ``ChatWidget`` struct.  This
Python port captures the module-local construction contract: model filtering,
header/collaboration initialization, transcript setup, bottom-pane parameter
wiring, and the post-construction sync calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol

from .._porting import RustTuiModule
from .settings import CollaborationMode, CollaborationModeMask, ModeKind, SettingsConfig
from .transcript import TranscriptState

RUST_MODULE = RustTuiModule(crate="codex-tui", module="chatwidget::constructor", source="codex/codex-rs/tui/src/chatwidget/constructor.rs")

__all__ = [
    "BottomPaneParams",
    "ChatWidgetInit",
    "CodexOpTarget",
    "ConstructedChatWidget",
    "RUST_MODULE",
    "new_with_app_event",
    "new_with_op_target",
]


DEFAULT_MODEL_DISPLAY_NAME = "Default"
PLACEHOLDERS = ("Ask Codex",)
SIDE_PLACEHOLDERS = ("Ask Codex in side conversation",)


class CodexOpTarget(str, Enum):
    APP_EVENT = "AppEvent"
    DIRECT = "Direct"


@dataclass
class BottomPaneParams:
    frame_requester: Any
    app_event_tx: Any
    has_input_focus: bool
    enhanced_keys_supported: bool
    placeholder_text: str
    disable_paste_burst: bool
    animations_enabled: bool
    skills: Any | None = None


@dataclass
class ChatWidgetInit:
    config: SettingsConfig
    frame_requester: Any
    app_event_tx: Any
    workspace_command_runner: Any = None
    initial_user_message: Any | None = None
    enhanced_keys_supported: bool = False
    has_chatgpt_account: bool = False
    model_catalog: Any | None = None
    feedback: Any | None = None
    is_first_run: bool = False
    status_account_display: Any | None = None
    runtime_model_provider_base_url: str | None = None
    initial_plan_type: Any | None = None
    model: str | None = None
    startup_tooltip_override: str | None = None
    status_line_invalid_items_warned: bool = False
    terminal_title_invalid_items_warned: bool = False
    session_telemetry: Any | None = None


@dataclass
class ConstructedChatWidget:
    app_event_tx: Any
    frame_requester: Any
    codex_op_target: CodexOpTarget
    bottom_pane: Any
    transcript: TranscriptState
    config: SettingsConfig
    current_collaboration_mode: CollaborationMode
    active_collaboration_mask: CollaborationModeMask | None
    session_header: Any
    initial_user_message: Any | None
    has_chatgpt_account: bool
    model_catalog: Any | None
    status_account_display: Any | None
    runtime_model_provider_base_url: str | None
    plan_type: Any | None
    normal_placeholder_text: str
    side_placeholder_text: str
    show_welcome_banner: bool
    startup_tooltip_override: str | None
    current_cwd: Any | None
    external_editor_state: str = "Closed"
    thread_id: Any | None = None
    last_non_retry_error: Any | None = None
    last_rendered_user_message_display: Any | None = None
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)

    def __getattr__(self, name: str):
        def recorder(*args: Any) -> None:
            self.calls.append((name, args))

        return recorder


def new_with_app_event(common: ChatWidgetInit, *, factories: dict[str, Callable[..., Any]] | None = None) -> ConstructedChatWidget:
    return new_with_op_target(common, CodexOpTarget.APP_EVENT, factories=factories)


def new_with_op_target(
    common: ChatWidgetInit,
    codex_op_target: CodexOpTarget,
    *,
    factories: dict[str, Callable[..., Any]] | None = None,
) -> ConstructedChatWidget:
    factories = factories or {}
    model = common.model.strip() if isinstance(common.model, str) and common.model.strip() else None
    common.config.model = model
    prevent_idle_sleep = common.config.features.enabled("PreventIdleSleep")
    placeholder = PLACEHOLDERS[0]
    side_placeholder = SIDE_PLACEHOLDERS[0]
    model_for_header = model or DEFAULT_MODEL_DISPLAY_NAME
    active_collaboration_mask = _initial_collaboration_mask(common.config, common.model_catalog, model)
    header_model = active_collaboration_mask.model if active_collaboration_mask and active_collaboration_mask.model else model_for_header
    current_collaboration_mode = CollaborationMode(mode=ModeKind.DEFAULT, model_value=header_model)
    active_cell = _placeholder_session_header_cell(common.config)
    bottom_pane_factory = factories.get("bottom_pane", _default_bottom_pane)
    session_header_factory = factories.get("session_header", _default_session_header)
    bottom_pane = bottom_pane_factory(
        BottomPaneParams(
            frame_requester=common.frame_requester,
            app_event_tx=common.app_event_tx,
            has_input_focus=True,
            enhanced_keys_supported=common.enhanced_keys_supported,
            placeholder_text=placeholder,
            disable_paste_burst=bool(getattr(common.config, "disable_paste_burst", False)),
            animations_enabled=bool(getattr(common.config, "animations", False)),
            skills=None,
        )
    )
    widget = ConstructedChatWidget(
        app_event_tx=common.app_event_tx,
        frame_requester=common.frame_requester,
        codex_op_target=codex_op_target,
        bottom_pane=bottom_pane,
        transcript=TranscriptState.new(active_cell),
        config=common.config,
        current_collaboration_mode=current_collaboration_mode,
        active_collaboration_mask=active_collaboration_mask,
        session_header=session_header_factory(header_model),
        initial_user_message=common.initial_user_message,
        has_chatgpt_account=common.has_chatgpt_account,
        model_catalog=common.model_catalog,
        status_account_display=common.status_account_display,
        runtime_model_provider_base_url=common.runtime_model_provider_base_url,
        plan_type=common.initial_plan_type,
        normal_placeholder_text=placeholder,
        side_placeholder_text=side_placeholder,
        show_welcome_banner=common.is_first_run,
        startup_tooltip_override=common.startup_tooltip_override,
        current_cwd=getattr(common.config, "cwd", None),
    )
    widget.turn_lifecycle = {"prevent_idle_sleep": prevent_idle_sleep}
    _post_construct_sync(widget)
    return widget


def _initial_collaboration_mask(config: SettingsConfig, model_catalog: Any, model_override: str | None) -> CollaborationModeMask | None:
    mask_factory = getattr(config, "initial_collaboration_mask", None)
    if callable(mask_factory):
        return mask_factory(model_catalog, model_override)
    if model_override is None:
        return None
    return CollaborationModeMask(name=ModeKind.DEFAULT.display_name(), mode=ModeKind.DEFAULT, model=model_override)


def _placeholder_session_header_cell(config: SettingsConfig) -> dict[str, Any]:
    return {"kind": "placeholder_session_header", "cwd": getattr(config, "cwd", None)}


def _default_bottom_pane(params: BottomPaneParams) -> Any:
    return RecordingBottomPane(params)


def _default_session_header(model: str) -> Any:
    return {"model": model}


def _post_construct_sync(widget: ConstructedChatWidget) -> None:
    bottom = widget.bottom_pane
    _call_optional(bottom, "set_vim_enabled", bool(getattr(widget.config, "tui_vim_mode_default", False)))
    _call_optional(bottom, "set_realtime_conversation_enabled", _call_optional(widget, "realtime_conversation_enabled", default=False))
    _call_optional(bottom, "set_audio_device_selection_enabled", _call_optional(widget, "realtime_audio_device_selection_enabled", default=False))
    _call_optional(bottom, "set_status_line_enabled", bool(_call_optional(widget, "configured_status_line_items", default=[])))
    _call_optional(bottom, "set_collaboration_modes_enabled", True)
    _call_optional(widget, "sync_service_tier_commands")
    _call_optional(widget, "sync_personality_command_enabled")
    _call_optional(widget, "sync_plugins_command_enabled")
    _call_optional(widget, "sync_goal_command_enabled")
    _call_optional(widget, "sync_mentions_v2_enabled")
    _call_optional(widget, "update_collaboration_mode_indicator")
    _call_optional(bottom, "set_connectors_enabled", _call_optional(widget, "connectors_enabled", default=False))
    _call_optional(widget, "refresh_status_surfaces")


def _call_optional(target: Any, method_name: str, *args: Any, default: Any = None) -> Any:
    method = getattr(target, method_name, None)
    if method is None:
        return default
    return method(*args)


@dataclass
class RecordingBottomPane:
    params: BottomPaneParams
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)

    def __getattr__(self, name: str):
        def recorder(*args: Any) -> None:
            self.calls.append((name, args))

        return recorder
