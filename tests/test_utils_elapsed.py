from __future__ import annotations

from datetime import timedelta
import unittest

from pycodex.utils.elapsed import format_duration


class ElapsedFormattingTests(unittest.TestCase):
    def test_format_duration_subsecond(self) -> None:
        # Source: codex/codex-rs/utils/elapsed/src/lib.rs
        # Rust crate: codex-utils-elapsed
        # Rust test: tests::test_format_duration_subsecond
        # Contract: durations below one second render as integer milliseconds.
        self.assertEqual(format_duration(timedelta(milliseconds=250)), "250ms")
        self.assertEqual(format_duration(timedelta(milliseconds=0)), "0ms")

    def test_format_duration_seconds(self) -> None:
        # Source: codex/codex-rs/utils/elapsed/src/lib.rs
        # Rust test: tests::test_format_duration_seconds
        # Contract: 1s inclusive to 60s exclusive renders seconds with two decimals.
        self.assertEqual(format_duration(timedelta(milliseconds=1_500)), "1.50s")
        self.assertEqual(format_duration(timedelta(milliseconds=59_999)), "60.00s")

    def test_format_duration_minutes(self) -> None:
        # Source: codex/codex-rs/utils/elapsed/src/lib.rs
        # Rust test: tests::test_format_duration_minutes
        # Contract: durations at or above one minute render minutes plus zero-padded seconds.
        self.assertEqual(format_duration(timedelta(milliseconds=75_000)), "1m 15s")
        self.assertEqual(format_duration(timedelta(milliseconds=60_000)), "1m 00s")
        self.assertEqual(format_duration(timedelta(milliseconds=3_601_000)), "60m 01s")

    def test_format_duration_one_hour_has_space(self) -> None:
        # Source: codex/codex-rs/utils/elapsed/src/lib.rs
        # Rust test: tests::test_format_duration_one_hour_has_space
        self.assertEqual(format_duration(timedelta(milliseconds=3_600_000)), "60m 00s")

    def test_format_duration_truncates_sub_millisecond_like_duration_as_millis(self) -> None:
        # Source: codex/codex-rs/utils/elapsed/src/lib.rs
        # Contract: Rust Duration::as_millis truncates fractional milliseconds.
        self.assertEqual(format_duration(timedelta(microseconds=999)), "0ms")
        self.assertEqual(format_duration(timedelta(milliseconds=999, microseconds=999)), "999ms")

    def test_format_duration_rejects_python_invalid_boundaries(self) -> None:
        with self.assertRaisesRegex(TypeError, "duration must be a datetime.timedelta"):
            format_duration(1000)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "duration must be non-negative"):
            format_duration(timedelta(milliseconds=-1))


if __name__ == "__main__":
    unittest.main()
