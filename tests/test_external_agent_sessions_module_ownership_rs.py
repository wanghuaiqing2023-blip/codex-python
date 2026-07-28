"""Rust-derived ownership checks for codex-external-agent-sessions.

Rust baseline: 1c7832ffa37a3ab56f601497c00bfce120370bf9.
"""

from pycodex import external_agent_sessions


def test_external_agent_session_items_have_rust_module_owners() -> None:
    from pycodex.external_agent_sessions import detect, export, ledger, records

    expected_owners = {
        detect.detect_recent_sessions: "pycodex.external_agent_sessions.detect",
        export.load_session_for_import: "pycodex.external_agent_sessions.export",
        ledger.has_current_session_been_imported: "pycodex.external_agent_sessions.ledger",
        ledger.record_imported_session: "pycodex.external_agent_sessions.ledger",
        records.SessionSummary: "pycodex.external_agent_sessions.records",
        records.summarize_session: "pycodex.external_agent_sessions.records",
    }

    for item, expected_owner in expected_owners.items():
        assert item.__module__ == expected_owner


def test_external_agent_session_root_reexports_match_rust_lib() -> None:
    from pycodex.external_agent_sessions.detect import detect_recent_sessions
    from pycodex.external_agent_sessions.export import load_session_for_import
    from pycodex.external_agent_sessions.ledger import (
        has_current_session_been_imported,
        record_imported_session,
    )
    from pycodex.external_agent_sessions.records import SessionSummary, summarize_session

    assert external_agent_sessions.detect_recent_sessions is detect_recent_sessions
    assert external_agent_sessions.load_session_for_import is load_session_for_import
    assert (
        external_agent_sessions.has_current_session_been_imported
        is has_current_session_been_imported
    )
    assert external_agent_sessions.record_imported_session is record_imported_session
    assert external_agent_sessions.SessionSummary is SessionSummary
    assert external_agent_sessions.summarize_session is summarize_session
