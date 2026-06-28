"""Construction and initial wiring for chat-widget semantic models.

Rust ``constructor.rs`` initializes a very large ``ChatWidget`` struct.  This
Python port captures the module-local construction contract: model filtering,
header/collaboration initialization, transcript setup, bottom-pane parameter
wiring, and the post-construction sync calls.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

from .._porting import RustTuiModule
from .settings import CollaborationMode, CollaborationModeMask, ModeKind, SettingsConfig
from .transcript import TranscriptState

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::constructor",
    source="codex/codex-rs/tui/src/chatwidget/constructor.rs",
    status="complete",
)

__all__ = [
    "BottomPaneParams",
    "ChatWidgetInit",
    "CodexOpTarget",
    "ConstructedChatWidget",
    "PLACEHOLDERS",
    "RUST_MODULE",
    "SIDE_PLACEHOLDERS",
    "select_placeholder",
    "new_with_app_event",
    "new_with_op_target",
]


DEFAULT_MODEL_DISPLAY_NAME = "loading"
PLACEHOLDERS = (
    "Explain this codebase",
    "Summarize recent commits",
    "Implement {feature}",
    "Find and fix a bug in @filename",
    "Write tests for @filename",
    "Improve documentation in @filename",
    "Run /review on my current changes",
    "Use /skills to list available skills",
)
SIDE_PLACEHOLDERS = (
    "Check recently modified functions for compatibility",
    "How many files have been modified?",
    "Will this algorithm scale well?",
)


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
    skills: Optional[Any] = None


@dataclass
class ChatWidgetInit:
    config: SettingsConfig
    frame_requester: Any
    app_event_tx: Any
    workspace_command_runner: Any = None
    initial_user_message: Optional[Any] = None
    enhanced_keys_supported: bool = False
    has_chatgpt_account: bool = False
    model_catalog: Optional[Any] = None
    feedback: Optional[Any] = None
    is_first_run: bool = False
    status_account_display: Optional[Any] = None
    runtime_model_provider_base_url: Optional[str] = None
    initial_plan_type: Optional[Any] = None
    model: Optional[str] = None
    startup_tooltip_override: Optional[str] = None
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
    active_collaboration_mask: Optional[CollaborationModeMask]
    session_header: Any
    initial_user_message: Optional[Any]
    has_chatgpt_account: bool
    model_catalog: Optional[Any]
    status_account_display: Optional[Any]
    runtime_model_provider_base_url: Optional[str]
    plan_type: Optional[Any]
    normal_placeholder_text: str
    side_placeholder_text: str
    show_welcome_banner: bool
    startup_tooltip_override: Optional[str]
    current_cwd: Optional[Any]
    raw_output_mode: bool = False
    effective_service_tier: Optional[Any] = None
    current_terminal_info: Optional[Any] = None
    runtime_keymap: Optional[Any] = None
    copy_last_response_binding: Optional[Any] = None
    chat_keymap: Optional[Any] = None
    queued_message_edit_hint_binding: Optional[Any] = None
    skills_all: List[Any] = field(default_factory=list)
    skills_initial_state: Optional[Any] = None
    token_info: Optional[Any] = None
    rate_limit_snapshots_by_limit_id: Dict[Any, Any] = field(default_factory=dict)
    refreshing_status_outputs: List[Any] = field(default_factory=list)
    next_status_refresh_request_id: int = 0
    running_commands: Dict[Any, Any] = field(default_factory=dict)
    collab_agent_metadata: Dict[Any, Any] = field(default_factory=dict)
    pending_collab_spawn_requests: Dict[Any, Any] = field(default_factory=dict)
    suppressed_exec_calls: set = field(default_factory=set)
    unified_exec_processes: List[Any] = field(default_factory=list)
    thread_name: Optional[str] = None
    active_side_conversation: bool = False
    external_editor_state: str = "Closed"
    thread_id: Optional[Any] = None
    last_non_retry_error: Optional[Any] = None
    last_rendered_user_message_display: Optional[Any] = None
    calls: List[Tuple[str, Tuple[Any, ...]]] = field(default_factory=list)

    def __getattr__(self, name: str):
        def recorder(*args: Any) -> None:
            self.calls.append((name, args))

        return recorder


def new_with_app_event(
    common: ChatWidgetInit,
    *,
    factories: Optional[Dict[str, Callable[..., Any]]] = None,
) -> ConstructedChatWidget:
    return new_with_op_target(common, CodexOpTarget.APP_EVENT, factories=factories)


def new_with_op_target(
    common: ChatWidgetInit,
    codex_op_target: CodexOpTarget,
    *,
    factories: Optional[Dict[str, Callable[..., Any]]] = None,
) -> ConstructedChatWidget:
    factories = factories or {}
    model = common.model.strip() if isinstance(common.model, str) and common.model.strip() else None
    common.config.model = model
    prevent_idle_sleep = common.config.features.enabled("PreventIdleSleep")
    rng = factories.get("rng")
    placeholder = select_placeholder(PLACEHOLDERS, rng=rng)
    side_placeholder = select_placeholder(SIDE_PLACEHOLDERS, rng=rng)
    model_for_header = model or DEFAULT_MODEL_DISPLAY_NAME
    active_collaboration_mask = _initial_collaboration_mask(common.config, common.model_catalog, model)
    header_model = active_collaboration_mask.model if active_collaboration_mask and active_collaboration_mask.model else model_for_header
    current_collaboration_mode = CollaborationMode(mode=ModeKind.DEFAULT, model_value=header_model)
    active_cell = _placeholder_session_header_cell(common.config)
    bottom_pane_factory = factories.get("bottom_pane", _default_bottom_pane)
    session_header_factory = factories.get("session_header", _default_session_header)
    service_tier_factory = factories.get("effective_service_tier", _default_effective_service_tier)
    terminal_info_factory = factories.get("terminal_info", lambda: None)
    runtime_keymap_factory = factories.get("runtime_keymap", _default_runtime_keymap)
    pet_loader = factories.get("start_configured_pet_load_if_needed")
    runtime_keymap = runtime_keymap_factory(common.config)
    default_keymap = runtime_keymap_factory(None)
    copy_binding = _keymap_binding(runtime_keymap, default_keymap, "app", "copy")
    chat_keymap = _keymap_section(runtime_keymap, default_keymap, "chat")
    queued_binding = _keymap_binding(runtime_keymap, default_keymap, "chat", "edit_queued_message")
    if callable(pet_loader):
        pet_loader(common.config, True, common.frame_requester, common.app_event_tx)
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
        raw_output_mode=bool(getattr(common.config, "tui_raw_output_mode", False)),
        effective_service_tier=service_tier_factory(common.config, header_model, common.model_catalog),
        current_terminal_info=terminal_info_factory(),
        runtime_keymap=runtime_keymap,
        copy_last_response_binding=copy_binding,
        chat_keymap=chat_keymap,
        queued_message_edit_hint_binding=queued_binding,
    )
    widget.turn_lifecycle = {"prevent_idle_sleep": prevent_idle_sleep}
    _post_construct_sync(widget)
    return widget


def select_placeholder(placeholders: Tuple[str, ...], *, rng: Any = None) -> str:
    """Select a composer placeholder like Rust ``rand::Rng::random_range``."""

    if not placeholders:
        return ""
    if rng is not None:
        random_range = getattr(rng, "random_range", None)
        if callable(random_range):
            return placeholders[int(random_range(0, len(placeholders))) % len(placeholders)]
        randrange = getattr(rng, "randrange", None)
        if callable(randrange):
            return placeholders[int(randrange(len(placeholders))) % len(placeholders)]
        randint = getattr(rng, "randint", None)
        if callable(randint):
            return placeholders[int(randint(0, len(placeholders) - 1)) % len(placeholders)]
    return placeholders[random.randrange(len(placeholders))]


def _initial_collaboration_mask(
    config: SettingsConfig,
    model_catalog: Any,
    model_override: Optional[str],
) -> Optional[CollaborationModeMask]:
    mask_factory = getattr(config, "initial_collaboration_mask", None)
    if callable(mask_factory):
        return mask_factory(model_catalog, model_override)
    if model_override is None:
        return None
    return CollaborationModeMask(name=ModeKind.DEFAULT.display_name(), mode=ModeKind.DEFAULT, model=model_override)


def _placeholder_session_header_cell(config: SettingsConfig) -> dict[str, Any]:
    return {
        "kind": "placeholder_session_header",
        "model": DEFAULT_MODEL_DISPLAY_NAME,
        "cwd": getattr(config, "cwd", None),
    }


def _default_bottom_pane(params: BottomPaneParams) -> Any:
    return RecordingBottomPane(params)


def _default_session_header(model: str) -> Any:
    return {"model": model}


def _default_effective_service_tier(config: SettingsConfig, header_model: str, model_catalog: Any) -> Any:
    resolver = getattr(config, "effective_service_tier", None)
    if callable(resolver):
        return resolver(header_model, model_catalog)
    return getattr(config, "service_tier", None)


def _default_runtime_keymap(config: Optional[SettingsConfig]) -> Any:
    if config is not None:
        keymap = getattr(config, "tui_keymap", None)
        if keymap is not None:
            return keymap
    return {
        "app": {"copy": "ctrl+y"},
        "chat": {"edit_queued_message": "ctrl+e"},
    }


def _keymap_section(runtime_keymap: Any, default_keymap: Any, section: str) -> Any:
    value = _lookup(runtime_keymap, section)
    if value is not None:
        return value
    return _lookup(default_keymap, section)


def _keymap_binding(runtime_keymap: Any, default_keymap: Any, section: str, key: str) -> Any:
    section_value = _keymap_section(runtime_keymap, default_keymap, section)
    value = _lookup(section_value, key)
    if value is not None:
        return value
    return _lookup(_lookup(default_keymap, section), key)


def _lookup(value: Any, key: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _post_construct_sync(widget: ConstructedChatWidget) -> None:
    bottom = widget.bottom_pane
    _call_optional(widget, "prefetch_rate_limits")
    if widget.runtime_keymap is not None:
        _call_optional(bottom, "set_keymap_bindings", widget.runtime_keymap)
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
    _call_optional(bottom, "set_queued_message_edit_binding", widget.queued_message_edit_hint_binding)
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
    calls: List[Tuple[str, Tuple[Any, ...]]] = field(default_factory=list)

    def __getattr__(self, name: str):
        def recorder(*args: Any) -> None:
            self.calls.append((name, args))

        return recorder
