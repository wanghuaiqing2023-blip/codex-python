"""Rust-derived tests for ``codex-api/src/rate_limits.rs``."""

from __future__ import annotations

import unittest

from pycodex.codex_api import CreditsSnapshot
from pycodex.codex_api import RateLimitError
from pycodex.codex_api import RateLimitSnapshot
from pycodex.codex_api import RateLimitWindow
from pycodex.codex_api import parse_all_rate_limits
from pycodex.codex_api import parse_default_rate_limit
from pycodex.codex_api import parse_promo_message
from pycodex.codex_api import parse_rate_limit_event
from pycodex.codex_api import parse_rate_limit_for_limit
from pycodex.codex_api import parse_rate_limit_reached_type


class CodexApiRateLimitsRsTests(unittest.TestCase):
    def test_parse_rate_limit_for_limit_defaults_to_codex_headers(self) -> None:
        # Rust test: parse_rate_limit_for_limit_defaults_to_codex_headers.
        snapshot = parse_rate_limit_for_limit(
            {
                "x-codex-primary-used-percent": "12.5",
                "x-codex-primary-window-minutes": "60",
                "x-codex-primary-reset-at": "1704069000",
            },
            None,
        )

        self.assertEqual(snapshot.limit_id, "codex")
        self.assertIsNone(snapshot.limit_name)
        self.assertEqual(
            snapshot.primary,
            RateLimitWindow(
                used_percent=12.5,
                window_minutes=60,
                resets_at=1704069000,
            ),
        )

    def test_parse_rate_limit_for_limit_reads_secondary_headers(self) -> None:
        # Rust test: parse_rate_limit_for_limit_reads_secondary_headers.
        snapshot = parse_rate_limit_for_limit(
            {
                "x-codex-secondary-primary-used-percent": "80",
                "x-codex-secondary-primary-window-minutes": "1440",
                "x-codex-secondary-primary-reset-at": "1704074400",
            },
            "codex_secondary",
        )

        self.assertEqual(snapshot.limit_id, "codex_secondary")
        self.assertIsNone(snapshot.limit_name)
        self.assertEqual(
            snapshot.primary,
            RateLimitWindow(
                used_percent=80.0,
                window_minutes=1440,
                resets_at=1704074400,
            ),
        )
        self.assertIsNone(snapshot.secondary)

    def test_parse_rate_limit_for_limit_prefers_limit_name_header(self) -> None:
        # Rust test: parse_rate_limit_for_limit_prefers_limit_name_header.
        snapshot = parse_rate_limit_for_limit(
            {
                "x-codex-bengalfox-primary-used-percent": "80",
                "x-codex-bengalfox-limit-name": "gpt-5.2-codex-sonic",
            },
            "codex_bengalfox",
        )

        self.assertEqual(snapshot.limit_id, "codex_bengalfox")
        self.assertEqual(snapshot.limit_name, "gpt-5.2-codex-sonic")

    def test_parse_all_rate_limits_reads_all_limit_families(self) -> None:
        # Rust test: parse_all_rate_limits_reads_all_limit_families.
        updates = parse_all_rate_limits(
            {
                "x-codex-primary-used-percent": "12.5",
                "x-codex-secondary-primary-used-percent": "80",
            }
        )

        self.assertEqual(len(updates), 2)
        self.assertEqual(updates[0].limit_id, "codex")
        self.assertEqual(updates[1].limit_id, "codex_secondary")
        self.assertIsNone(updates[0].limit_name)
        self.assertIsNone(updates[1].limit_name)

    def test_parse_all_rate_limits_includes_default_codex_snapshot(self) -> None:
        # Rust test: parse_all_rate_limits_includes_default_codex_snapshot.
        updates = parse_all_rate_limits({})

        self.assertEqual(
            updates,
            [
                RateLimitSnapshot(
                    limit_id="codex",
                    limit_name=None,
                    primary=None,
                    secondary=None,
                    credits=None,
                )
            ],
        )

    def test_parse_event_payload_maps_windows_credits_and_limit_name(self) -> None:
        # Rust crate/module: codex-api/src/rate_limits.rs
        # Contract: parse_rate_limit_event accepts codex.rate_limits events,
        # maps primary/secondary windows, credits, plan_type, and normalizes
        # metered limit names.
        snapshot = parse_rate_limit_event(
            """
            {
              "type": "codex.rate_limits",
              "plan_type": "plus",
              "metered_limit_name": "Codex-Secondary",
              "rate_limits": {
                "primary": {
                  "used_percent": 75.5,
                  "window_minutes": 1440,
                  "reset_at": 1704074400
                },
                "secondary": {
                  "used_percent": 10.0
                }
              },
              "credits": {
                "has_credits": true,
                "unlimited": false,
                "balance": "12"
              }
            }
            """
        )

        self.assertEqual(snapshot.limit_id, "codex_secondary")
        self.assertEqual(snapshot.plan_type, "plus")
        self.assertEqual(
            snapshot.primary,
            RateLimitWindow(75.5, window_minutes=1440, resets_at=1704074400),
        )
        self.assertEqual(snapshot.secondary, RateLimitWindow(10.0))
        self.assertEqual(snapshot.credits, CreditsSnapshot(True, False, "12"))

    def test_parse_event_payload_uses_legacy_limit_name_fallback(self) -> None:
        # Rust crate/module: codex-api/src/rate_limits.rs
        # Contract: parse_rate_limit_event uses metered_limit_name first and
        # falls back to legacy limit_name before defaulting to codex.
        snapshot = parse_rate_limit_event(
            '{"type":"codex.rate_limits","limit_name":"Codex-Legacy"}'
        )

        self.assertEqual(snapshot.limit_id, "codex_legacy")

    def test_parse_event_payload_rejects_non_bool_credits(self) -> None:
        # Rust crate/module: codex-api/src/rate_limits.rs
        # Contract: serde_json parses RateLimitEventCredits bool fields
        # strictly, so string booleans reject the whole event.
        self.assertIsNone(
            parse_rate_limit_event(
                """
                {
                  "type": "codex.rate_limits",
                  "credits": {
                    "has_credits": "false",
                    "unlimited": false
                  }
                }
                """
            )
        )

    def test_parse_helpers_match_rust_private_branches(self) -> None:
        # Rust crate/module: codex-api/src/rate_limits.rs
        # Contract: helper branches trim promo messages, parse bool credits,
        # ignore zero-only windows, reject non-finite floats, and surface
        # reached-type header values.
        headers = {
            "x-codex-primary-used-percent": "0",
            "x-codex-primary-window-minutes": "0",
            "x-codex-credits-has-credits": "1",
            "x-codex-credits-unlimited": "false",
            "x-codex-credits-balance": "  ",
            "x-codex-promo-message": "  upgrade soon  ",
            "x-codex-rate-limit-reached-type": " primary ",
        }

        snapshot = parse_default_rate_limit(headers)

        self.assertIsNone(snapshot.primary)
        self.assertEqual(snapshot.credits, CreditsSnapshot(True, False, None))
        self.assertEqual(parse_promo_message(headers), "upgrade soon")
        self.assertIsNone(parse_rate_limit_reached_type(headers))
        self.assertEqual(
            parse_rate_limit_reached_type(
                {
                    "x-codex-rate-limit-reached-type": (
                        " workspace_member_usage_limit_reached "
                    )
                }
            ),
            "workspace_member_usage_limit_reached",
        )
        self.assertIsNone(parse_rate_limit_for_limit({"x-codex-primary-used-percent": "inf"}).primary)
        self.assertIsNone(parse_rate_limit_event("{not-json"))
        self.assertIsNone(parse_rate_limit_event('{"type":"other"}'))

    def test_rate_limit_error_display_is_message_only(self) -> None:
        # Rust crate/module: codex-api/src/rate_limits.rs
        # Contract: RateLimitError Display writes only message.
        self.assertEqual(str(RateLimitError("limited")), "limited")


if __name__ == "__main__":
    unittest.main()
