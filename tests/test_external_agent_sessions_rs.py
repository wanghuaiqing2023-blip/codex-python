import json
from pathlib import Path

import pytest

from pycodex.external_agent_sessions import (
    EXTERNAL_SESSION_IMPORTED_MARKER,
    ExternalAgentSessionMigration,
    SessionNotDetected,
    detect_recent_sessions,
    load_session_for_import,
    prepare_pending_session_imports,
    record_imported_session,
    tool_call_note,
    tool_result_note,
)


def record(role: str, text: str, cwd: Path, timestamp: str = "2026-06-23T00:00:00Z") -> dict:
    return {
        "type": role,
        "cwd": str(cwd),
        "timestamp": timestamp,
        "message": {"content": text},
    }


def custom_title_record(title: str) -> dict:
    return {"type": "custom-title", "customTitle": title}


def ai_title_record(title: str) -> dict:
    return {"type": "ai-title", "aiTitle": title}


def jsonl(records: list[dict]) -> str:
    return "\n".join(json.dumps(item, separators=(",", ":")) for item in records)


def write_session(
    external_agent_home: Path,
    project_root: Path,
    file_name: str,
    records: list[dict],
) -> Path:
    projects_dir = external_agent_home / "projects" / "repo"
    project_root.mkdir(parents=True, exist_ok=True)
    projects_dir.mkdir(parents=True, exist_ok=True)
    session_path = projects_dir / file_name
    session_path.write_text(jsonl(records), encoding="utf-8")
    return session_path


def event_messages(imported) -> list[dict]:
    return [item["event"] for item in imported.rollout_items if item["type"] == "event_msg"]


def test_converts_tool_use_blocks_to_bounded_external_agent_tags() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/records.rs
    # Rust test: converts_tool_use_blocks_to_bounded_external_agent_tags
    # Contract: tool_use blocks become bounded external_agent_tool_call notes.
    block = {
        "type": "tool_use",
        "name": "Bash",
        "input": {
            "description": "Check repo status",
            "command": "git status --short",
        },
    }

    assert tool_call_note(block) == (
        "[external_agent_tool_call: Bash]\n"
        "description: Check repo status\n"
        "command: git status --short\n"
        "[/external_agent_tool_call]"
    )


def test_converts_tool_result_blocks_to_bounded_external_agent_tags() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/records.rs
    # Rust test: converts_tool_result_blocks_to_bounded_external_agent_tags
    # Contract: tool_result blocks become bounded external_agent_tool_result notes.
    block = {
        "type": "tool_result",
        "content": "codex-rs/external-agent-sessions/src/records.rs",
    }

    assert tool_result_note(block) == (
        "[external_agent_tool_result]\n"
        "codex-rs/external-agent-sessions/src/records.rs\n"
        "[/external_agent_tool_result]"
    )


def test_converts_error_tool_result_blocks_to_bounded_external_agent_tags() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/records.rs
    # Rust test: converts_error_tool_result_blocks_to_bounded_external_agent_tags
    # Contract: error tool_result blocks include the error tag variant.
    assert tool_result_note({"type": "tool_result", "is_error": True, "content": "command failed"}) == (
        "[external_agent_tool_result: error]\n"
        "command failed\n"
        "[/external_agent_tool_result]"
    )


def test_detects_recent_sessions_with_existing_roots(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/detect.rs
    # Rust test: detects_recent_sessions_with_existing_roots
    # Contract: recent jsonl sessions under projects/* with existing cwd are detected.
    external_agent_home = tmp_path / ".external"
    project_root = tmp_path / "repo"
    session_path = write_session(
        external_agent_home,
        project_root,
        "session.jsonl",
        [record("user", "hello there", project_root), record("assistant", "ack", project_root)],
    )

    sessions = detect_recent_sessions(external_agent_home, tmp_path)

    assert sessions == [
        ExternalAgentSessionMigration(session_path, project_root, "hello there")
    ]


def test_prefers_custom_title_over_later_ai_title(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/detect.rs
    # Rust test: prefers_custom_title_over_later_ai_title
    # Contract: custom title has precedence over AI title when both are present.
    external_agent_home = tmp_path / ".external"
    project_root = tmp_path / "repo"
    session_path = write_session(
        external_agent_home,
        project_root,
        "session.jsonl",
        [
            record("user", "hello there", project_root),
            custom_title_record("custom title"),
            ai_title_record("generated title"),
        ],
    )

    assert detect_recent_sessions(external_agent_home, tmp_path) == [
        ExternalAgentSessionMigration(session_path, project_root, "custom title")
    ]


def test_prefers_latest_custom_title_over_first_user_message(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/detect.rs
    # Rust test: prefers_latest_custom_title_over_first_user_message
    # Contract: latest custom-title record overrides the first user-message label.
    external_agent_home = tmp_path / ".external"
    project_root = tmp_path / "repo"
    session_path = write_session(
        external_agent_home,
        project_root,
        "session.jsonl",
        [
            record("user", "hello there", project_root),
            custom_title_record("first title"),
            custom_title_record("final title"),
        ],
    )

    assert detect_recent_sessions(external_agent_home, tmp_path) == [
        ExternalAgentSessionMigration(session_path, project_root, "final title")
    ]


def test_detects_ai_title_over_first_user_message(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/detect.rs
    # Rust test: detects_ai_title_over_first_user_message
    # Contract: AI title is used when no custom title exists.
    external_agent_home = tmp_path / ".external"
    project_root = tmp_path / "repo"
    session_path = write_session(
        external_agent_home,
        project_root,
        "session.jsonl",
        [
            record("user", "hello there", project_root),
            ai_title_record("generated by source app"),
        ],
    )

    assert detect_recent_sessions(external_agent_home, tmp_path) == [
        ExternalAgentSessionMigration(session_path, project_root, "generated by source app")
    ]


def test_ignores_old_sessions(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/detect.rs
    # Rust test: ignores_old_sessions
    # Contract: sessions older than 30 days are not imported.
    external_agent_home = tmp_path / ".external"
    project_root = tmp_path / "repo"
    write_session(
        external_agent_home,
        project_root,
        "session.jsonl",
        [record("user", "hello", project_root, "2020-01-01T00:00:00Z")],
    )

    assert detect_recent_sessions(external_agent_home, tmp_path) == []


def test_skips_already_imported_current_session_versions(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/detect.rs
    # Rust test: skips_already_imported_current_session_versions
    # Contract: exact source path/content hash already recorded in ledger is not redetected.
    external_agent_home = tmp_path / ".external"
    project_root = tmp_path / "repo"
    session_path = write_session(
        external_agent_home,
        project_root,
        "session.jsonl",
        [record("user", "hello there", project_root)],
    )
    record_imported_session(tmp_path, session_path, "thread-1")

    assert detect_recent_sessions(external_agent_home, tmp_path) == []


def test_redetects_sessions_when_source_contents_change_after_import(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/detect.rs
    # Rust test: redetects_sessions_when_source_contents_change_after_import
    # Contract: import ledger keys include source path plus current content hash.
    external_agent_home = tmp_path / ".external"
    project_root = tmp_path / "repo"
    session_path = write_session(
        external_agent_home,
        project_root,
        "session.jsonl",
        [record("user", "hello there", project_root)],
    )
    record_imported_session(tmp_path, session_path, "thread-1")
    session_path.write_text(
        jsonl(
            [
                record("user", "hello there", project_root),
                record("assistant", "new reply", project_root),
            ]
        ),
        encoding="utf-8",
    )

    assert detect_recent_sessions(external_agent_home, tmp_path) == [
        ExternalAgentSessionMigration(session_path, project_root, "hello there")
    ]


def test_builds_visible_turns_for_imported_history(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/export.rs
    # Rust test: builds_visible_turns_for_imported_history
    # Contract: imported history creates visible turns and appends import marker to the final turn.
    project_root = tmp_path / "repo"
    project_root.mkdir()
    path = tmp_path / "session.jsonl"
    path.write_text(
        jsonl(
            [
                record("user", "first request", project_root),
                record("assistant", "first answer", project_root),
                record("user", "second request", project_root),
            ]
        ),
        encoding="utf-8",
    )

    imported = load_session_for_import(path)
    assert imported is not None
    events = event_messages(imported)

    assert [event["turn_id"] for event in events if event["type"] == "turn_started"] == [
        "external-import-turn-1",
        "external-import-turn-2",
    ]
    assert {"type": "user_message", "message": "first request"} in events
    assert {"type": "agent_message", "message": "first answer"} in events
    assert {"type": "agent_message", "message": EXTERNAL_SESSION_IMPORTED_MARKER} in events


def test_adds_import_marker_without_replacing_last_agent_message(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/export.rs
    # Rust test: adds_import_marker_without_replacing_last_agent_message
    # Contract: marker is visible, while turn_complete keeps the last real agent message.
    project_root = tmp_path / "repo"
    project_root.mkdir()
    path = tmp_path / "session.jsonl"
    path.write_text(
        jsonl(
            [
                record("user", "first request", project_root),
                record("assistant", "first answer", project_root),
            ]
        ),
        encoding="utf-8",
    )

    imported = load_session_for_import(path)
    assert imported is not None
    events = event_messages(imported)

    assert {"type": "agent_message", "message": EXTERNAL_SESSION_IMPORTED_MARKER} in events
    turn_complete = [event for event in events if event["type"] == "turn_complete"][-1]
    assert turn_complete["last_agent_message"] == "first answer"


def test_loads_custom_title_for_imported_session(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/export.rs
    # Rust test: loads_custom_title_for_imported_session
    # Contract: exported session title uses custom-title.
    project_root = tmp_path / "repo"
    project_root.mkdir()
    path = tmp_path / "session.jsonl"
    path.write_text(
        jsonl([record("user", "first request", project_root), custom_title_record("named by source app")]),
        encoding="utf-8",
    )

    imported = load_session_for_import(path)

    assert imported is not None
    assert imported.title == "named by source app"


def test_loads_ai_title_for_imported_session(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/export.rs
    # Rust test: loads_ai_title_for_imported_session
    # Contract: exported session title uses AI title when no custom title exists.
    project_root = tmp_path / "repo"
    project_root.mkdir()
    path = tmp_path / "session.jsonl"
    path.write_text(
        jsonl([record("user", "first request", project_root), ai_title_record("generated by source app")]),
        encoding="utf-8",
    )

    imported = load_session_for_import(path)

    assert imported is not None
    assert imported.title == "generated by source app"


def test_loads_custom_title_over_later_ai_title_for_imported_session(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/export.rs
    # Rust test: loads_custom_title_over_later_ai_title_for_imported_session
    # Contract: exported session title uses custom-title over later ai-title.
    project_root = tmp_path / "repo"
    project_root.mkdir()
    path = tmp_path / "session.jsonl"
    path.write_text(
        jsonl(
            [
                record("user", "first request", project_root),
                custom_title_record("named by source app"),
                ai_title_record("generated by source app"),
            ]
        ),
        encoding="utf-8",
    )

    imported = load_session_for_import(path)

    assert imported is not None
    assert imported.title == "named by source app"


def test_emits_token_usage_for_imported_history(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/export.rs
    # Rust test: emits_token_usage_for_imported_history
    # Contract: import emits a token_count event with matching total and last usage.
    project_root = tmp_path / "repo"
    project_root.mkdir()
    path = tmp_path / "session.jsonl"
    path.write_text(
        jsonl(
            [
                record("user", "first request", project_root),
                record("assistant", "first answer", project_root),
                record("user", "second request", project_root),
            ]
        ),
        encoding="utf-8",
    )

    imported = load_session_for_import(path)
    assert imported is not None
    token_count = next(event for event in event_messages(imported) if event["type"] == "token_count")
    info = token_count["info"]

    assert info["last_token_usage"]["total_tokens"] > 0
    assert info["total_token_usage"] == info["last_token_usage"]


def test_rejects_session_that_was_not_detected(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/lib.rs
    # Rust test: rejects_session_that_was_not_detected
    # Contract: requested undetected sessions fail unless already imported.
    source_path = tmp_path / "session.jsonl"
    source_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(SessionNotDetected) as exc_info:
        prepare_pending_session_imports(
            tmp_path / "codex-home",
            [ExternalAgentSessionMigration(source_path, tmp_path)],
            [],
        )

    assert exc_info.value.path == source_path


def test_skips_session_that_was_already_imported(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-external-agent-sessions
    # Rust module: src/lib.rs
    # Rust test: skips_session_that_was_already_imported
    # Contract: current source path/content already recorded in ledger is skipped.
    codex_home = tmp_path / "codex-home"
    source_path = tmp_path / "session.jsonl"
    source_path.write_text("{}\n", encoding="utf-8")
    record_imported_session(codex_home, source_path, "thread-1")

    assert (
        prepare_pending_session_imports(
            codex_home,
            [ExternalAgentSessionMigration(source_path, tmp_path)],
            [],
        )
        == []
    )
