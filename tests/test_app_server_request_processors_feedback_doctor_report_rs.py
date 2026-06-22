"""Rust parity tests for ``request_processors/feedback_doctor_report.rs``."""

from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace

from pycodex.app_server.request_processors_feedback_doctor_report import (
    DOCTOR_FEEDBACK_REPORT_TIMEOUT,
    MAX_DOCTOR_TAG_VALUE_LEN,
    doctor_feedback_report,
    doctor_report_tags,
    parse_doctor_report_stdout,
    truncate_tag_value,
)
from pycodex.feedback import DOCTOR_REPORT_ATTACHMENT_FILENAME


def test_doctor_report_tags_summarize_status_counts_like_rust() -> None:
    # Rust source: feedback_doctor_report.rs doctor_report_tags_summarize_status_counts.
    report = {
        "overallStatus": "fail",
        "checks": {
            "runtime.provenance": {"id": "runtime.provenance", "status": "ok"},
            "websocket.reachability": {"id": "websocket.reachability", "status": "warning"},
            "auth.credentials": {"id": "auth.credentials", "status": "fail"},
        },
    }

    assert doctor_report_tags(report) == {
        "doctor_fail_count": "1",
        "doctor_failed_checks": "auth.credentials",
        "doctor_ok_count": "1",
        "doctor_overall_status": "fail",
        "doctor_warning_checks": "websocket.reachability",
        "doctor_warning_count": "1",
    }


def test_doctor_report_tags_accept_array_checks_and_unknown_ids() -> None:
    # Rust source: check_values supports both object and array reports; missing id defaults to unknown.
    report = {
        "checks": [
            {"status": "warning"},
            {"id": "failed.one", "status": "fail"},
            {"id": "ignored", "status": "other"},
        ]
    }

    assert doctor_report_tags(report) == {
        "doctor_fail_count": "1",
        "doctor_failed_checks": "failed.one",
        "doctor_ok_count": "0",
        "doctor_warning_checks": "unknown",
        "doctor_warning_count": "1",
    }


def test_truncate_tag_value_matches_rust_limit_and_ellipsis() -> None:
    short = "x" * MAX_DOCTOR_TAG_VALUE_LEN
    long = "a" * (MAX_DOCTOR_TAG_VALUE_LEN + 10)

    assert truncate_tag_value(short) == short
    assert truncate_tag_value(long) == ("a" * (MAX_DOCTOR_TAG_VALUE_LEN - 3)) + "..."


def test_parse_doctor_report_stdout_uses_first_json_object() -> None:
    # Rust source: stdout before first `{` is ignored, and invalid/no JSON returns None.
    assert parse_doctor_report_stdout("noise\n{\"overallStatus\":\"ok\"}\n") == {"overallStatus": "ok"}
    assert parse_doctor_report_stdout("no json here") is None
    assert parse_doctor_report_stdout("{not json") is None


def test_doctor_feedback_report_builds_pretty_attachment_and_tags() -> None:
    async def runner(executable, timeout_seconds):
        assert str(executable) == "codex-test"
        assert timeout_seconds == DOCTOR_FEEDBACK_REPORT_TIMEOUT
        return 0, b'banner\n{"overallStatus":"warning","checks":[{"id":"c1","status":"warning"}]}', b""

    report = asyncio.run(
        doctor_feedback_report(SimpleNamespace(codex_self_exe="codex-test"), runner=runner)
    )

    assert report is not None
    assert report.attachment.filename == DOCTOR_REPORT_ATTACHMENT_FILENAME
    assert json.loads(report.attachment.data.decode("utf-8")) == {
        "overallStatus": "warning",
        "checks": [{"id": "c1", "status": "warning"}],
    }
    assert b'\n  "overallStatus": "warning"' in report.attachment.data
    assert report.tags["doctor_warning_checks"] == "c1"


def test_doctor_feedback_report_is_best_effort() -> None:
    invalid_calls: list[str] = []

    async def invalid_runner(executable, timeout_seconds):
        invalid_calls.append(str(executable))
        return 1, b"doctor failed", b"boom"

    async def failing_runner(executable, timeout_seconds):
        raise OSError("spawn failed")

    assert asyncio.run(doctor_feedback_report({}, runner=invalid_runner)) is None
    assert invalid_calls == [sys.executable]
    assert asyncio.run(
        doctor_feedback_report(SimpleNamespace(codex_self_exe="codex-test"), runner=invalid_runner)
    ) is None
    assert asyncio.run(
        doctor_feedback_report(SimpleNamespace(codex_self_exe="codex-test"), runner=failing_runner)
    ) is None
