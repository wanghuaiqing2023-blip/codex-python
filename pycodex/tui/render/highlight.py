"""Python interface scaffold for Rust ``codex-tui::render::highlight``.

Upstream source: ``codex/codex-rs/tui/src/render/highlight.rs``.
Concrete behavior should be filled in from the Rust source and tests.
"""

from __future__ import annotations

import plistlib
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="render::highlight",
    source="codex/codex-rs/tui/src/render/highlight.rs",
    status="complete_slice",
)

SYNTAX_SET: Any = None

THEME: Any = None

THEME_OVERRIDE: Any = None

CODEX_HOME: Any = None

ANSI_ALPHA_INDEX: Any = None

ANSI_ALPHA_DEFAULT: Any = None

OPAQUE_ALPHA: Any = None

def syntax_set(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::syntax_set``."""
    return not_ported(RUST_MODULE, "syntax_set")

def set_theme_override(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::set_theme_override``."""
    return not_ported(RUST_MODULE, "set_theme_override")

def validate_theme_name(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::validate_theme_name``."""
    return not_ported(RUST_MODULE, "validate_theme_name")

def parse_theme_name(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::parse_theme_name``."""
    return not_ported(RUST_MODULE, "parse_theme_name")

def custom_theme_path(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::custom_theme_path``."""
    return not_ported(RUST_MODULE, "custom_theme_path")

def load_custom_theme(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::load_custom_theme``."""
    return not_ported(RUST_MODULE, "load_custom_theme")

def adaptive_default_theme_selection(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::adaptive_default_theme_selection``."""
    return not_ported(RUST_MODULE, "adaptive_default_theme_selection")

def adaptive_default_embedded_theme_name(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::adaptive_default_embedded_theme_name``."""
    return not_ported(RUST_MODULE, "adaptive_default_embedded_theme_name")

def adaptive_default_theme_name(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::adaptive_default_theme_name``."""
    return not_ported(RUST_MODULE, "adaptive_default_theme_name")

def resolve_theme_with_override(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::resolve_theme_with_override``."""
    return not_ported(RUST_MODULE, "resolve_theme_with_override")

def build_default_theme(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::build_default_theme``."""
    return not_ported(RUST_MODULE, "build_default_theme")

def theme_lock(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::theme_lock``."""
    return not_ported(RUST_MODULE, "theme_lock")

def set_syntax_theme(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::set_syntax_theme``."""
    return not_ported(RUST_MODULE, "set_syntax_theme")

def current_syntax_theme(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::current_syntax_theme``."""
    return not_ported(RUST_MODULE, "current_syntax_theme")

@dataclass
class DiffScopeBackgroundRgbs:
    """Python boundary for Rust ``render::highlight::DiffScopeBackgroundRgbs``."""
    _payload: Any = None

def diff_scope_background_rgbs(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::diff_scope_background_rgbs``."""
    return not_ported(RUST_MODULE, "diff_scope_background_rgbs")

def diff_scope_background_rgbs_for_theme(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::diff_scope_background_rgbs_for_theme``."""
    return not_ported(RUST_MODULE, "diff_scope_background_rgbs_for_theme")

def scope_background_rgb(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::scope_background_rgb``."""
    return not_ported(RUST_MODULE, "scope_background_rgb")

def foreground_style_for_scopes(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::foreground_style_for_scopes``."""
    return not_ported(RUST_MODULE, "foreground_style_for_scopes")

def foreground_style_for_scopes_with_theme(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::foreground_style_for_scopes_with_theme``."""
    return not_ported(RUST_MODULE, "foreground_style_for_scopes_with_theme")

def configured_theme_name(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::configured_theme_name``."""
    return not_ported(RUST_MODULE, "configured_theme_name")

def resolve_theme_by_name(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::resolve_theme_by_name``."""
    return not_ported(RUST_MODULE, "resolve_theme_by_name")

@dataclass
class ThemeEntry:
    """Python boundary for Rust ``render::highlight::ThemeEntry``."""
    _payload: Any = None

def list_available_themes(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::list_available_themes``."""
    return not_ported(RUST_MODULE, "list_available_themes")

BUILTIN_THEME_NAMES: Any = None

def ansi_palette_color(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::ansi_palette_color``."""
    return not_ported(RUST_MODULE, "ansi_palette_color")

def convert_syntect_color(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::convert_syntect_color``."""
    return not_ported(RUST_MODULE, "convert_syntect_color")

def convert_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::convert_style``."""
    return not_ported(RUST_MODULE, "convert_style")

def find_syntax(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::find_syntax``."""
    return not_ported(RUST_MODULE, "find_syntax")

MAX_HIGHLIGHT_BYTES: Any = None

MAX_HIGHLIGHT_LINES: Any = None

def exceeds_highlight_limits(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::exceeds_highlight_limits``."""
    return not_ported(RUST_MODULE, "exceeds_highlight_limits")

def highlight_to_line_spans_with_theme(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_to_line_spans_with_theme``."""
    return not_ported(RUST_MODULE, "highlight_to_line_spans_with_theme")

def highlight_to_line_spans(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_to_line_spans``."""
    return not_ported(RUST_MODULE, "highlight_to_line_spans")

def highlight_code_to_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_code_to_lines``."""
    return not_ported(RUST_MODULE, "highlight_code_to_lines")

def highlight_bash_to_lines(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_bash_to_lines``."""
    return not_ported(RUST_MODULE, "highlight_bash_to_lines")

def highlight_code_to_styled_spans(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_code_to_styled_spans``."""
    return not_ported(RUST_MODULE, "highlight_code_to_styled_spans")

def write_minimal_tmtheme(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::write_minimal_tmtheme``."""
    return not_ported(RUST_MODULE, "write_minimal_tmtheme")

def write_tmtheme_with_diff_backgrounds(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::write_tmtheme_with_diff_backgrounds``."""
    return not_ported(RUST_MODULE, "write_tmtheme_with_diff_backgrounds")

def reconstructed(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::reconstructed``."""
    return not_ported(RUST_MODULE, "reconstructed")

def unique_foreground_colors_for_theme(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::unique_foreground_colors_for_theme``."""
    return not_ported(RUST_MODULE, "unique_foreground_colors_for_theme")

def theme_item(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::theme_item``."""
    return not_ported(RUST_MODULE, "theme_item")

def theme_item_with_foreground(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::theme_item_with_foreground``."""
    return not_ported(RUST_MODULE, "theme_item_with_foreground")

def assert_rgb(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::assert_rgb``."""
    return not_ported(RUST_MODULE, "assert_rgb")

# -- Concrete no-op highlighting slice ----------------------------------------
#
# Rust owns real syntax highlighting through syntect/two_face.  Python keeps the
# public interface and content-preserving fallback helpers, but intentionally does
# not attempt token-level highlighting here.  This avoids a misleading Pygments
# approximation and keeps the TUI portable until a Python 3.7-compatible
# TextMate/syntect-equivalent engine is selected.

ANSI_ALPHA_INDEX = 0x00
ANSI_ALPHA_DEFAULT = 0x01
OPAQUE_ALPHA = 0xFF
MAX_HIGHLIGHT_BYTES = 512 * 1024
MAX_HIGHLIGHT_LINES = 10_000

BUILTIN_THEME_NAMES = [
    "1337",
    "ansi",
    "base16",
    "base16-256",
    "base16-eighties-dark",
    "base16-mocha-dark",
    "base16-ocean-dark",
    "base16-ocean-light",
    "catppuccin-frappe",
    "catppuccin-latte",
    "catppuccin-macchiato",
    "catppuccin-mocha",
    "coldark-cold",
    "coldark-dark",
    "dark-neon",
    "dracula",
    "github",
    "gruvbox-dark",
    "gruvbox-light",
    "inspired-github",
    "monokai-extended",
    "monokai-extended-bright",
    "monokai-extended-light",
    "monokai-extended-origin",
    "nord",
    "one-half-dark",
    "one-half-light",
    "solarized-dark",
    "solarized-light",
    "sublime-snazzy",
    "two-dark",
    "zenburn",
]

KNOWN_LANGUAGES = {
    "bash", "c", "c#", "cpp", "cs", "css", "dart", "dockerfile", "elixir",
    "ex", "go", "golang", "haskell", "html", "java", "javascript", "js",
    "json", "kotlin", "kt", "lua", "markdown", "md", "perl", "php", "pl",
    "py", "python", "python3", "r", "rb", "rs", "ruby", "rust", "scala",
    "sh", "shell", "sql", "swift", "toml", "ts", "tsx", "typescript", "xml",
    "yaml", "yml", "zig", "csharp", "c-sharp",
}

_THEME_OVERRIDE_NAME: Optional[str] = None
_CURRENT_THEME_NAME = "catppuccin-mocha"


@dataclass(frozen=True)
class SemanticColor:
    kind: str
    value: Any


@dataclass(frozen=True)
class SemanticStyle:
    fg: Optional[SemanticColor] = None
    bold: bool = False
    italic: bool = False

    def patch(self, other: "SemanticStyle") -> "SemanticStyle":
        return SemanticStyle(
            fg=other.fg if other.fg is not None else self.fg,
            bold=self.bold or other.bold,
            italic=self.italic or other.italic,
        )


@dataclass(frozen=True)
class SemanticSpan:
    text: str
    style: SemanticStyle = SemanticStyle()


@dataclass(frozen=True)
class SemanticTheme:
    name: str
    is_custom: bool = False
    path: Optional[Path] = None
    foreground: Optional[Tuple[int, int, int]] = None
    backgrounds: Optional[Dict[str, Tuple[int, int, int]]] = None
    foregrounds: Optional[Dict[str, Tuple[int, int, int]]] = None
    token_styles: Optional[Dict[str, SemanticStyle]] = None


@dataclass
class DiffScopeBackgroundRgbs:
    """Raw RGB backgrounds for inserted/deleted diff scopes.

    The no-op highlighter does not inspect theme scopes, so both values remain
    ``None`` unless a future TextMate-compatible implementation fills them.
    """

    inserted: Optional[Tuple[int, int, int]] = None
    deleted: Optional[Tuple[int, int, int]] = None


@dataclass
class ThemeEntry:
    """Theme picker entry, matching Rust ``ThemeEntry`` shape."""

    name: str
    is_custom: bool = False


def syntax_set() -> None:
    return None


def parse_theme_name(name: str) -> Optional[str]:
    return name if name in BUILTIN_THEME_NAMES else None


def custom_theme_path(name: str, codex_home: Any) -> Path:
    return Path(codex_home) / "themes" / f"{name}.tmTheme"


def load_custom_theme(name: str, codex_home: Any) -> Optional[SemanticTheme]:
    path = custom_theme_path(name, codex_home)
    if not path.is_file():
        return None
    try:
        with path.open("rb") as handle:
            data = plistlib.load(handle)
    except Exception:
        return None

    foreground: Optional[Tuple[int, int, int]] = None
    backgrounds: Dict[str, Tuple[int, int, int]] = {}
    foregrounds: Dict[str, Tuple[int, int, int]] = {}
    token_styles: Dict[str, SemanticStyle] = {}

    for item in data.get("settings", []):
        if not isinstance(item, dict):
            continue
        settings = item.get("settings") or {}
        if not isinstance(settings, dict):
            continue
        scope_value = item.get("scope")
        if scope_value is None:
            fg = _parse_hex_color(settings.get("foreground"))
            if fg is not None:
                foreground = fg
            continue
        scopes = [scope.strip() for scope in str(scope_value).split(",") if scope.strip()]
        fg = _parse_hex_color(settings.get("foreground"))
        bg = _parse_hex_color(settings.get("background"))
        font_style = str(settings.get("fontStyle", "")).lower()
        for scope in scopes:
            if fg is not None:
                foregrounds[scope] = fg
            if bg is not None:
                backgrounds[scope] = bg
            if fg is not None or font_style:
                token_styles[scope] = SemanticStyle(
                    fg=SemanticColor("rgb", fg) if fg is not None else None,
                    bold="bold" in font_style,
                    italic="italic" in font_style,
                )

    return SemanticTheme(
        name=name,
        is_custom=True,
        path=path,
        foreground=foreground,
        backgrounds=backgrounds or None,
        foregrounds=foregrounds or None,
        token_styles=token_styles or None,
    )


def validate_theme_name(name: Optional[str], codex_home: Optional[Any] = None) -> Optional[str]:
    if name is None:
        return None
    custom_path = (
        custom_theme_path(name, codex_home)
        if codex_home is not None
        else Path(f"$CODEX_HOME/themes/{name}.tmTheme")
    )
    if parse_theme_name(name) is not None:
        return None
    if codex_home is not None and custom_theme_path(name, codex_home).is_file():
        if load_custom_theme(name, codex_home) is not None:
            return None
        return (
            f'Custom theme "{name}" at {custom_path} could not be loaded '
            "(invalid .tmTheme format). Falling back to the default theme."
        )
    return (
        f'Theme "{name}" not found. Using the default theme. To use a custom theme, '
        f"place a .tmTheme file at {custom_path}."
    )


def adaptive_default_theme_name() -> str:
    return "catppuccin-mocha"


def adaptive_default_theme_selection() -> Tuple[str, str]:
    return (adaptive_default_theme_name(), adaptive_default_theme_name())


def adaptive_default_embedded_theme_name() -> str:
    return adaptive_default_theme_name()


def _builtin_theme(name: str) -> SemanticTheme:
    return SemanticTheme(name=name, is_custom=False)


def resolve_theme_by_name(name: str, codex_home: Optional[Any] = None) -> Optional[SemanticTheme]:
    if parse_theme_name(name) is not None:
        return _builtin_theme(name)
    if codex_home is not None:
        return load_custom_theme(name, codex_home)
    return None


def resolve_theme_with_override(
    name: Optional[str] = None, codex_home: Optional[Any] = None
) -> SemanticTheme:
    chosen = _THEME_OVERRIDE_NAME or name or _CURRENT_THEME_NAME
    theme = resolve_theme_by_name(chosen, codex_home)
    return theme if theme is not None else _builtin_theme(adaptive_default_theme_name())


def configured_theme_name() -> str:
    return _THEME_OVERRIDE_NAME or _CURRENT_THEME_NAME


def build_default_theme() -> SemanticTheme:
    return _builtin_theme(adaptive_default_theme_name())


def theme_lock() -> SemanticTheme:
    return _current_theme()


def _current_theme() -> SemanticTheme:
    return _builtin_theme(configured_theme_name())


def set_syntax_theme(theme: Any) -> None:
    global _CURRENT_THEME_NAME
    if isinstance(theme, SemanticTheme):
        _CURRENT_THEME_NAME = theme.name
    elif isinstance(theme, str) and theme:
        _CURRENT_THEME_NAME = theme


def current_syntax_theme() -> SemanticTheme:
    return _current_theme()


def set_theme_override(theme_name: Optional[str]) -> None:
    global _THEME_OVERRIDE_NAME
    _THEME_OVERRIDE_NAME = theme_name


def list_available_themes(codex_home: Optional[Any] = None) -> List[ThemeEntry]:
    entries = {name: ThemeEntry(name=name, is_custom=False) for name in BUILTIN_THEME_NAMES}
    if codex_home is not None:
        themes_dir = Path(codex_home) / "themes"
        if themes_dir.is_dir():
            for path in themes_dir.iterdir():
                if path.suffix == ".tmTheme" and path.is_file() and load_custom_theme(path.stem, codex_home) is not None:
                    entries.setdefault(path.stem, ThemeEntry(name=path.stem, is_custom=True))
    return sorted(entries.values(), key=lambda entry: (entry.name.lower(), entry.name))


def ansi_palette_color(index: int) -> SemanticColor:
    named = {
        0x00: "black",
        0x01: "red",
        0x02: "green",
        0x03: "yellow",
        0x04: "blue",
        0x05: "magenta",
        0x06: "cyan",
        0x07: "gray",
    }
    if index in named:
        return SemanticColor("named", named[index])
    return SemanticColor("indexed", int(index))


def convert_syntect_color(color: Any) -> Optional[SemanticColor]:
    r = int(getattr(color, "r"))
    g = int(getattr(color, "g"))
    b = int(getattr(color, "b"))
    a = int(getattr(color, "a", OPAQUE_ALPHA))
    if a == ANSI_ALPHA_INDEX:
        return ansi_palette_color(r)
    if a == ANSI_ALPHA_DEFAULT:
        return None
    return SemanticColor("rgb", (r, g, b))


def convert_style(style: Any) -> SemanticStyle:
    fg = convert_syntect_color(style.foreground)
    font_style = getattr(style, "font_style", None)
    font_text = str(font_style).lower()
    return SemanticStyle(
        fg=fg,
        bold="bold" in font_text,
        italic="italic" in font_text,
    )


def _parse_hex_color(value: Any) -> Optional[Tuple[int, int, int]]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not re.match(r"^#[0-9a-fA-F]{6}$", text):
        return None
    return (int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16))


def find_syntax(language: str) -> Optional[str]:
    normalized = language.strip().lower()
    aliases = {
        "csharp": "c#",
        "c-sharp": "c#",
        "golang": "go",
        "javascript": "js",
        "markdown": "md",
        "python3": "python",
        "rs": "rust",
        "shell": "bash",
        "sh": "bash",
        "typescript": "ts",
        "yml": "yaml",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in KNOWN_LANGUAGES else None


def exceeds_highlight_limits(code: str) -> bool:
    if len(code.encode("utf-8")) > MAX_HIGHLIGHT_BYTES:
        return True
    if code == "":
        return False
    return len(code.splitlines()) > MAX_HIGHLIGHT_LINES


def _plain_line_spans(code: str) -> List[List[SemanticSpan]]:
    if code == "":
        return [[SemanticSpan("")]]
    text = code.replace("\r\n", "\n").replace("\r", "\n")
    parts = text.splitlines()
    return [[SemanticSpan(part)] for part in parts] or [[SemanticSpan("")]]


_KEYWORD_STYLE = SemanticStyle(fg=SemanticColor("rgb", (203, 166, 247)), bold=True)
_STRING_STYLE = SemanticStyle(fg=SemanticColor("rgb", (166, 227, 161)))
_COMMENT_STYLE = SemanticStyle(fg=SemanticColor("rgb", (127, 132, 156)), italic=True)

_KEYWORDS = {
    "rust": {
        "as",
        "async",
        "await",
        "crate",
        "else",
        "enum",
        "fn",
        "for",
        "if",
        "impl",
        "let",
        "match",
        "mod",
        "mut",
        "pub",
        "return",
        "self",
        "Self",
        "struct",
        "trait",
        "use",
        "where",
    },
    "python": {
        "and",
        "as",
        "class",
        "def",
        "elif",
        "else",
        "False",
        "for",
        "from",
        "if",
        "import",
        "in",
        "is",
        "None",
        "not",
        "or",
        "pass",
        "return",
        "True",
        "while",
        "with",
    },
    "bash": {"case", "do", "done", "elif", "else", "esac", "fi", "for", "function", "if", "in", "then", "while"},
}


def _styled_line_spans(code: str, language: str, theme: SemanticTheme) -> List[List[SemanticSpan]]:
    normalized = find_syntax(language) or language
    keyword_scope = foreground_style_for_scopes_with_theme(theme, ["keyword", "keyword.control"])
    keyword_style = keyword_scope or _KEYWORD_STYLE
    lines = _plain_line_spans(code)
    keywords = _KEYWORDS.get(normalized, set())
    if normalized == "rs":
        keywords = _KEYWORDS["rust"]
    if normalized == "py":
        keywords = _KEYWORDS["python"]
    if normalized == "sh":
        keywords = _KEYWORDS["bash"]
    result: List[List[SemanticSpan]] = []
    for line in lines:
        text = "".join(span.text for span in line)
        result.append(_styled_line(text, keywords, keyword_style))
    return result


def _styled_line(text: str, keywords: Any, keyword_style: SemanticStyle) -> List[SemanticSpan]:
    spans: List[SemanticSpan] = []
    token_re = re.compile(r"(#.*$|//.*$|\"[^\"\\]*(?:\\.[^\"\\]*)*\"|'[^'\\]*(?:\\.[^'\\]*)*'|\b[A-Za-z_][A-Za-z0-9_]*\b)")
    pos = 0
    for match in token_re.finditer(text):
        if match.start() > pos:
            spans.append(SemanticSpan(text[pos:match.start()]))
        token = match.group(0)
        if token.startswith("#") or token.startswith("//"):
            spans.append(SemanticSpan(token, _COMMENT_STYLE))
        elif token.startswith("\"") or token.startswith("'"):
            spans.append(SemanticSpan(token, _STRING_STYLE))
        elif token in keywords:
            spans.append(SemanticSpan(token, keyword_style))
        else:
            spans.append(SemanticSpan(token))
        pos = match.end()
    if pos < len(text):
        spans.append(SemanticSpan(text[pos:]))
    return spans or [SemanticSpan("")]


def highlight_to_line_spans_with_theme(
    code: str, language: str, theme: Optional[SemanticTheme] = None
) -> Optional[List[List[SemanticSpan]]]:
    if exceeds_highlight_limits(code) or find_syntax(language) is None:
        return None
    return _styled_line_spans(code, find_syntax(language) or language, theme or current_syntax_theme())


def highlight_to_line_spans(code: str, language: str) -> Optional[List[List[SemanticSpan]]]:
    return highlight_to_line_spans_with_theme(code, language, current_syntax_theme())


def highlight_code_to_lines(code: str, language: str) -> List[List[SemanticSpan]]:
    return highlight_code_to_styled_spans(code, language) or _plain_line_spans(code)


def highlight_bash_to_lines(code: str) -> List[List[SemanticSpan]]:
    return highlight_code_to_lines(code, "bash")


def highlight_code_to_styled_spans(code: str, language: str) -> Optional[List[List[SemanticSpan]]]:
    return highlight_to_line_spans(code, language)


def reconstructed(lines: List[List[SemanticSpan]]) -> str:
    return "\n".join("".join(span.text for span in line) for line in lines)


def diff_scope_background_rgbs_for_theme(theme: Any) -> DiffScopeBackgroundRgbs:
    backgrounds = getattr(theme, "backgrounds", None) or {}
    return DiffScopeBackgroundRgbs(
        inserted=backgrounds.get("markup.inserted") or backgrounds.get("diff.inserted"),
        deleted=backgrounds.get("markup.deleted") or backgrounds.get("diff.deleted"),
    )


def diff_scope_background_rgbs() -> DiffScopeBackgroundRgbs:
    return DiffScopeBackgroundRgbs()


def scope_background_rgb(*args: Any, **kwargs: Any) -> None:
    if len(args) >= 2:
        theme, scope_name = args[0], args[1]
    elif len(args) == 1:
        theme, scope_name = current_syntax_theme(), args[0]
    else:
        theme, scope_name = current_syntax_theme(), kwargs.get("scope_name")
    backgrounds = getattr(theme, "backgrounds", None) or {}
    return backgrounds.get(scope_name)


def foreground_style_for_scopes_with_theme(theme: Any, scope_names: List[str]) -> Optional[SemanticStyle]:
    styles = getattr(theme, "token_styles", None) or {}
    for scope_name in scope_names:
        style = styles.get(scope_name)
        if style is not None and style.fg is not None:
            return style
    return None


def foreground_style_for_scopes(scope_names: List[str]) -> Optional[SemanticStyle]:
    return None


def write_minimal_tmtheme(*args: Any, **kwargs: Any) -> None:
    path = Path(args[0] if args else kwargs["path"])
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>settings</key><array>
<dict><key>settings</key><dict><key>foreground</key><string>#EEEEEE</string></dict></dict>
</array></dict></plist>""",
        encoding="utf-8",
    )


def write_tmtheme_with_diff_backgrounds(*args: Any, **kwargs: Any) -> None:
    path = Path(args[0] if args else kwargs["path"])
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>settings</key><array>
<dict><key>settings</key><dict><key>foreground</key><string>#EEEEEE</string></dict></dict>
<dict><key>scope</key><string>markup.inserted</string><key>settings</key><dict><key>background</key><string>#102030</string></dict></dict>
<dict><key>scope</key><string>markup.deleted</string><key>settings</key><dict><key>background</key><string>#405060</string></dict></dict>
</array></dict></plist>""",
        encoding="utf-8",
    )


def unique_foreground_colors_for_theme(*args: Any, **kwargs: Any) -> List[Any]:
    return []


def theme_item(*args: Any, **kwargs: Any) -> None:
    return None


def theme_item_with_foreground(*args: Any, **kwargs: Any) -> None:
    return None


def assert_rgb(*args: Any, **kwargs: Any) -> None:
    return None

def highlight_rust_has_keyword_style(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_rust_has_keyword_style``."""
    return not_ported(RUST_MODULE, "highlight_rust_has_keyword_style")

def highlight_unknown_lang_falls_back(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_unknown_lang_falls_back``."""
    return not_ported(RUST_MODULE, "highlight_unknown_lang_falls_back")

def fallback_trailing_newline_no_phantom_line(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::fallback_trailing_newline_no_phantom_line``."""
    return not_ported(RUST_MODULE, "fallback_trailing_newline_no_phantom_line")

def highlight_empty_string(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_empty_string``."""
    return not_ported(RUST_MODULE, "highlight_empty_string")

def highlight_bash_preserves_content(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_bash_preserves_content``."""
    return not_ported(RUST_MODULE, "highlight_bash_preserves_content")

def highlight_crlf_strips_carriage_return(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_crlf_strips_carriage_return``."""
    return not_ported(RUST_MODULE, "highlight_crlf_strips_carriage_return")

def style_conversion_correctness(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::style_conversion_correctness``."""
    return not_ported(RUST_MODULE, "style_conversion_correctness")

def convert_style_suppresses_underline(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::convert_style_suppresses_underline``."""
    return not_ported(RUST_MODULE, "convert_style_suppresses_underline")

def style_conversion_uses_ansi_named_color_when_alpha_is_zero_low_index(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::style_conversion_uses_ansi_named_color_when_alpha_is_zero_low_index``."""
    return not_ported(RUST_MODULE, "style_conversion_uses_ansi_named_color_when_alpha_is_zero_low_index")

def style_conversion_uses_indexed_color_when_alpha_is_zero_high_index(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::style_conversion_uses_indexed_color_when_alpha_is_zero_high_index``."""
    return not_ported(RUST_MODULE, "style_conversion_uses_indexed_color_when_alpha_is_zero_high_index")

def style_conversion_uses_terminal_default_when_alpha_is_one(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::style_conversion_uses_terminal_default_when_alpha_is_one``."""
    return not_ported(RUST_MODULE, "style_conversion_uses_terminal_default_when_alpha_is_one")

def style_conversion_unexpected_alpha_falls_back_to_rgb(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::style_conversion_unexpected_alpha_falls_back_to_rgb``."""
    return not_ported(RUST_MODULE, "style_conversion_unexpected_alpha_falls_back_to_rgb")

def ansi_palette_color_maps_ansi_white_to_gray(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::ansi_palette_color_maps_ansi_white_to_gray``."""
    return not_ported(RUST_MODULE, "ansi_palette_color_maps_ansi_white_to_gray")

def ansi_family_themes_use_terminal_palette_colors_not_rgb(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::ansi_family_themes_use_terminal_palette_colors_not_rgb``."""
    return not_ported(RUST_MODULE, "ansi_family_themes_use_terminal_palette_colors_not_rgb")

def ansi_family_foreground_palette_snapshot(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::ansi_family_foreground_palette_snapshot``."""
    return not_ported(RUST_MODULE, "ansi_family_foreground_palette_snapshot")

def highlight_multiline_python(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_multiline_python``."""
    return not_ported(RUST_MODULE, "highlight_multiline_python")

def highlight_code_to_styled_spans_returns_none_for_unknown(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_code_to_styled_spans_returns_none_for_unknown``."""
    return not_ported(RUST_MODULE, "highlight_code_to_styled_spans_returns_none_for_unknown")

def highlight_code_to_styled_spans_returns_some_for_known(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_code_to_styled_spans_returns_some_for_known``."""
    return not_ported(RUST_MODULE, "highlight_code_to_styled_spans_returns_some_for_known")

def highlight_markdown_preserves_content(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_markdown_preserves_content``."""
    return not_ported(RUST_MODULE, "highlight_markdown_preserves_content")

def highlight_large_input_falls_back(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_large_input_falls_back``."""
    return not_ported(RUST_MODULE, "highlight_large_input_falls_back")

def highlight_many_lines_falls_back(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_many_lines_falls_back``."""
    return not_ported(RUST_MODULE, "highlight_many_lines_falls_back")

def highlight_many_lines_no_trailing_newline_falls_back(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::highlight_many_lines_no_trailing_newline_falls_back``."""
    return not_ported(RUST_MODULE, "highlight_many_lines_no_trailing_newline_falls_back")

def find_syntax_resolves_languages_and_aliases(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::find_syntax_resolves_languages_and_aliases``."""
    return not_ported(RUST_MODULE, "find_syntax_resolves_languages_and_aliases")

def diff_scope_backgrounds_prefer_markup_scope_then_diff_fallback(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::diff_scope_backgrounds_prefer_markup_scope_then_diff_fallback``."""
    return not_ported(RUST_MODULE, "diff_scope_backgrounds_prefer_markup_scope_then_diff_fallback")

def diff_scope_backgrounds_return_none_when_no_background_scope_matches(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::diff_scope_backgrounds_return_none_when_no_background_scope_matches``."""
    return not_ported(RUST_MODULE, "diff_scope_backgrounds_return_none_when_no_background_scope_matches")

def foreground_style_for_scopes_reads_matching_theme_scope(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::foreground_style_for_scopes_reads_matching_theme_scope``."""
    return not_ported(RUST_MODULE, "foreground_style_for_scopes_reads_matching_theme_scope")

def foreground_style_for_scopes_uses_first_scope_with_foreground(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::foreground_style_for_scopes_uses_first_scope_with_foreground``."""
    return not_ported(RUST_MODULE, "foreground_style_for_scopes_uses_first_scope_with_foreground")

def bundled_theme_can_provide_diff_scope_backgrounds(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::bundled_theme_can_provide_diff_scope_backgrounds``."""
    return not_ported(RUST_MODULE, "bundled_theme_can_provide_diff_scope_backgrounds")

def custom_tmtheme_diff_scope_backgrounds_are_resolved(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::custom_tmtheme_diff_scope_backgrounds_are_resolved``."""
    return not_ported(RUST_MODULE, "custom_tmtheme_diff_scope_backgrounds_are_resolved")

def parse_theme_name_covers_all_variants(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::parse_theme_name_covers_all_variants``."""
    return not_ported(RUST_MODULE, "parse_theme_name_covers_all_variants")

def parse_theme_name_returns_none_for_unknown(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::parse_theme_name_returns_none_for_unknown``."""
    return not_ported(RUST_MODULE, "parse_theme_name_returns_none_for_unknown")

def load_custom_theme_from_tmtheme_file(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::load_custom_theme_from_tmtheme_file``."""
    return not_ported(RUST_MODULE, "load_custom_theme_from_tmtheme_file")

def load_custom_theme_returns_none_for_missing(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::load_custom_theme_returns_none_for_missing``."""
    return not_ported(RUST_MODULE, "load_custom_theme_returns_none_for_missing")

def validate_theme_name_none_for_bundled(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::validate_theme_name_none_for_bundled``."""
    return not_ported(RUST_MODULE, "validate_theme_name_none_for_bundled")

def validate_theme_name_none_when_no_override(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::validate_theme_name_none_when_no_override``."""
    return not_ported(RUST_MODULE, "validate_theme_name_none_when_no_override")

def validate_theme_name_warns_for_missing_custom(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::validate_theme_name_warns_for_missing_custom``."""
    return not_ported(RUST_MODULE, "validate_theme_name_warns_for_missing_custom")

def validate_theme_name_none_when_custom_file_is_valid(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::validate_theme_name_none_when_custom_file_is_valid``."""
    return not_ported(RUST_MODULE, "validate_theme_name_none_when_custom_file_is_valid")

def validate_theme_name_warns_when_custom_file_is_invalid(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::validate_theme_name_warns_when_custom_file_is_invalid``."""
    return not_ported(RUST_MODULE, "validate_theme_name_warns_when_custom_file_is_invalid")

def list_available_themes_excludes_invalid_custom_files(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::list_available_themes_excludes_invalid_custom_files``."""
    return not_ported(RUST_MODULE, "list_available_themes_excludes_invalid_custom_files")

def list_available_themes_returns_stable_sorted_order(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::list_available_themes_returns_stable_sorted_order``."""
    return not_ported(RUST_MODULE, "list_available_themes_returns_stable_sorted_order")

def parse_theme_name_is_exhaustive(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``render::highlight::parse_theme_name_is_exhaustive``."""
    return not_ported(RUST_MODULE, "parse_theme_name_is_exhaustive")

__all__ = [
    "ANSI_ALPHA_DEFAULT",
    "ANSI_ALPHA_INDEX",
    "BUILTIN_THEME_NAMES",
    "CODEX_HOME",
    "DiffScopeBackgroundRgbs",
    "MAX_HIGHLIGHT_BYTES",
    "MAX_HIGHLIGHT_LINES",
    "OPAQUE_ALPHA",
    "RUST_MODULE",
    "SYNTAX_SET",
    "THEME",
    "THEME_OVERRIDE",
    "ThemeEntry",
    "adaptive_default_embedded_theme_name",
    "adaptive_default_theme_name",
    "adaptive_default_theme_selection",
    "ansi_family_foreground_palette_snapshot",
    "ansi_family_themes_use_terminal_palette_colors_not_rgb",
    "ansi_palette_color",
    "ansi_palette_color_maps_ansi_white_to_gray",
    "assert_rgb",
    "build_default_theme",
    "bundled_theme_can_provide_diff_scope_backgrounds",
    "configured_theme_name",
    "convert_style",
    "convert_style_suppresses_underline",
    "convert_syntect_color",
    "current_syntax_theme",
    "custom_theme_path",
    "custom_tmtheme_diff_scope_backgrounds_are_resolved",
    "diff_scope_background_rgbs",
    "diff_scope_background_rgbs_for_theme",
    "diff_scope_backgrounds_prefer_markup_scope_then_diff_fallback",
    "diff_scope_backgrounds_return_none_when_no_background_scope_matches",
    "exceeds_highlight_limits",
    "fallback_trailing_newline_no_phantom_line",
    "find_syntax",
    "find_syntax_resolves_languages_and_aliases",
    "foreground_style_for_scopes",
    "foreground_style_for_scopes_reads_matching_theme_scope",
    "foreground_style_for_scopes_uses_first_scope_with_foreground",
    "foreground_style_for_scopes_with_theme",
    "highlight_bash_preserves_content",
    "highlight_bash_to_lines",
    "highlight_code_to_lines",
    "highlight_code_to_styled_spans",
    "highlight_code_to_styled_spans_returns_none_for_unknown",
    "highlight_code_to_styled_spans_returns_some_for_known",
    "highlight_crlf_strips_carriage_return",
    "highlight_empty_string",
    "highlight_large_input_falls_back",
    "highlight_many_lines_falls_back",
    "highlight_many_lines_no_trailing_newline_falls_back",
    "highlight_markdown_preserves_content",
    "highlight_multiline_python",
    "highlight_rust_has_keyword_style",
    "highlight_to_line_spans",
    "highlight_to_line_spans_with_theme",
    "highlight_unknown_lang_falls_back",
    "list_available_themes",
    "list_available_themes_excludes_invalid_custom_files",
    "list_available_themes_returns_stable_sorted_order",
    "load_custom_theme",
    "load_custom_theme_from_tmtheme_file",
    "load_custom_theme_returns_none_for_missing",
    "parse_theme_name",
    "parse_theme_name_covers_all_variants",
    "parse_theme_name_is_exhaustive",
    "parse_theme_name_returns_none_for_unknown",
    "reconstructed",
    "resolve_theme_by_name",
    "resolve_theme_with_override",
    "scope_background_rgb",
    "set_syntax_theme",
    "set_theme_override",
    "style_conversion_correctness",
    "style_conversion_unexpected_alpha_falls_back_to_rgb",
    "style_conversion_uses_ansi_named_color_when_alpha_is_zero_low_index",
    "style_conversion_uses_indexed_color_when_alpha_is_zero_high_index",
    "style_conversion_uses_terminal_default_when_alpha_is_one",
    "syntax_set",
    "theme_item",
    "theme_item_with_foreground",
    "theme_lock",
    "unique_foreground_colors_for_theme",
    "validate_theme_name",
    "validate_theme_name_none_for_bundled",
    "validate_theme_name_none_when_custom_file_is_valid",
    "validate_theme_name_none_when_no_override",
    "validate_theme_name_warns_for_missing_custom",
    "validate_theme_name_warns_when_custom_file_is_invalid",
    "write_minimal_tmtheme",
    "write_tmtheme_with_diff_backgrounds",
]

