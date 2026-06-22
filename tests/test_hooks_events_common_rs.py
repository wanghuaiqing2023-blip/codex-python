"""Rust-derived tests for ``codex-hooks/src/events/common.rs``.

Rust crate: ``codex-hooks``
Rust module: ``src/events/common.rs``

Rust tests mirrored:
- matcher helper tests in ``#[cfg(test)] mod tests``
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest

from pycodex.hooks import append_additional_context
from pycodex.hooks import flatten_additional_contexts
from pycodex.hooks import hook_completed_for_tool_use
from pycodex.hooks import hook_run_for_tool_use
from pycodex.hooks import join_text_chunks
from pycodex.hooks import matcher_inputs
from pycodex.hooks import matcher_pattern_for_event
from pycodex.hooks import matches_matcher
from pycodex.hooks import serialization_failure_hook_events
from pycodex.hooks import serialization_failure_hook_events_for_tool_use
from pycodex.hooks import trimmed_non_empty
from pycodex.hooks import validate_matcher_pattern
from pycodex.protocol import HookCompletedEvent
from pycodex.protocol import HookEventName
from pycodex.protocol import HookExecutionMode
from pycodex.protocol import HookHandlerType
from pycodex.protocol import HookOutputEntry
from pycodex.protocol import HookOutputEntryKind
from pycodex.protocol import HookRunStatus
from pycodex.protocol import HookRunSummary
from pycodex.protocol import HookScope
from pycodex.protocol import HookSource


def _summary() -> HookRunSummary:
    return HookRunSummary(
        id="pre-tool-use:0:/tmp/hooks.json",
        event_name=HookEventName.PRE_TOOL_USE,
        handler_type=HookHandlerType.COMMAND,
        execution_mode=HookExecutionMode.SYNC,
        scope=HookScope.TURN,
        source_path=PurePosixPath("/tmp/hooks.json"),
        source=HookSource.USER,
        display_order=0,
        status=HookRunStatus.RUNNING,
        started_at=123,
    )


def _handler() -> SimpleNamespace:
    return SimpleNamespace(
        event_name=HookEventName.PRE_TOOL_USE,
        source_path=PurePosixPath("/tmp/hooks.json"),
        source=HookSource.USER,
        display_order=0,
        status_message="running",
        started_at=123,
    )


def test_matcher_omitted_matches_all_occurrences() -> None:
    # Rust crate/module/test: codex-hooks/src/events/common.rs
    # tests::matcher_omitted_matches_all_occurrences.
    assert matches_matcher(None, "Bash")
    assert matches_matcher(None, "Write")


def test_matcher_star_and_empty_string_match_all_occurrences() -> None:
    # Rust tests: matcher_star_matches_all_occurrences and
    # matcher_empty_string_matches_all_occurrences.
    assert matches_matcher("*", "Bash")
    assert matches_matcher("*", "Edit")
    assert validate_matcher_pattern("*") is None
    assert matches_matcher("", "Bash")
    assert matches_matcher("", "SessionStart")
    assert validate_matcher_pattern("") is None


def test_exact_matcher_supports_pipe_alternatives() -> None:
    # Rust test: exact_matcher_supports_pipe_alternatives.
    assert matches_matcher("Edit|Write", "Edit")
    assert matches_matcher("Edit|Write", "Write")
    assert not matches_matcher("Edit|Write", "Bash")
    assert validate_matcher_pattern("Edit|Write") is None


def test_literal_matcher_uses_exact_matching() -> None:
    # Rust test: literal_matcher_uses_exact_matching.
    assert matches_matcher("Bash", "Bash")
    assert not matches_matcher("Bash", "BashOutput")
    assert matches_matcher(
        "mcp__memory__create_entities",
        "mcp__memory__create_entities",
    )
    assert not matches_matcher("mcp__memory", "mcp__memory__create_entities")
    assert validate_matcher_pattern("mcp__memory") is None


def test_matcher_uses_regex_when_it_contains_regex_characters() -> None:
    # Rust tests: matcher_uses_regex_when_it_contains_regex_characters,
    # mcp_matchers_support_regex_wildcards, and matcher_supports_anchored_regexes.
    assert matches_matcher("^Bash", "BashOutput")
    assert validate_matcher_pattern("^Bash") is None
    assert matches_matcher("mcp__memory__.*", "mcp__memory__create_entities")
    assert matches_matcher("mcp__.*__write.*", "mcp__filesystem__write_file")
    assert not matches_matcher("mcp__.*__write.*", "mcp__filesystem__read_file")
    assert validate_matcher_pattern("mcp__memory__.*") is None
    assert matches_matcher("^Bash$", "Bash")
    assert not matches_matcher("^Bash$", "BashOutput")
    assert validate_matcher_pattern("^Bash$") is None


def test_invalid_regex_is_rejected() -> None:
    # Rust test: invalid_regex_is_rejected.
    with pytest.raises(re.error):
        validate_matcher_pattern("[")
    assert not matches_matcher("[", "Bash")


def test_unsupported_events_ignore_matchers() -> None:
    # Rust test: unsupported_events_ignore_matchers.
    assert matcher_pattern_for_event(HookEventName.USER_PROMPT_SUBMIT, "^hello") is None
    assert matcher_pattern_for_event(HookEventName.STOP, "^done$") is None


def test_supported_events_keep_matchers() -> None:
    # Rust test: supported_events_keep_matchers.
    assert matcher_pattern_for_event(HookEventName.PRE_TOOL_USE, "Bash") == "Bash"
    assert matcher_pattern_for_event(HookEventName.POST_TOOL_USE, "Edit|Write") == "Edit|Write"
    assert matcher_pattern_for_event(HookEventName.SESSION_START, "startup|resume") == "startup|resume"
    assert matcher_pattern_for_event(HookEventName.PRE_COMPACT, "^auto$") == "^auto$"
    assert matcher_pattern_for_event(HookEventName.POST_COMPACT, "manual|auto") == "manual|auto"


def test_context_helpers_match_common_contracts() -> None:
    # Rust source contract: join_text_chunks, trimmed_non_empty,
    # append_additional_context, flatten_additional_contexts, matcher_inputs.
    assert join_text_chunks([]) is None
    assert join_text_chunks(["first", "second"]) == "first\n\nsecond"
    assert trimmed_non_empty("  hello  ") == "hello"
    assert trimmed_non_empty("   ") is None
    entries: list[HookOutputEntry] = []
    contexts: list[str] = []
    append_additional_context(entries, contexts, "remember this")
    assert entries == [HookOutputEntry(HookOutputEntryKind.CONTEXT, "remember this")]
    assert contexts == ["remember this"]
    assert flatten_additional_contexts([["a"], [], ["b", "c"]]) == ["a", "b", "c"]
    assert matcher_inputs("Bash", ["Shell", "Run"]) == ["Bash", "Shell", "Run"]


def test_tool_use_helpers_append_tool_use_id_to_run_and_event() -> None:
    # Rust source contract: hook_run_for_tool_use and
    # hook_completed_for_tool_use append :<tool_use_id> to the run id.
    run = _summary()
    event = HookCompletedEvent("turn-1", run)

    assert hook_run_for_tool_use(run, "tool-1").id == "pre-tool-use:0:/tmp/hooks.json:tool-1"
    completed = hook_completed_for_tool_use(event, "tool-1")

    assert completed.turn_id == "turn-1"
    assert completed.run.id == "pre-tool-use:0:/tmp/hooks.json:tool-1"
    assert event.run.id == "pre-tool-use:0:/tmp/hooks.json"


def test_serialization_failure_hook_events_use_failed_summary() -> None:
    # Rust source contract: serialization_failure_hook_events builds failed
    # completed events with completed_at = started_at, duration 0, and one
    # error entry.
    events = serialization_failure_hook_events(
        [_handler()],
        "turn-1",
        "serialize failed",
    )

    assert len(events) == 1
    assert events[0].turn_id == "turn-1"
    assert events[0].run.id == "pre-tool-use:0:/tmp/hooks.json"
    assert events[0].run.status == HookRunStatus.FAILED
    assert events[0].run.completed_at == 123
    assert events[0].run.duration_ms == 0
    assert events[0].run.entries == (
        HookOutputEntry(HookOutputEntryKind.ERROR, "serialize failed"),
    )


def test_serialization_failure_hook_events_for_tool_use_appends_tool_use_id() -> None:
    # Rust source contract: serialization_failure_hook_events_for_tool_use
    # applies hook_completed_for_tool_use to every generated event.
    events = serialization_failure_hook_events_for_tool_use(
        [_handler()],
        "turn-1",
        "serialize failed",
        "tool-1",
    )

    assert events[0].run.id == "pre-tool-use:0:/tmp/hooks.json:tool-1"
