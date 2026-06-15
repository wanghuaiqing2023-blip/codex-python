from pathlib import Path
from types import SimpleNamespace

from pycodex.tui.render.highlight import (
    ANSI_ALPHA_DEFAULT,
    ANSI_ALPHA_INDEX,
    BUILTIN_THEME_NAMES,
    MAX_HIGHLIGHT_BYTES,
    MAX_HIGHLIGHT_LINES,
    OPAQUE_ALPHA,
    SemanticColor,
    SemanticStyle,
    ThemeEntry,
    diff_scope_background_rgbs_for_theme,
    foreground_style_for_scopes_with_theme,
    ansi_palette_color,
    convert_syntect_color,
    custom_theme_path,
    exceeds_highlight_limits,
    find_syntax,
    highlight_code_to_lines,
    highlight_code_to_styled_spans,
    load_custom_theme,
    list_available_themes,
    parse_theme_name,
    reconstructed,
    resolve_theme_by_name,
    validate_theme_name,
)


def _write_tmtheme(path: Path, extra_settings: str = "") -> None:
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>name</key><string>Test</string>
<key>settings</key><array>
<dict><key>settings</key><dict>
<key>foreground</key><string>#EEEEEE</string>
<key>background</key><string>#111111</string>
</dict></dict>
{extra_settings}
</array>
</dict></plist>""",
        encoding="utf-8",
    )


def test_theme_constants_and_builtin_names_match_rust_contract() -> None:
    """Rust: alpha sentinel constants and 32 bundled kebab-case theme names."""
    assert ANSI_ALPHA_INDEX == 0x00
    assert ANSI_ALPHA_DEFAULT == 0x01
    assert OPAQUE_ALPHA == 0xFF
    assert len(BUILTIN_THEME_NAMES) == 32
    assert BUILTIN_THEME_NAMES[0] == "1337"
    assert BUILTIN_THEME_NAMES[-1] == "zenburn"


def test_parse_and_resolve_builtin_theme_names() -> None:
    """Rust: parse_theme_name covers bundled names and rejects unknown names."""
    assert parse_theme_name("dracula") == "dracula"
    assert parse_theme_name("nonexistent-theme") is None
    assert resolve_theme_by_name("nord").name == "nord"
    assert resolve_theme_by_name("missing") is None


def test_custom_theme_path_validation_and_listing(tmp_path: Path) -> None:
    """Rust: custom themes must parse successfully to be accepted/listed."""
    themes = tmp_path / "themes"
    themes.mkdir()
    _write_tmtheme(themes / "valid-custom.tmTheme")
    (themes / "broken-custom.tmTheme").write_text("not a plist", encoding="utf-8")

    assert custom_theme_path("valid-custom", tmp_path) == themes / "valid-custom.tmTheme"
    assert validate_theme_name("valid-custom", tmp_path) is None
    assert "could not be loaded" in validate_theme_name("broken-custom", tmp_path)
    assert "not found" in validate_theme_name("missing-custom", tmp_path)

    entries = list_available_themes(tmp_path)
    assert ThemeEntry("valid-custom", True) in entries
    assert ThemeEntry("broken-custom", True) not in entries
    assert entries == sorted(entries, key=lambda entry: (entry.name.lower(), entry.name))


def test_custom_tmtheme_parser_extracts_scope_styles_and_diff_backgrounds(tmp_path: Path) -> None:
    """Rust: TextMate theme scopes provide foreground styles and diff backgrounds."""
    themes = tmp_path / "themes"
    themes.mkdir()
    _write_tmtheme(
        themes / "custom-diff.tmTheme",
        """
<dict><key>scope</key><string>keyword</string><key>settings</key><dict>
<key>foreground</key><string>#AABBCC</string><key>fontStyle</key><string>bold italic</string>
</dict></dict>
<dict><key>scope</key><string>markup.inserted</string><key>settings</key><dict>
<key>background</key><string>#102030</string>
</dict></dict>
<dict><key>scope</key><string>markup.deleted</string><key>settings</key><dict>
<key>background</key><string>#405060</string>
</dict></dict>
""",
    )

    theme = load_custom_theme("custom-diff", tmp_path)

    assert theme is not None
    assert theme.name == "custom-diff"
    assert theme.is_custom is True
    assert theme.path == themes / "custom-diff.tmTheme"
    assert theme.foregrounds["keyword"] == (170, 187, 204)
    assert theme.token_styles["keyword"] == SemanticStyle(
        fg=SemanticColor("rgb", (170, 187, 204)),
        bold=True,
        italic=True,
    )
    assert diff_scope_background_rgbs_for_theme(theme).inserted == (16, 32, 48)
    assert diff_scope_background_rgbs_for_theme(theme).deleted == (64, 80, 96)
    assert foreground_style_for_scopes_with_theme(theme, ["missing", "keyword"]) == theme.token_styles["keyword"]


def test_ansi_color_conversion_matches_rust_alpha_semantics() -> None:
    """Rust: alpha 0 indexes ANSI palette, alpha 1 means terminal default."""
    assert ansi_palette_color(0x07) == SemanticColor("named", "gray")
    assert ansi_palette_color(42) == SemanticColor("indexed", 42)
    assert convert_syntect_color(SimpleNamespace(r=2, g=0, b=0, a=ANSI_ALPHA_INDEX)) == SemanticColor(
        "named", "green"
    )
    assert convert_syntect_color(SimpleNamespace(r=1, g=2, b=3, a=ANSI_ALPHA_DEFAULT)) is None
    assert convert_syntect_color(SimpleNamespace(r=1, g=2, b=3, a=OPAQUE_ALPHA)) == SemanticColor(
        "rgb", (1, 2, 3)
    )
    assert convert_syntect_color(SimpleNamespace(r=1, g=2, b=3, a=0x80)) == SemanticColor(
        "rgb", (1, 2, 3)
    )


def test_find_syntax_aliases_and_unknown_language_fallback() -> None:
    """Rust: common languages/extensions and patched aliases resolve; unknown languages return None."""
    for name in ["rust", "rs", "python", "py", "markdown", "md", "csharp", "c-sharp", "golang", "python3", "shell"]:
        assert find_syntax(name) is not None
    assert find_syntax("xyzlang") is None
    assert highlight_code_to_styled_spans("x", "xyzlang") is None


def test_semantic_highlighting_styles_rust_keywords() -> None:
    """Python semantic slice: known languages return styled spans and preserve content."""
    lines = highlight_code_to_styled_spans("fn main() { let answer = 42; }", "rust")

    assert lines is not None
    assert reconstructed(lines) == "fn main() { let answer = 42; }"
    styled_tokens = [span.text for line in lines for span in line if span.style.bold]
    assert "fn" in styled_tokens
    assert "let" in styled_tokens


def test_highlight_limits_and_content_preserving_fallback() -> None:
    """Rust: highlight guardrails reject oversized snippets and fallback preserves code text."""
    assert exceeds_highlight_limits("x" * (MAX_HIGHLIGHT_BYTES + 1))
    assert exceeds_highlight_limits(("let x = 1;\n" * MAX_HIGHLIGHT_LINES) + "let x = 1;")

    code = "def hello():\n    print('hi')\n    return 42"
    lines = highlight_code_to_lines(code, "python")
    assert reconstructed(lines) == code
    assert len(lines) == 3

    markdown = "```sh\nprintf 'fenced within fenced\\n'\n```"
    assert reconstructed(highlight_code_to_lines(markdown, "markdown")) == markdown
    assert reconstructed(highlight_code_to_lines("a\r\nb\r\n", "python")) == "a\nb"
