from __future__ import annotations

import pycodex.agent_graph_store as agent_graph_store
from pycodex.agent_graph_store.error import AgentGraphStoreError, AgentGraphStoreResult
from pycodex.agent_graph_store.local import LocalAgentGraphStore
from pycodex.agent_graph_store.store import AgentGraphStore
from pycodex.agent_graph_store.types import ThreadSpawnEdgeStatus


def test_agent_graph_store_crate_root_reexports_rust_public_items():
    # Rust crate/module: codex-agent-graph-store src/lib.rs. Behavior
    # contract: crate root pub-uses error, local, store, and types public items.
    assert agent_graph_store.AgentGraphStoreError is AgentGraphStoreError
    assert agent_graph_store.AgentGraphStoreResult is AgentGraphStoreResult
    assert agent_graph_store.LocalAgentGraphStore is LocalAgentGraphStore
    assert agent_graph_store.AgentGraphStore is AgentGraphStore
    assert agent_graph_store.ThreadSpawnEdgeStatus is ThreadSpawnEdgeStatus


def test_agent_graph_store_all_includes_rust_root_exports():
    # Rust source contract: these five names are public at crate root.
    rust_public_exports = {
        "AgentGraphStoreError",
        "AgentGraphStoreResult",
        "LocalAgentGraphStore",
        "AgentGraphStore",
        "ThreadSpawnEdgeStatus",
    }

    assert rust_public_exports.issubset(set(agent_graph_store.__all__))
