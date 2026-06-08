from __future__ import annotations

from datetime import timedelta
import logging
from pathlib import Path
import tempfile
import unittest

from pycodex.core.util import (
    FEEDBACK_TAGS_LOGGER_NAME,
    backoff,
    emit_feedback_auth_recovery_tags,
    error_or_panic,
    feedback_tags,
    normalize_thread_name,
    resolve_path,
)


class CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class UtilTests(unittest.TestCase):
    def test_backoff_matches_upstream_base_delays_without_jitter(self) -> None:
        self.assertEqual(backoff(0, jitter=1.0), timedelta(milliseconds=200))
        self.assertEqual(backoff(1, jitter=1.0), timedelta(milliseconds=200))
        self.assertEqual(backoff(3, jitter=1.0), timedelta(milliseconds=800))

    def test_backoff_applies_jitter_and_rejects_negative_attempts(self) -> None:
        self.assertEqual(backoff(2, jitter=0.9), timedelta(milliseconds=360))
        self.assertEqual(backoff(2, jitter=1.1), timedelta(milliseconds=440))
        with self.assertRaisesRegex(ValueError, "attempt must be non-negative"):
            backoff(-1)

    def test_resolve_path_matches_upstream_absolute_and_relative_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            absolute = base / "absolute.txt"

            self.assertEqual(resolve_path(base, absolute), absolute)
            self.assertEqual(resolve_path(base, Path("nested/file.txt")), base / "nested/file.txt")

    def test_normalize_thread_name_trims_and_rejects_empty(self) -> None:
        self.assertIsNone(normalize_thread_name("   "))
        self.assertEqual(normalize_thread_name("  my thread  "), "my thread")

    def test_feedback_tags_emits_stdlib_logging_record(self) -> None:
        logger = logging.getLogger(FEEDBACK_TAGS_LOGGER_NAME)
        handler = CaptureHandler()
        old_level = logger.level
        old_propagate = logger.propagate
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.addHandler(handler)
        try:
            tags = feedback_tags(model="gpt-5.2", cached=True)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
            logger.propagate = old_propagate

        self.assertEqual(tags, {"model": "gpt-5.2", "cached": True})
        self.assertEqual(len(handler.records), 1)
        self.assertEqual(
            getattr(handler.records[0], "feedback_tags"),
            {"model": "gpt-5.2", "cached": True},
        )

    def test_emit_feedback_auth_recovery_tags_clears_missing_401_fields(self) -> None:
        tags = emit_feedback_auth_recovery_tags(
            "managed",
            "done",
            "recovery_not_run",
            "req-401",
            None,
            None,
            None,
        )

        self.assertEqual(tags["auth_recovery_mode"], "managed")
        self.assertEqual(tags["auth_recovery_phase"], "done")
        self.assertEqual(tags["auth_recovery_outcome"], "recovery_not_run")
        self.assertEqual(tags["auth_401_request_id"], "req-401")
        self.assertEqual(tags["auth_401_cf_ray"], "")
        self.assertEqual(tags["auth_401_error"], "")
        self.assertEqual(tags["auth_401_error_code"], "")

    def test_emit_feedback_auth_recovery_tags_preserves_401_specific_fields(self) -> None:
        tags = emit_feedback_auth_recovery_tags(
            "managed",
            "refresh_token",
            "recovery_succeeded",
            "req-401",
            "ray-401",
            "missing_authorization_header",
            "token_expired",
        )

        self.assertEqual(
            tags,
            {
                "auth_recovery_mode": "managed",
                "auth_recovery_phase": "refresh_token",
                "auth_recovery_outcome": "recovery_succeeded",
                "auth_401_request_id": "req-401",
                "auth_401_cf_ray": "ray-401",
                "auth_401_error": "missing_authorization_header",
                "auth_401_error_code": "token_expired",
            },
        )

    def test_error_or_panic_raises_in_debug_and_logs_otherwise(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "boom"):
            error_or_panic("boom", debug_assertions=True)

        with self.assertLogs("pycodex.core.util", level="ERROR") as captured:
            error_or_panic("logged", debug_assertions=False)
        self.assertEqual(captured.output, ["ERROR:pycodex.core.util:logged"])


if __name__ == "__main__":
    unittest.main()
