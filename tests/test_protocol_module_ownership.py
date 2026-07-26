"""Rust-derived ownership checks for codex-protocol modules."""

from __future__ import annotations

from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxKind,
    FileSystemSandboxPolicy,
    FileSystemSpecialPath,
    NetworkSandboxPolicy,
    ReadDenyMatcher,
    SandboxPolicy,
    SessionId,
    ThreadId,
    WritableRoot,
)
from pycodex.protocol.protocol import ConversationStartParams, RealtimeOutputModality


def test_identifier_types_use_their_rust_module_owners() -> None:
    # Rust: codex-protocol/src/session_id.rs and thread_id.rs.
    assert SessionId.__module__ == "pycodex.protocol.session_id"
    assert ThreadId.__module__ == "pycodex.protocol.thread_id"


def test_permissions_types_use_permissions_module_owner() -> None:
    # Rust: codex-protocol/src/permissions.rs.
    owned_types = (
        NetworkSandboxPolicy,
        FileSystemAccessMode,
        FileSystemSpecialPath,
        FileSystemPath,
        FileSystemSandboxEntry,
        FileSystemSandboxKind,
        FileSystemSandboxPolicy,
        ReadDenyMatcher,
    )
    assert {item.__module__ for item in owned_types} == {"pycodex.protocol.permissions"}


def test_protocol_types_are_not_owned_by_models_module() -> None:
    # Rust: codex-protocol/src/protocol.rs.
    assert SandboxPolicy.__module__ == "pycodex.protocol.protocol"
    assert WritableRoot.__module__ == "pycodex.protocol.protocol"


def test_conversation_start_prompt_preserves_missing_null_and_text() -> None:
    # Rust: protocol.rs::conversation_start_prompt_serde uses double_option.
    omitted = ConversationStartParams(output_modality=RealtimeOutputModality.TEXT)
    explicit_null = ConversationStartParams(output_modality=RealtimeOutputModality.TEXT, prompt=None)
    text = ConversationStartParams(output_modality=RealtimeOutputModality.TEXT, prompt="hello")

    assert "prompt" not in omitted.to_mapping()
    assert explicit_null.to_mapping()["prompt"] is None
    assert text.to_mapping()["prompt"] == "hello"
