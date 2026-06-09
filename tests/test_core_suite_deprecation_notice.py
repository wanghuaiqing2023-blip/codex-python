"""Rust integration parity for ``core/tests/suite/deprecation_notice.rs``.

The Rust integration tests wait for startup ``EventMsg::DeprecationNotice``
events after legacy feature flags are applied. Python keeps the same contract at
the feature-registry/protocol boundary: applying or recording legacy feature
usage yields the exact summary/details that should be emitted as a deprecation
notice event.
"""

from __future__ import annotations

import unittest

from pycodex.features import Feature, Features
from pycodex.protocol import DeprecationNoticeEvent, EventMsg


class DeprecationNoticeParityTests(unittest.TestCase):
    def test_emits_deprecation_notice_for_legacy_feature_flag(self) -> None:
        # Rust test: emits_deprecation_notice_for_legacy_feature_flag.
        features = Features.with_defaults()
        features.enable(Feature.UNIFIED_EXEC)
        features.record_legacy_usage_force("use_experimental_unified_exec_tool", Feature.UNIFIED_EXEC)

        notice = _single_notice_event(features).payload

        self.assertEqual(
            notice.summary,
            "`[features].use_experimental_unified_exec_tool` is deprecated. Use `[features].unified_exec` instead.",
        )
        self.assertEqual(
            notice.details,
            "Enable it with `--enable unified_exec` or `[features].unified_exec` in config.toml. "
            "See https://developers.openai.com/codex/config-basic#feature-flags for details.",
        )

    def test_emits_deprecation_notice_for_web_search_feature_flag_values(self) -> None:
        # Rust test: emits_deprecation_notice_for_web_search_feature_flag_values.
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                features = Features.with_defaults()
                features.apply_map({"web_search_request": enabled})

                notice = _single_notice_event(features).payload

                self.assertEqual(
                    notice.summary,
                    "`[features].web_search_request` is deprecated because web search is enabled by default.",
                )
                self.assertEqual(
                    notice.details,
                    "Set `web_search` to `\"live\"`, `\"cached\"`, or `\"disabled\"` at the top level "
                    "(or under a profile) in config.toml if you want to override it.",
                )

    def test_emits_deprecation_notice_for_use_legacy_landlock(self) -> None:
        # Rust test: emits_deprecation_notice_for_use_legacy_landlock.
        features = Features.with_defaults()
        features.apply_map({"use_legacy_landlock": True})

        notice = _single_notice_event(features).payload

        self.assertEqual(
            notice.summary,
            "`[features].use_legacy_landlock` is deprecated and will be removed soon.",
        )
        self.assertEqual(
            notice.details,
            "Remove this setting to stop opting into the legacy Linux sandbox behavior.",
        )


def _single_notice_event(features: Features) -> EventMsg:
    usages = features.legacy_feature_usages()
    assert len(usages) == 1
    usage = usages[0]
    event = EventMsg.with_payload(
        "deprecation_notice",
        DeprecationNoticeEvent(summary=usage.summary, details=usage.details),
    )
    assert event.type == "deprecation_notice"
    assert isinstance(event.payload, DeprecationNoticeEvent)
    return EventMsg.from_mapping(event.to_mapping())


if __name__ == "__main__":
    unittest.main()
