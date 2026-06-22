"""Rust-derived tests for ``codex-hooks/src/schema.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/schema.rs``

Rust tests mirrored:
- ``generated_hook_schemas_match_fixtures``
- ``turn_scoped_hook_inputs_include_codex_turn_id_extension``
- ``subagent_context_fields_are_optional_for_hooks_that_run_inside_subagents``
- ``subagent_context_fields_serialize_flat_and_omit_when_absent``
"""

from __future__ import annotations

import json
from pathlib import Path

from pycodex.hooks import GENERATED_SCHEMA_DIR
from pycodex.hooks import PERMISSION_REQUEST_INPUT_FIXTURE
from pycodex.hooks import POST_COMPACT_INPUT_FIXTURE
from pycodex.hooks import POST_TOOL_USE_INPUT_FIXTURE
from pycodex.hooks import PRE_COMPACT_INPUT_FIXTURE
from pycodex.hooks import PRE_TOOL_USE_INPUT_FIXTURE
from pycodex.hooks import SCHEMA_FIXTURE_NAMES
from pycodex.hooks import STOP_INPUT_FIXTURE
from pycodex.hooks import SUBAGENT_START_INPUT_FIXTURE
from pycodex.hooks import SUBAGENT_STOP_INPUT_FIXTURE
from pycodex.hooks import USER_PROMPT_SUBMIT_INPUT_FIXTURE
from pycodex.hooks import SubagentCommandInputFields
from pycodex.hooks import SubagentHookContext
from pycodex.hooks import canonicalize_json
from pycodex.hooks import nullable_string_from_path
from pycodex.hooks import schema_for_fixture
from pycodex.hooks import schema_json
from pycodex.hooks import write_schema_fixtures


TURN_SCOPED_INPUT_FIXTURES = (
    PRE_TOOL_USE_INPUT_FIXTURE,
    PERMISSION_REQUEST_INPUT_FIXTURE,
    POST_TOOL_USE_INPUT_FIXTURE,
    PRE_COMPACT_INPUT_FIXTURE,
    POST_COMPACT_INPUT_FIXTURE,
    USER_PROMPT_SUBMIT_INPUT_FIXTURE,
    SUBAGENT_START_INPUT_FIXTURE,
    SUBAGENT_STOP_INPUT_FIXTURE,
    STOP_INPUT_FIXTURE,
)

OPTIONAL_SUBAGENT_INPUT_FIXTURES = (
    PRE_TOOL_USE_INPUT_FIXTURE,
    PERMISSION_REQUEST_INPUT_FIXTURE,
    POST_TOOL_USE_INPUT_FIXTURE,
    PRE_COMPACT_INPUT_FIXTURE,
    POST_COMPACT_INPUT_FIXTURE,
    USER_PROMPT_SUBMIT_INPUT_FIXTURE,
)


def test_generated_hook_schemas_match_python_fixtures(tmp_path: Path) -> None:
    # Rust test: generated_hook_schemas_match_fixtures.
    stale = tmp_path / "schema" / GENERATED_SCHEMA_DIR / "stale.schema.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")

    write_schema_fixtures(tmp_path / "schema")

    generated_dir = tmp_path / "schema" / GENERATED_SCHEMA_DIR
    assert sorted(path.name for path in generated_dir.iterdir()) == sorted(SCHEMA_FIXTURE_NAMES)
    assert not stale.exists()
    for fixture in SCHEMA_FIXTURE_NAMES:
        assert (generated_dir / fixture).read_text(encoding="utf-8") == schema_json(fixture)


def test_turn_scoped_hook_inputs_include_codex_turn_id_extension() -> None:
    # Rust test: turn_scoped_hook_inputs_include_codex_turn_id_extension.
    for fixture in TURN_SCOPED_INPUT_FIXTURES:
        schema = schema_for_fixture(fixture)
        assert schema["properties"]["turn_id"]["type"] == "string"
        assert "Codex extension" in schema["properties"]["turn_id"]["description"]
        assert "turn_id" in schema["required"]


def test_subagent_context_fields_are_optional_for_hooks_that_run_inside_subagents() -> None:
    # Rust test: subagent_context_fields_are_optional_for_hooks_that_run_inside_subagents.
    for fixture in OPTIONAL_SUBAGENT_INPUT_FIXTURES:
        schema = schema_for_fixture(fixture)
        assert schema["properties"]["agent_id"]["type"] == "string"
        assert schema["properties"]["agent_type"]["type"] == "string"
        assert "agent_id" not in schema["required"]
        assert "agent_type" not in schema["required"]


def test_subagent_context_fields_serialize_flat_and_omit_when_absent() -> None:
    # Rust test: subagent_context_fields_serialize_flat_and_omit_when_absent.
    subagent = SubagentCommandInputFields.from_context(
        SubagentHookContext("agent-1", "worker")
    )
    payload = {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "transcript_path": nullable_string_from_path(None),
        "cwd": "/tmp",
        "hook_event_name": "PreToolUse",
        "model": "gpt-test",
        "permission_mode": "default",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello"},
        "tool_use_id": "tool-1",
    }
    subagent.apply_to(payload)

    assert payload == {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "agent_id": "agent-1",
        "agent_type": "worker",
        "transcript_path": None,
        "cwd": "/tmp",
        "hook_event_name": "PreToolUse",
        "model": "gpt-test",
        "permission_mode": "default",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello"},
        "tool_use_id": "tool-1",
    }

    root_payload = {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "transcript_path": nullable_string_from_path(None),
        "cwd": "/tmp",
        "hook_event_name": "PreToolUse",
    }
    SubagentCommandInputFields.from_context(None).apply_to(root_payload)
    assert "agent_id" not in root_payload
    assert "agent_type" not in root_payload


def test_schema_json_is_canonicalized_and_stable() -> None:
    # Rust source contract: schema_json canonicalizes object keys before pretty JSON.
    fixture_json = schema_json(PRE_TOOL_USE_INPUT_FIXTURE)
    parsed = json.loads(fixture_json)
    assert parsed == canonicalize_json(parsed)
    assert fixture_json.endswith("\n")
