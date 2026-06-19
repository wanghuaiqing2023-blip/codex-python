"""Feedback doctor-report attachment helper.

Ported from ``codex-app-server/src/request_processors/feedback_doctor_report.rs``.
The Rust helper is best-effort: run ``codex doctor --json``, accept only valid
JSON beginning at the first ``{`` in stdout, pretty-print it as an attachment,
and derive a small set of Sentry-friendly tags from report status/checks.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.feedback import DOCTOR_REPORT_ATTACHMENT_FILENAME, FeedbackAttachment

JsonValue = Any
DOCTOR_FEEDBACK_REPORT_TIMEOUT = 25.0
MAX_DOCTOR_TAG_VALUE_LEN = 256

DoctorCommandRunner = Callable[[Path, float], Awaitable[tuple[int | None, bytes, bytes]]]


@dataclass(frozen=True)
class DoctorFeedbackReport:
    attachment: FeedbackAttachment
    tags: dict[str, str]


async def doctor_feedback_report(config: Any, *, runner: DoctorCommandRunner | None = None) -> DoctorFeedbackReport | None:
    executable = _codex_executable(config)
    if executable is None:
        return None
    runner = runner or _run_doctor_command
    try:
        _status, stdout, _stderr = await runner(executable, DOCTOR_FEEDBACK_REPORT_TIMEOUT)
    except Exception:
        return None

    report = parse_doctor_report_stdout(stdout)
    if report is None:
        return None
    pretty = json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8")
    return DoctorFeedbackReport(
        attachment=FeedbackAttachment(
            filename=DOCTOR_REPORT_ATTACHMENT_FILENAME,
            data=pretty,
        ),
        tags=doctor_report_tags(report),
    )


def parse_doctor_report_stdout(stdout: bytes | str) -> JsonValue | None:
    text = stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else stdout
    json_start = text.find("{")
    if json_start < 0:
        return None
    raw_json = text[json_start:].strip()
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        return None


def doctor_report_tags(report: JsonValue) -> dict[str, str]:
    tags: dict[str, str] = {}
    if isinstance(report, Mapping):
        overall_status = report.get("overallStatus")
        if isinstance(overall_status, str):
            tags["doctor_overall_status"] = truncate_tag_value(overall_status)

        ok_count = 0
        warning_count = 0
        fail_count = 0
        failed_checks: list[str] = []
        warning_checks: list[str] = []
        for check in check_values(report.get("checks")):
            status = check.get("status")
            check_id = check.get("id") if isinstance(check.get("id"), str) else "unknown"
            if status == "ok":
                ok_count += 1
            elif status == "warning":
                warning_count += 1
                warning_checks.append(check_id)
            elif status == "fail":
                fail_count += 1
                failed_checks.append(check_id)
    else:
        ok_count = warning_count = fail_count = 0
        failed_checks = []
        warning_checks = []

    tags["doctor_ok_count"] = str(ok_count)
    tags["doctor_warning_count"] = str(warning_count)
    tags["doctor_fail_count"] = str(fail_count)
    if failed_checks:
        tags["doctor_failed_checks"] = truncate_tag_value(",".join(failed_checks))
    if warning_checks:
        tags["doctor_warning_checks"] = truncate_tag_value(",".join(warning_checks))
    return dict(sorted(tags.items()))


def check_values(checks: JsonValue) -> list[Mapping[str, JsonValue]]:
    if isinstance(checks, Mapping):
        values = checks.values()
    elif isinstance(checks, list):
        values = checks
    else:
        return []
    return [value for value in values if isinstance(value, Mapping)]


def truncate_tag_value(value: str) -> str:
    if len(value) <= MAX_DOCTOR_TAG_VALUE_LEN:
        return value
    return value[: MAX_DOCTOR_TAG_VALUE_LEN - 3] + "..."


def _codex_executable(config: Any) -> Path | None:
    value = getattr(config, "codex_self_exe", None)
    if value is None and isinstance(config, Mapping):
        value = config.get("codex_self_exe") or config.get("codexSelfExe")
    if value is None:
        value = sys.executable
    return Path(value)


async def _run_doctor_command(executable: Path, timeout_seconds: float) -> tuple[int | None, bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        str(executable),
        "doctor",
        "--json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    return process.returncode, stdout, stderr


__all__ = [
    "DOCTOR_FEEDBACK_REPORT_TIMEOUT",
    "MAX_DOCTOR_TAG_VALUE_LEN",
    "DoctorFeedbackReport",
    "check_values",
    "doctor_feedback_report",
    "doctor_report_tags",
    "parse_doctor_report_stdout",
    "truncate_tag_value",
]
