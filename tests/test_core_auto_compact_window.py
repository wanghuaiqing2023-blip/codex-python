import unittest

from pycodex.core import (
    AutoCompactWindow,
    AutoCompactWindowPrefillKind,
    AutoCompactWindowSnapshot,
)
from pycodex.protocol import TokenUsage


class AutoCompactWindowTests(unittest.TestCase):
    def test_tracks_prefill_and_window_boundaries(self) -> None:
        window = AutoCompactWindow()

        self.assertEqual(
            window.snapshot(),
            AutoCompactWindowSnapshot(ordinal=1, prefill_input_tokens=None),
        )

        window.set_estimated_prefill(150)
        self.assertEqual(
            window.snapshot(),
            AutoCompactWindowSnapshot(ordinal=1, prefill_input_tokens=150),
        )
        self.assertIs(window.prefill_input_tokens.kind, AutoCompactWindowPrefillKind.ESTIMATED)

        window.ensure_server_observed_prefill_from_usage(
            TokenUsage(input_tokens=120, total_tokens=170)
        )
        self.assertEqual(
            window.snapshot(),
            AutoCompactWindowSnapshot(ordinal=1, prefill_input_tokens=120),
        )
        self.assertIs(
            window.prefill_input_tokens.kind,
            AutoCompactWindowPrefillKind.SERVER_OBSERVED,
        )

        window.ensure_server_observed_prefill_from_usage(
            TokenUsage(input_tokens=130, total_tokens=180)
        )
        window.set_estimated_prefill(90)
        self.assertEqual(
            window.snapshot(),
            AutoCompactWindowSnapshot(ordinal=1, prefill_input_tokens=120),
        )

        window.start_next()
        self.assertEqual(
            window.snapshot(),
            AutoCompactWindowSnapshot(ordinal=2, prefill_input_tokens=None),
        )

    def test_estimated_prefill_clamps_negative_values(self) -> None:
        window = AutoCompactWindow()

        window.set_estimated_prefill(-10)

        self.assertEqual(window.snapshot().prefill_input_tokens, 0)

    def test_server_observed_prefill_clamps_negative_values(self) -> None:
        window = AutoCompactWindow()

        window.ensure_server_observed_prefill_from_usage(TokenUsage(input_tokens=-12))

        self.assertEqual(window.snapshot().prefill_input_tokens, 0)

    def test_start_next_saturates_u64_ordinal_and_clears_prefill(self) -> None:
        window = AutoCompactWindow()
        window.ordinal = (1 << 64) - 1
        window.set_estimated_prefill(10)

        window.start_next()

        self.assertEqual(window.snapshot(), AutoCompactWindowSnapshot((1 << 64) - 1, None))

    def test_clear_prefill_keeps_window_ordinal(self) -> None:
        window = AutoCompactWindow()
        window.start_next()
        window.set_estimated_prefill(20)

        window.clear_prefill()

        self.assertEqual(window.snapshot(), AutoCompactWindowSnapshot(2, None))


if __name__ == "__main__":
    unittest.main()
