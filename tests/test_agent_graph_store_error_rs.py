from __future__ import annotations

import pytest

from pycodex.agent_graph_store import (
    AgentGraphStoreError,
    Internal,
    InvalidRequest,
    internal,
    invalid_request,
)


def test_agent_graph_store_error_display_messages_match_rust_thiserror():
    # Rust crate/module: codex-agent-graph-store src/error.rs. Behavior
    # contract: thiserror Display strings include the variant prefix.
    invalid = InvalidRequest("missing parent")
    failure = Internal("database unavailable")

    assert str(invalid) == "invalid agent graph store request: missing parent"
    assert str(failure) == "agent graph store internal error: database unavailable"


def test_agent_graph_store_error_constructors_and_base_type():
    # Rust source contract: the shared error enum has invalid request and
    # internal variants.
    invalid = invalid_request("bad edge")
    failure = internal("boom")

    assert isinstance(invalid, AgentGraphStoreError)
    assert isinstance(failure, AgentGraphStoreError)
    assert invalid.variant == "invalid_request"
    assert failure.variant == "internal"
    assert invalid.message == "bad edge"
    assert failure.message == "boom"


def test_agent_graph_store_error_requires_string_message():
    with pytest.raises(TypeError):
        InvalidRequest(1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Internal(None)  # type: ignore[arg-type]
