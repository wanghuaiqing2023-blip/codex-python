from __future__ import annotations

import json

import pytest

from pycodex.agent_graph_store import ThreadSpawnEdgeStatus


def test_thread_spawn_edge_status_serializes_as_snake_case():
    # Rust crate/module: codex-agent-graph-store src/types.rs. Rust test:
    # thread_spawn_edge_status_serializes_as_snake_case.
    assert json.dumps(ThreadSpawnEdgeStatus.Open.to_json()) == '"open"'
    assert json.dumps(ThreadSpawnEdgeStatus.Closed.to_json()) == '"closed"'
    assert ThreadSpawnEdgeStatus.from_json(json.loads('"open"')) is ThreadSpawnEdgeStatus.Open
    assert ThreadSpawnEdgeStatus.from_json(json.loads('"closed"')) is ThreadSpawnEdgeStatus.Closed


def test_thread_spawn_edge_status_rejects_unknown_values():
    # Rust serde enum accepts only declared snake_case variants.
    with pytest.raises(ValueError):
        ThreadSpawnEdgeStatus.from_json("OPEN")
    with pytest.raises(TypeError):
        ThreadSpawnEdgeStatus.from_json(1)  # type: ignore[arg-type]
