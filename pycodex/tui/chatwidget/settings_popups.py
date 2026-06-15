"""Settings-adjacent popup surfaces for chat widgets.

Rust ``settings_popups.rs`` builds ratatui selection/toggle views for theme,
personality, realtime audio, and experimental feature settings.  This Python
port returns semantic DTOs and declarative action records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::settings_popups",
    source="codex/codex-rs/tui/src/chatwidget/settings_popups.rs",
    status="complete",
)

__all__ = [
    "AppEvent",
    "ExperimentalFeatureItem",
    "ExperimentalFeaturesView",
    "Personality",
    "RealtimeAudioDeviceKind",
    "RUST_MODULE",
    "SelectionItem",
    "SelectionViewParams",
    "open_experimental_popup",
    "open_personality_popup",
    "open_realtime_audio_device_selection",
    "open_realtime_audio_device_selection_with_names",
    "open_realtime_audio_popup",
    "open_realtime_audio_restart_prompt",
    "open_theme_picker",
    "personality_description",
    "personality_label",
]


class Personality(str, Enum):
    NONE = "None"
    FRIENDLY = "Friendly"
    PRAGMATIC = "Pragmatic"


class RealtimeAudioDeviceKind(str, Enum):
    MICROPHONE = "Microphone"
    SPEAKER = "Speaker"

    def title(self) -> str:
        return "Microphone" if self is RealtimeAudioDeviceKind.MICROPHONE else "Speaker"

    def noun(self) -> str:
        return "microphone" if self is RealtimeAudioDeviceKind.MICROPHONE else "speaker"


@dataclass(frozen=True)
class AppEvent:
    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SelectionItem:
    name: str
    description: Optional[str] = None
    is_current: bool = False
    is_disabled: bool = False
    disabled_reason: Optional[str] = None
    actions: List[AppEvent] = field(default_factory=list)
    dismiss_on_select: bool = False


@dataclass
class SelectionViewParams:
    title: Optional[str] = None
    subtitle: Optional[str] = None
    footer_hint: Optional[str] = "Enter to select, Esc to cancel"
    items: List[SelectionItem] = field(default_factory=list)
    header: Optional[str] = None


@dataclass(frozen=True)
class ExperimentalFeatureItem:
    feature: Any
    name: str
    description: str
    enabled: bool


@dataclass(frozen=True)
class ExperimentalFeaturesView:
    features: Tuple[ExperimentalFeatureItem, ...]


class SettingsPopupsWidget:
    config: Any
    bottom_pane: Any


def open_theme_picker(widget: Any) -> Any:
    """Build and show theme picker params.

    If the widget exposes ``build_theme_picker_params`` we delegate to it so a
    real UI can supply the full theme picker.  Otherwise a semantic placeholder
    preserving current theme and width inputs is returned.
    """

    current_theme = getattr(widget.config, "tui_theme", None)
    terminal_width = _last_width(widget)
    builder = getattr(widget, "build_theme_picker_params", None)
    if builder is not None:
        params = builder(current_theme, None, terminal_width)
    else:
        params = SelectionViewParams(
            title="Theme",
            subtitle="Choose a syntax theme.",
            items=[
                SelectionItem(
                    name=current_theme or "Default",
                    description="Current theme",
                    is_current=True,
                )
            ],
        )
    widget.bottom_pane.show_selection_view(params)
    return params


def open_personality_popup(widget: Any) -> Optional[SelectionViewParams]:
    if not widget.is_session_configured():
        widget.add_info_message(
            "Personality selection is disabled until startup completes.",
            None,
        )
        return None
    if not widget.current_model_supports_personality():
        current_model = widget.current_model()
        widget.add_error_message(
            f"Current model ({current_model}) doesn't support personalities. Try /model to pick a different model."
        )
        return None
    return open_personality_popup_for_current_model(widget)


def open_personality_popup_for_current_model(widget: Any) -> SelectionViewParams:
    current_personality = getattr(widget.config, "personality", None) or Personality.FRIENDLY
    current_personality = _personality(current_personality)
    supports_personality = widget.current_model_supports_personality()
    items = []
    for personality in (Personality.FRIENDLY, Personality.PRAGMATIC):
        items.append(
            SelectionItem(
                name=personality_label(personality),
                description=personality_description(personality),
                is_current=current_personality is personality,
                is_disabled=not supports_personality,
                actions=[
                    AppEvent("CodexOp", {"op": "override_turn_context", "personality": personality}),
                    AppEvent("UpdatePersonality", {"personality": personality}),
                    AppEvent("PersistPersonalitySelection", {"personality": personality}),
                ],
                dismiss_on_select=True,
            )
        )
    params = SelectionViewParams(
        header="Select Personality\nChoose a communication style for Codex.",
        items=items,
    )
    widget.bottom_pane.show_selection_view(params)
    return params


def open_realtime_audio_popup(widget: Any) -> SelectionViewParams:
    items = []
    for kind in (RealtimeAudioDeviceKind.MICROPHONE, RealtimeAudioDeviceKind.SPEAKER):
        items.append(
            SelectionItem(
                name=kind.title(),
                description=f"Current: {widget.current_realtime_audio_selection_label(kind)}",
                actions=[AppEvent("OpenRealtimeAudioDeviceSelection", {"kind": kind})],
                dismiss_on_select=True,
            )
        )
    params = SelectionViewParams(
        title="Settings",
        subtitle="Configure settings for Codex.",
        items=items,
    )
    widget.bottom_pane.show_selection_view(params)
    return params


def open_realtime_audio_device_selection(
    widget: Any,
    kind: Union[RealtimeAudioDeviceKind, str],
    list_device_names: Optional[Callable[[RealtimeAudioDeviceKind], Iterable[str]]] = None,
    linux_noop: bool = False,
) -> Optional[SelectionViewParams]:
    kind = _audio_kind(kind)
    if linux_noop:
        return None
    if list_device_names is None:
        list_device_names = getattr(widget, "list_realtime_audio_device_names", None)
    if list_device_names is None:
        raise NotImplementedError(
            "open_realtime_audio_device_selection requires a list_realtime_audio_device_names provider"
        )
    try:
        device_names = list(list_device_names(kind))
    except Exception as exc:
        widget.add_error_message(f"Failed to load realtime {kind.noun()} devices: {exc}")
        return None
    return open_realtime_audio_device_selection_with_names(widget, kind, device_names)


def open_realtime_audio_device_selection_with_names(
    widget: Any,
    kind: Union[RealtimeAudioDeviceKind, str],
    device_names: Iterable[str],
) -> SelectionViewParams:
    kind = _audio_kind(kind)
    device_names = list(device_names)
    current_selection = widget.current_realtime_audio_device_name(kind)
    current_available = current_selection in device_names if current_selection is not None else False
    items = [
        SelectionItem(
            name="System default",
            description="Use your operating system default device.",
            is_current=current_selection is None,
            actions=[AppEvent("PersistRealtimeAudioDeviceSelection", {"kind": kind, "name": None})],
            dismiss_on_select=True,
        )
    ]
    if current_selection is not None and not current_available:
        items.append(
            SelectionItem(
                name=f"Unavailable: {current_selection}",
                description="Configured device is not currently available.",
                is_current=True,
                is_disabled=True,
                disabled_reason="Reconnect the device or choose another one.",
            )
        )
    for device_name in device_names:
        items.append(
            SelectionItem(
                name=device_name,
                is_current=current_selection == device_name,
                actions=[
                    AppEvent(
                        "PersistRealtimeAudioDeviceSelection",
                        {"kind": kind, "name": device_name},
                    )
                ],
                dismiss_on_select=True,
            )
        )
    params = SelectionViewParams(
        header=f"Select {kind.title()}\nSaved devices apply to realtime voice only.",
        items=items,
    )
    widget.bottom_pane.show_selection_view(params)
    return params


def open_realtime_audio_restart_prompt(widget: Any, kind: Union[RealtimeAudioDeviceKind, str]) -> SelectionViewParams:
    kind = _audio_kind(kind)
    params = SelectionViewParams(
        header=f"Restart {kind.title()} now?\nConfiguration is saved. Restart local audio to use it immediately.",
        items=[
            SelectionItem(
                name="Restart now",
                description=f"Restart local {kind.noun()} audio now.",
                actions=[AppEvent("RestartRealtimeAudioDevice", {"kind": kind})],
                dismiss_on_select=True,
            ),
            SelectionItem(
                name="Apply later",
                description=f"Keep the current {kind.noun()} until local audio starts again.",
                dismiss_on_select=True,
            ),
        ],
    )
    widget.bottom_pane.show_selection_view(params)
    return params


def open_experimental_popup(widget: Any) -> ExperimentalFeaturesView:
    features = []
    for spec in getattr(widget, "FEATURES", ()):
        stage = getattr(spec, "stage", None)
        name = _maybe_call(stage, "experimental_menu_name")
        description = _maybe_call(stage, "experimental_menu_description")
        if name is None or description is None:
            continue
        feature = getattr(spec, "id")
        features.append(
            ExperimentalFeatureItem(
                feature=feature,
                name=name,
                description=description,
                enabled=widget.config.features.enabled(feature),
            )
        )
    view = ExperimentalFeaturesView(tuple(features))
    widget.bottom_pane.show_view(view)
    return view


def personality_label(personality: Union[Personality, str]) -> str:
    personality = _personality(personality)
    return {
        Personality.NONE: "None",
        Personality.FRIENDLY: "Friendly",
        Personality.PRAGMATIC: "Pragmatic",
    }[personality]


def personality_description(personality: Union[Personality, str]) -> str:
    personality = _personality(personality)
    return {
        Personality.NONE: "No personality instructions.",
        Personality.FRIENDLY: "Warm, collaborative, and helpful.",
        Personality.PRAGMATIC: "Concise, task-focused, and direct.",
    }[personality]


def _personality(value: Union[Personality, str]) -> Personality:
    return value if isinstance(value, Personality) else Personality(str(value))


def _audio_kind(value: Union[RealtimeAudioDeviceKind, str]) -> RealtimeAudioDeviceKind:
    return value if isinstance(value, RealtimeAudioDeviceKind) else RealtimeAudioDeviceKind(str(value))


def _maybe_call(target: Any, method_name: str) -> Optional[Any]:
    method = getattr(target, method_name, None)
    if method is None:
        return None
    return method()


def _last_width(widget: Any) -> Optional[int]:
    width = getattr(widget, "last_rendered_width", None)
    if hasattr(width, "get"):
        width = width.get()
    if width is None:
        return None
    try:
        width = int(width)
    except (TypeError, ValueError):
        return None
    return width if 0 <= width <= 65535 else None
