from __future__ import annotations

import random
from datetime import date

from pycodex.tui.tooltips import (
    FAST_TOOLTIP,
    FREE_GO_TOOLTIP,
    OTHER_TOOLTIP_NON_MAC,
    TargetOs,
    announcement_tip_toml_bad_deserialization,
    announcement_tip_toml_matches_target_os,
    announcement_tip_toml_matches_target_plan_type,
    announcement_tip_toml_parse_comments,
    announcement_tip_toml_picks_last_matching,
    announcement_tip_toml_picks_no_match,
    announcement_tip_toml_rejects_unknown_target_os,
    announcement_tip_toml_rejects_unknown_target_plan_type,
    get_tooltip,
    load_raw_tooltips,
    paid_tooltip_pool_rotates_between_promos,
    paid_tooltip_pool_skips_fast_when_fast_mode_is_enabled,
    parse_announcement_tip_toml,
    pick_paid_tooltip,
    pick_tooltip,
    random_tooltip_is_reproducible_with_seed,
    random_tooltip_returns_some_tip_when_available,
    tooltips,
)


def test_random_tooltip_returns_some_tip_when_available() -> None:
    random_tooltip_returns_some_tip_when_available()


def test_random_tooltip_is_reproducible_with_seed() -> None:
    random_tooltip_is_reproducible_with_seed()


def test_paid_tooltip_pool_rotates_between_promos() -> None:
    paid_tooltip_pool_rotates_between_promos()


def test_paid_tooltip_pool_skips_fast_when_fast_mode_is_enabled() -> None:
    paid_tooltip_pool_skips_fast_when_fast_mode_is_enabled()


def test_announcement_tip_toml_picks_last_matching() -> None:
    announcement_tip_toml_picks_last_matching()


def test_announcement_tip_toml_picks_no_match() -> None:
    announcement_tip_toml_picks_no_match()


def test_announcement_tip_toml_bad_deserialization() -> None:
    announcement_tip_toml_bad_deserialization()


def test_announcement_tip_toml_parse_comments() -> None:
    announcement_tip_toml_parse_comments()


def test_announcement_tip_toml_matches_target_plan_type() -> None:
    announcement_tip_toml_matches_target_plan_type()


def test_announcement_tip_toml_rejects_unknown_target_plan_type() -> None:
    announcement_tip_toml_rejects_unknown_target_plan_type()


def test_announcement_tip_toml_matches_target_os() -> None:
    announcement_tip_toml_matches_target_os()


def test_announcement_tip_toml_rejects_unknown_target_os() -> None:
    announcement_tip_toml_rejects_unknown_target_os()


def test_parse_announcement_tip_toml_accepts_array_root_shape() -> None:
    text = '[{content = "first"}, {content = "second"}]'

    assert parse_announcement_tip_toml(text) == "second"


def test_parse_announcement_tip_toml_date_and_version_boundaries() -> None:
    text = """
[[announcements]]
content = "old"
from_date = "2024-01-01"
to_date = "2024-02-01"

[[announcements]]
content = "current"
from_date = "2024-02-01"
to_date = "2024-03-01"
version_regex = "^1\\.2\\."
"""

    assert parse_announcement_tip_toml(text, today=date(2024, 2, 1), version="1.2.3") == "current"
    assert parse_announcement_tip_toml(text, today=date(2024, 3, 1), version="1.2.3") is None
    assert parse_announcement_tip_toml(text, today=date(2024, 2, 1), version="2.0.0") is None


def test_get_tooltip_prefers_announcement_then_plan_specific_paths() -> None:
    assert get_tooltip("free", rng=random.Random(1), announcement_text="announcement") == "announcement"
    assert get_tooltip("free", rng=random.Random(1), announcement_text=None) == FREE_GO_TOOLTIP
    assert get_tooltip(None, rng=random.Random(1), announcement_text=None) == OTHER_TOOLTIP_NON_MAC


def test_free_go_tooltip_matches_rust_text() -> None:
    # Rust source contract:
    # codex-tui/src/tooltips.rs::FREE_GO_TOOLTIP uses an en dash and curly
    # apostrophe, not mojibake replacement text.
    assert FREE_GO_TOOLTIP == "*New* For a limited time, Codex is included in your plan for free – let’s build together."


def test_pick_paid_tooltip_suppresses_fast_when_enabled() -> None:
    assert pick_paid_tooltip(random.Random(1), True) is not FAST_TOOLTIP


def test_tooltips_filters_empty_comments_and_non_platform_codex_app_tip() -> None:
    values = tooltips()

    assert values
    assert all(value and not value.startswith("#") for value in values)


def test_load_raw_tooltips_uses_supplied_catalog_path(tmp_path) -> None:
    catalog = tmp_path / "tooltips.txt"
    catalog.write_text("# comment\n  hello tip  \n", encoding="utf-8")

    assert load_raw_tooltips(catalog) == "# comment\n  hello tip  \n"


def test_pick_tooltip_uses_seeded_rng() -> None:
    assert pick_tooltip(random.Random(7)) == pick_tooltip(random.Random(7))
