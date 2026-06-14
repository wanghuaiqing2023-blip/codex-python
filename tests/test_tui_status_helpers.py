"""Parity tests for codex-rs/tui/src/status/helpers.rs."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pycodex.tui.status.account import StatusAccountDisplay
from pycodex.tui.status.helpers import (
    compose_account_display,
    compose_agents_summary,
    compose_model_display,
    format_directory_display,
    format_reset_timestamp,
    format_tokens_compact,
    plan_type_display_name,
    title_case,
)


@dataclass
class Config:
    cwd: Path


def test_compose_model_display_collects_reasoning_details():
    assert compose_model_display(
        "gpt-5",
        [("reasoning effort", "HIGH"), ("reasoning summaries", "Off")],
    ) == ("gpt-5", ["reasoning high", "summaries off"])
    assert compose_model_display("gpt-5", [("reasoning summaries", "Detailed")]) == (
        "gpt-5",
        ["summaries detailed"],
    )


def test_compose_agents_summary_matches_rust_relative_display_rules():
    config = Config(cwd=Path("/workspace/project"))

    assert compose_agents_summary(config, []) == "<none>"
    assert compose_agents_summary(config, [Path("/workspace/project/AGENTS.md")]) == "AGENTS.md"
    assert compose_agents_summary(config, [Path("/workspace/AGENTS.md")]) == "../AGENTS.md"
    assert compose_agents_summary(config, [Path("/other/AGENTS.md")]) == "/other/AGENTS.md"
    assert compose_agents_summary(
        config,
        [Path("/other/AGENTS.md"), Path("/workspace/project/AGENTS.md")],
    ) == "/other/AGENTS.md, AGENTS.md"


def test_compose_account_display_clones_semantic_value_by_identity_boundary():
    account = StatusAccountDisplay.api_key()

    assert compose_account_display(account) == account
    assert compose_account_display(None) is None


def test_plan_type_display_name_remaps_display_labels():
    cases = {
        "Free": "Free",
        "Go": "Go",
        "Plus": "Plus",
        "Pro": "Pro",
        "ProLite": "Pro Lite",
        "Team": "Business",
        "SelfServeBusinessUsageBased": "Business",
        "Business": "Enterprise",
        "EnterpriseCbpUsageBased": "Enterprise",
        "Enterprise": "Enterprise",
        "Edu": "Edu",
        "Unknown": "Unknown",
    }
    for plan_type, expected in cases.items():
        assert plan_type_display_name(plan_type) == expected


def test_format_tokens_compact_matches_scaled_suffix_rules():
    assert format_tokens_compact(-5) == "0"
    assert format_tokens_compact(999) == "999"
    assert format_tokens_compact(1_234) == "1.23K"
    assert format_tokens_compact(12_340) == "12.3K"
    assert format_tokens_compact(123_400) == "123K"
    assert format_tokens_compact(1_250_000) == "1.25M"
    assert format_tokens_compact(2_000_000_000) == "2B"
    assert format_tokens_compact(3_500_000_000_000) == "3.5T"


def test_format_directory_display_relativizes_home_and_truncates_when_requested(monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: Path("/home/user")))

    assert format_directory_display(Path("/home/user"), None) == "~"
    assert format_directory_display(Path("/home/user/project"), None) == "~/project"
    assert format_directory_display(Path("/tmp/project"), 0) == ""
    assert len(format_directory_display(Path("/tmp/some/very/long/project"), 10)) <= 10


def test_format_reset_timestamp_uses_date_only_when_needed():
    captured = datetime(2026, 6, 12, 10, 0)

    assert format_reset_timestamp(datetime(2026, 6, 12, 11, 5), captured) == "11:05"
    assert format_reset_timestamp(datetime(2026, 6, 13, 9, 1), captured) == "09:01 on 13 Jun"


def test_title_case_matches_rust_ascii_lowercase_rest_behavior():
    assert title_case("") == ""
    assert title_case("PROLITE") == "Prolite"
    assert title_case("unknown") == "Unknown"
