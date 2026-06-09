from __future__ import annotations

from types import SimpleNamespace

from pycodex.core.context import TurnAborted
from pycodex.core.tasks import (
    GRACEFULL_INTERRUPTION_TIMEOUT_MS,
    TASK_COMPACT_METRIC,
    TURN_MEMORY_METRIC,
    TURN_NETWORK_PROXY_METRIC,
    InterruptedTurnHistoryMarker,
    SessionTaskContext,
    bool_tag,
    emit_compact_metric,
    emit_turn_memory_metric,
    emit_turn_network_proxy_metric,
    interrupted_turn_history_marker,
)
from pycodex.features import Feature, Features
from pycodex.protocol import ContentItem, ResponseItem


class Telemetry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, list[tuple[str, str]]]] = []

    def counter(self, name: str, inc: int, tags: list[tuple[str, str]]) -> None:
        self.calls.append((name, inc, tags))


def test_interrupted_turn_history_marker_from_config_matches_rust_feature_gate() -> None:
    # Rust source: codex-rs/core/src/tasks/mod.rs
    # Contract: agent interrupt history is disabled by config; otherwise
    # MultiAgentV2 switches the marker from contextual user to developer.
    disabled = SimpleNamespace(agent_interrupt_message_enabled=False, features=Features())
    v1 = SimpleNamespace(agent_interrupt_message_enabled=True, features=Features())
    v2 = SimpleNamespace(agent_interrupt_message_enabled=True, features=Features().enable(Feature.MULTI_AGENT_V2))

    assert InterruptedTurnHistoryMarker.from_config(disabled) is InterruptedTurnHistoryMarker.DISABLED
    assert InterruptedTurnHistoryMarker.from_config(v1) is InterruptedTurnHistoryMarker.CONTEXTUAL_USER
    assert InterruptedTurnHistoryMarker.from_config(v2) is InterruptedTurnHistoryMarker.DEVELOPER


def test_interrupted_turn_history_marker_renders_contextual_user_item() -> None:
    # Rust source: interrupted_turn_history_marker(ContextualUser).
    # Contract: contextual marker is a user message containing the
    # TurnAborted interrupted guidance fragment.
    item = interrupted_turn_history_marker(InterruptedTurnHistoryMarker.CONTEXTUAL_USER)

    expected = TurnAborted.new(TurnAborted.INTERRUPTED_GUIDANCE).render()
    assert item == ResponseItem.message("user", (ContentItem.input_text(expected),))


def test_interrupted_turn_history_marker_renders_developer_item() -> None:
    # Rust source: interrupted_turn_history_marker(Developer).
    # Contract: developer marker uses the developer-specific interrupted
    # guidance wrapped in the same TurnAborted markers.
    item = interrupted_turn_history_marker(InterruptedTurnHistoryMarker.DEVELOPER)

    expected = TurnAborted.new(TurnAborted.INTERRUPTED_DEVELOPER_GUIDANCE).render()
    assert item == ResponseItem.message("developer", (ContentItem.input_text(expected),))
    assert interrupted_turn_history_marker(InterruptedTurnHistoryMarker.DISABLED) is None


def test_root_metric_helpers_emit_rust_metric_names_and_tags() -> None:
    # Rust source: codex-rs/core/src/tasks/mod_tests.rs
    # Contract: root task metric helpers use fixed metric names and lower-case
    # boolean tag strings.
    telemetry = Telemetry()

    emit_turn_network_proxy_metric(telemetry, True, ("tmp_mem_enabled", "true"))
    emit_turn_memory_metric(telemetry, True, False, False)
    emit_compact_metric(telemetry, "remote_v2", True)

    assert telemetry.calls == [
        (
            TURN_NETWORK_PROXY_METRIC,
            1,
            [("active", "true"), ("tmp_mem_enabled", "true")],
        ),
        (
            TURN_MEMORY_METRIC,
            1,
            [
                ("read_allowed", "false"),
                ("feature_enabled", "true"),
                ("config_use_memories", "false"),
                ("has_citations", "false"),
            ],
        ),
        (TASK_COMPACT_METRIC, 1, [("type", "remote_v2"), ("manual", "true")]),
    ]
    assert bool_tag(False) == "false"
    assert GRACEFULL_INTERRUPTION_TIMEOUT_MS == 100


def test_emit_turn_network_proxy_metric_records_inactive_turn() -> None:
    # Rust source: codex-rs/core/src/tasks/mod_tests.rs
    # Rust test: emit_turn_network_proxy_metric_records_inactive_turn.
    telemetry = Telemetry()

    emit_turn_network_proxy_metric(telemetry, False, ("tmp_mem_enabled", "false"))

    assert telemetry.calls == [
        (
            TURN_NETWORK_PROXY_METRIC,
            1,
            [("active", "false"), ("tmp_mem_enabled", "false")],
        )
    ]


def test_emit_turn_memory_metric_records_read_allowed_with_citations() -> None:
    # Rust source: codex-rs/core/src/tasks/mod_tests.rs
    # Rust test: emit_turn_memory_metric_records_read_allowed_with_citations.
    telemetry = Telemetry()

    emit_turn_memory_metric(telemetry, True, True, True)

    assert telemetry.calls == [
        (
            TURN_MEMORY_METRIC,
            1,
            [
                ("read_allowed", "true"),
                ("feature_enabled", "true"),
                ("config_use_memories", "true"),
                ("has_citations", "true"),
            ],
        )
    ]


def test_emit_compact_metric_records_auto_local() -> None:
    # Rust source: codex-rs/core/src/tasks/mod_tests.rs
    # Rust test: emit_compact_metric_records_auto_local.
    telemetry = Telemetry()

    emit_compact_metric(telemetry, "local", False)

    assert telemetry.calls == [
        (TASK_COMPACT_METRIC, 1, [("type", "local"), ("manual", "false")])
    ]


def test_session_task_context_wraps_session_services() -> None:
    # Rust source: SessionTaskContext in codex-rs/core/src/tasks/mod.rs.
    # Contract: the context clones/exposes the session, turn extension data,
    # auth manager, and models manager.
    session = SimpleNamespace(
        services=SimpleNamespace(auth_manager="auth", models_manager="models")
    )

    ctx = SessionTaskContext.new(session, {"turn": 1})

    assert ctx.clone_session() is session
    assert ctx.turn_extension_data() == {"turn": 1}
    assert ctx.auth_manager() == "auth"
    assert ctx.models_manager() == "models"
