import pytest

from pycodex.state import DirectionalThreadSpawnEdgeStatus


def test_directional_thread_spawn_edge_status_wire_values() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/graph.rs::DirectionalThreadSpawnEdgeStatus
    # Behavior contract: strum serialize_all = "snake_case" persists open/closed.
    assert DirectionalThreadSpawnEdgeStatus.OPEN.value == "open"
    assert DirectionalThreadSpawnEdgeStatus.CLOSED.value == "closed"


def test_directional_thread_spawn_edge_status_as_ref_and_display() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/graph.rs::DirectionalThreadSpawnEdgeStatus
    # Behavior contract: AsRefStr and Display expose the same snake_case string.
    assert DirectionalThreadSpawnEdgeStatus.OPEN.as_ref() == "open"
    assert DirectionalThreadSpawnEdgeStatus.CLOSED.as_ref() == "closed"
    assert str(DirectionalThreadSpawnEdgeStatus.OPEN) == "open"
    assert str(DirectionalThreadSpawnEdgeStatus.CLOSED) == "closed"


def test_directional_thread_spawn_edge_status_parse() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/graph.rs::DirectionalThreadSpawnEdgeStatus
    # Behavior contract: EnumString accepts persisted snake_case values.
    assert DirectionalThreadSpawnEdgeStatus.parse("open") is DirectionalThreadSpawnEdgeStatus.OPEN
    assert (
        DirectionalThreadSpawnEdgeStatus.parse("closed")
        is DirectionalThreadSpawnEdgeStatus.CLOSED
    )


def test_directional_thread_spawn_edge_status_parse_rejects_unknown() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/graph.rs::DirectionalThreadSpawnEdgeStatus
    # Behavior contract: unknown persisted values fail parsing.
    with pytest.raises(ValueError, match="invalid directional thread spawn edge status"):
        DirectionalThreadSpawnEdgeStatus.parse("in_progress")
