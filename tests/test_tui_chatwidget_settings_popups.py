from __future__ import annotations

from types import SimpleNamespace

from pycodex.tui.chatwidget.settings_popups import (
    AppEvent,
    Personality,
    RealtimeAudioDeviceKind,
    open_experimental_popup,
    open_personality_popup,
    open_realtime_audio_device_selection_with_names,
    open_realtime_audio_popup,
    open_realtime_audio_restart_prompt,
    open_theme_picker,
    personality_description,
    personality_label,
)


class Pane:
    def __init__(self) -> None:
        self.selection = None
        self.view = None

    def show_selection_view(self, params) -> None:
        self.selection = params

    def show_view(self, view) -> None:
        self.view = view


class Features:
    def __init__(self, enabled=()) -> None:
        self._enabled = set(enabled)

    def enabled(self, feature) -> bool:
        return feature in self._enabled


class Widget:
    def __init__(self) -> None:
        self.bottom_pane = Pane()
        self.config = SimpleNamespace(
            tui_theme="solarized",
            personality=None,
            features=Features(),
        )
        self.info_messages = []
        self.error_messages = []
        self.session_configured = True
        self.supports_personality = True
        self.model = "gpt"
        self.microphone = None
        self.speaker = "Desk Speaker"
        self.FEATURES = ()

    def is_session_configured(self) -> bool:
        return self.session_configured

    def current_model_supports_personality(self) -> bool:
        return self.supports_personality

    def current_model(self) -> str:
        return self.model

    def add_info_message(self, message, hint=None) -> None:
        self.info_messages.append((message, hint))

    def add_error_message(self, message) -> None:
        self.error_messages.append(message)

    def current_realtime_audio_selection_label(self, kind) -> str:
        name = self.current_realtime_audio_device_name(kind)
        return name or "System default"

    def current_realtime_audio_device_name(self, kind):
        return self.microphone if kind == RealtimeAudioDeviceKind.MICROPHONE else self.speaker


def test_open_theme_picker_delegates_or_builds_semantic_placeholder() -> None:
    widget = Widget()

    params = open_theme_picker(widget)

    assert params.title == "Theme"
    assert params.items[0].name == "solarized"
    assert widget.bottom_pane.selection is params


def test_open_personality_popup_guards_startup_and_model_support_then_builds_items() -> None:
    widget = Widget()
    widget.session_configured = False

    assert open_personality_popup(widget) is None
    assert widget.info_messages == [("Personality selection is disabled until startup completes.", None)]

    widget = Widget()
    widget.supports_personality = False
    assert open_personality_popup(widget) is None
    assert "doesn't support personalities" in widget.error_messages[0]

    widget = Widget()
    widget.config.personality = Personality.PRAGMATIC
    params = open_personality_popup(widget)
    assert [item.name for item in params.items] == ["Friendly", "Pragmatic"]
    assert params.items[1].is_current is True
    assert params.items[0].actions == [
        AppEvent("CodexOp", {"op": "override_turn_context", "personality": Personality.FRIENDLY}),
        AppEvent("UpdatePersonality", {"personality": Personality.FRIENDLY}),
        AppEvent("PersistPersonalitySelection", {"personality": Personality.FRIENDLY}),
    ]


def test_realtime_audio_popup_and_device_selection_match_current_state() -> None:
    widget = Widget()

    params = open_realtime_audio_popup(widget)
    assert [item.name for item in params.items] == ["Microphone", "Speaker"]
    assert params.items[0].description == "Current: System default"
    assert params.items[1].description == "Current: Desk Speaker"

    params = open_realtime_audio_device_selection_with_names(
        widget,
        RealtimeAudioDeviceKind.SPEAKER,
        ["Headphones"],
    )
    assert params.items[0].name == "System default"
    assert params.items[1].name == "Unavailable: Desk Speaker"
    assert params.items[1].is_disabled is True
    assert params.items[2].actions == [
        AppEvent("PersistRealtimeAudioDeviceSelection", {"kind": RealtimeAudioDeviceKind.SPEAKER, "name": "Headphones"})
    ]


def test_realtime_audio_restart_prompt_builds_restart_and_apply_later_choices() -> None:
    widget = Widget()

    params = open_realtime_audio_restart_prompt(widget, RealtimeAudioDeviceKind.MICROPHONE)

    assert [item.name for item in params.items] == ["Restart now", "Apply later"]
    assert params.items[0].actions == [
        AppEvent("RestartRealtimeAudioDevice", {"kind": RealtimeAudioDeviceKind.MICROPHONE})
    ]
    assert "microphone" in params.items[1].description


class Stage:
    def __init__(self, name=None, description=None) -> None:
        self.name = name
        self.description = description

    def experimental_menu_name(self):
        return self.name

    def experimental_menu_description(self):
        return self.description


def test_open_experimental_popup_filters_specs_without_menu_metadata() -> None:
    widget = Widget()
    widget.config.features = Features({"fast"})
    widget.FEATURES = (
        SimpleNamespace(id="fast", stage=Stage("Fast mode", "Go faster")),
        SimpleNamespace(id="hidden", stage=Stage(None, None)),
    )

    view = open_experimental_popup(widget)

    assert widget.bottom_pane.view is view
    assert len(view.features) == 1
    assert view.features[0].feature == "fast"
    assert view.features[0].enabled is True


def test_personality_labels_and_descriptions_match_rust_strings() -> None:
    assert personality_label(Personality.NONE) == "None"
    assert personality_label(Personality.FRIENDLY) == "Friendly"
    assert personality_label(Personality.PRAGMATIC) == "Pragmatic"
    assert personality_description(Personality.NONE) == "No personality instructions."
    assert personality_description(Personality.FRIENDLY) == "Warm, collaborative, and helpful."
    assert personality_description(Personality.PRAGMATIC) == "Concise, task-focused, and direct."
