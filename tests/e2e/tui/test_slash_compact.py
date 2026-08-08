"""End-to-end coverage for the ``/compact`` slash command."""

from __future__ import annotations

import json

import pytest

from pycodex.tui.chatwidget.slash_dispatch import terminal_slash_command_routes
from pycodex.tui.slash_command import SlashCommand
from tests.e2e.tui._slash_command_common import (
    python_slash_candidate,
    require_native_slash_comparison,
    require_python_slash_conpty,
    run_compact_slash_candidate,
    slash_candidate_pair,
)

pytestmark = pytest.mark.e2e

COMPACT_WARNING_PREFIX = "Heads up: Long threads and multiple compactions"
SEED_USER = "COMPACT_E2E_USER_BEFORE"
SEED_REPLY = "COMPACT_E2E_ASSISTANT_BEFORE"
SUMMARY = "COMPACT_E2E_SUMMARY"
FOLLOW_UP_USER = "COMPACT_E2E_USER_AFTER"
FOLLOW_UP_REPLY = "COMPACT_E2E_ASSISTANT_AFTER"


def test_compact_registry_contract() -> None:
    # Rust owners:
    # - chatwidget::slash_dispatch marks the task running and emits
    #   AppCommand::Compact.
    # - app::thread_routing invokes thread/compact/start.
    # - core::compact owns the standalone manual compaction turn.
    route = terminal_slash_command_routes()[SlashCommand.COMPACT]

    assert SlashCommand.COMPACT.command() == "compact"
    assert SlashCommand.COMPACT.supports_inline_args() is False
    assert SlashCommand.COMPACT.available_during_task() is False
    assert SlashCommand.COMPACT.available_in_side_conversation() is False
    assert route.outcome == "effect"
    assert route.argument_form == "bare"
    assert route.python_owner == "pycodex.tui.chatwidget.slash_dispatch"


def test_windows_conpty_native_and_python_compact_uses_dedicated_turn(tmp_path) -> None:
    native_exe = require_native_slash_comparison()
    rust, python = slash_candidate_pair(native_exe)

    parity_views: dict[str, tuple[object, ...]] = {}
    for label, command in (("rust", rust), ("python", python)):
        transcript, request_bodies = run_compact_slash_candidate(
            command,
            label=label,
            artifact_dir=tmp_path,
        )
        parity_views[label] = _assert_successful_compact(
            label,
            transcript,
            request_bodies,
        )

    assert parity_views["python"] == parity_views["rust"]


def test_windows_conpty_python_compact_completes_and_replaces_history(tmp_path) -> None:
    """Python regression must run without enabling native Rust comparison."""

    require_python_slash_conpty()
    transcript, request_bodies = run_compact_slash_candidate(
        python_slash_candidate(),
        label="python",
        artifact_dir=tmp_path,
    )

    _assert_successful_compact("python", transcript, request_bodies)


def test_windows_conpty_python_compact_failure_preserves_history_and_recovers_composer(
    tmp_path,
) -> None:
    """A failed compact turn must not report success or poison the next turn."""

    require_python_slash_conpty()
    failure = "COMPACT_E2E_STREAM_FAILURE"
    transcript, request_bodies = run_compact_slash_candidate(
        python_slash_candidate(),
        label="python-failure",
        artifact_dir=tmp_path,
        compact_failure_message=failure,
        include_rate_limit_headers=False,
    )

    output = transcript.normalized_stdout()
    requests = [json.loads(body.decode("utf-8")) for body in request_bodies]
    detail = (
        f"requests={len(requests)}\n"
        f"stdout={output}\n"
        f"stderr={transcript.normalized_stderr()}"
    )

    assert transcript.returncode == 0, detail
    assert len(requests) == 3, detail
    assert failure in output, detail
    assert "Context compacted" not in output, detail
    assert COMPACT_WARNING_PREFIX not in output, detail
    assert FOLLOW_UP_REPLY in output, detail
    assert all("/compact" not in json.dumps(request) for request in requests), detail

    follow_up_request = json.dumps(requests[2], ensure_ascii=False)
    assert SEED_USER in follow_up_request, detail
    assert SEED_REPLY in follow_up_request, detail
    assert SUMMARY not in follow_up_request, detail
    assert FOLLOW_UP_USER in follow_up_request, detail


def test_windows_conpty_python_compact_queues_follow_up_until_compaction_finishes(
    tmp_path,
) -> None:
    """Port Rust ``slash_compact_eagerly_queues_follow_up_before_turn_start``."""

    require_python_slash_conpty()
    transcript, request_bodies = run_compact_slash_candidate(
        python_slash_candidate(),
        label="python-queued",
        artifact_dir=tmp_path,
        queue_follow_up_during_compact=True,
    )

    _assert_successful_compact("python-queued", transcript, request_bodies)


def test_windows_conpty_python_repeated_compact_returns_to_ready_state(tmp_path) -> None:
    require_python_slash_conpty()
    transcript, request_bodies = run_compact_slash_candidate(
        python_slash_candidate(),
        label="python-repeated",
        artifact_dir=tmp_path,
        compact_repetitions=2,
    )

    _assert_successful_compact(
        "python-repeated",
        transcript,
        request_bodies,
        expected_request_count=4,
    )
    requests = [json.loads(body.decode("utf-8")) for body in request_bodies]
    second_compact_request = json.dumps(requests[2], ensure_ascii=False)
    assert SUMMARY in second_compact_request
    assert SEED_REPLY not in second_compact_request


def _assert_successful_compact(
    label: str,
    transcript: object,
    request_bodies: tuple[bytes, ...],
    *,
    expected_request_count: int = 3,
) -> tuple[object, ...]:
    output = transcript.normalized_stdout()
    combined = transcript.normalized_combined()
    requests = [json.loads(body.decode("utf-8")) for body in request_bodies]
    detail = (
        f"{label}: requests={len(requests)}\n"
        f"stdout={output}\n"
        f"stderr={transcript.normalized_stderr()}"
    )

    assert transcript.returncode == 0, detail
    assert len(requests) == expected_request_count, detail
    assert "/compact" in output, detail
    assert "Context compacted" in output, detail
    assert COMPACT_WARNING_PREFIX in output, detail
    assert FOLLOW_UP_REPLY in output, detail
    assert SUMMARY not in output, "compact summary must not render as an assistant turn\n" + detail
    for forbidden in (
        "new_rate_limits must be RateLimitSnapshot",
        "product effect is not yet available",
        "Traceback",
        "■",
    ):
        assert forbidden not in combined, f"unexpected {forbidden!r}\n{detail}"

    compact_request = json.dumps(requests[1], ensure_ascii=False)
    follow_up_request = json.dumps(requests[-1], ensure_ascii=False)
    assert SEED_USER in compact_request, detail
    assert SEED_REPLY in compact_request, detail
    assert all("/compact" not in json.dumps(request) for request in requests), detail
    assert SUMMARY in follow_up_request, detail
    assert FOLLOW_UP_USER in follow_up_request, detail
    assert SEED_REPLY not in follow_up_request, (
        "post-compact request retained the pre-compact assistant turn\n" + detail
    )

    return (
        len(requests),
        "Context compacted" in output,
        COMPACT_WARNING_PREFIX in output,
        SUMMARY in follow_up_request,
        SEED_REPLY not in follow_up_request,
        FOLLOW_UP_REPLY in output,
    )
