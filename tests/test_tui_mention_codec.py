"""Parity tests for Rust ``codex-tui::mention_codec``.

Rust source: ``codex/codex-rs/tui/src/mention_codec.rs``.
"""

from pycodex.tui.mention_codec import (
    DecodedHistoryText,
    LinkedMention,
    decode_history_mentions,
    encode_history_mentions,
    is_common_env_var,
    is_tool_path,
)


def test_decode_history_mentions_restores_visible_tokens() -> None:
    decoded = decode_history_mentions(
        "Use [$figma](app://figma-1), [$sample](plugin://sample@test), and [$figma](/tmp/figma/SKILL.md)."
    )
    assert decoded == DecodedHistoryText(
        text="Use $figma, $sample, and $figma.",
        mentions=[
            LinkedMention("figma", "app://figma-1"),
            LinkedMention("sample", "plugin://sample@test"),
            LinkedMention("figma", "/tmp/figma/SKILL.md"),
        ],
    )


def test_decode_history_mentions_restores_plugin_links_with_at_sigil() -> None:
    decoded = decode_history_mentions("Use [@sample](plugin://sample@test) and [$figma](app://figma-1).")
    assert decoded == DecodedHistoryText(
        text="Use $sample and $figma.",
        mentions=[
            LinkedMention("sample", "plugin://sample@test"),
            LinkedMention("figma", "app://figma-1"),
        ],
    )


def test_decode_history_mentions_ignores_at_sigil_for_non_plugin_paths() -> None:
    decoded = decode_history_mentions("Use [@figma](app://figma-1).")
    assert decoded == DecodedHistoryText(text="Use [@figma](app://figma-1).", mentions=[])


def test_encode_history_mentions_links_bound_mentions_in_order() -> None:
    encoded = encode_history_mentions(
        "$figma then $sample then $figma then $other",
        [
            LinkedMention("figma", "app://figma-app"),
            LinkedMention("sample", "plugin://sample@test"),
            LinkedMention("figma", "/tmp/figma/SKILL.md"),
        ],
    )
    assert encoded == (
        "[$figma](app://figma-app) then [$sample](plugin://sample@test) "
        "then [$figma](/tmp/figma/SKILL.md) then $other"
    )


def test_decode_history_mentions_filters_env_vars_and_non_tool_paths() -> None:
    assert decode_history_mentions("[$PATH](app://path)").mentions == []
    assert decode_history_mentions("[$foo](/tmp/not-a-skill.txt)").mentions == []


def test_tool_path_accepts_known_schemes_and_skill_md() -> None:
    assert is_tool_path("app://figma")
    assert is_tool_path("mcp://server/tool")
    assert is_tool_path("plugin://sample@test")
    assert is_tool_path("skill://writer")
    assert is_tool_path(r"C:\tmp\SKILL.md")
    assert not is_tool_path("/tmp/README.md")
    assert is_common_env_var("path")
