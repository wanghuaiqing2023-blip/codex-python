import os

from pycodex.tui.text_formatting import capitalize_first
from pycodex.tui.text_formatting import center_truncate_path
from pycodex.tui.text_formatting import format_and_truncate_tool_result
from pycodex.tui.text_formatting import format_json_compact
from pycodex.tui.text_formatting import proper_join
from pycodex.tui.text_formatting import truncate_text


def test_capitalize_first_matches_rust_char_uppercase() -> None:
    # Rust: text_formatting.rs::capitalize_first behavior contract.
    assert capitalize_first("") == ""
    assert capitalize_first("hello") == "Hello"
    assert capitalize_first("éclair") == "Éclair"
    assert capitalize_first("ßeta") == "SSeta"


def test_truncate_text() -> None:
    # Rust: codex-rs/tui/src/text_formatting.rs::tests::test_truncate_text
    assert truncate_text("Hello, world!", 8) == "Hello..."


def test_truncate_boundaries() -> None:
    # Rust: text_formatting.rs truncate_text boundary tests.
    assert truncate_text("", 5) == ""
    assert truncate_text("Hello", 0) == ""
    assert truncate_text("Hello", 1) == "H"
    assert truncate_text("Hello", 2) == "He"
    assert truncate_text("Hello", 3) == "..."
    assert truncate_text("Hi", 10) == "Hi"
    assert truncate_text("Hello", 5) == "Hello"


def test_truncate_unicode_combining_characters() -> None:
    # Rust uses Unicode grapheme segmentation, so combining marks stay attached.
    assert truncate_text("e\u0301n\u0303", 2) == "e\u0301n\u0303"


def test_truncate_emoji_and_very_long_text() -> None:
    # Rust: text_formatting.rs::tests::test_truncate_emoji and test_truncate_very_long_text.
    emoji_text = "👋🌍🚀✨"
    assert truncate_text(emoji_text, 3) == "..."
    assert truncate_text(emoji_text, 4) == emoji_text
    long_text = "a" * 1000
    assert truncate_text(long_text, 10) == "aaaaaaa..."
    assert len(truncate_text(long_text, 10)) == 10


def test_format_json_compact_examples() -> None:
    # Rust: text_formatting.rs format_json_compact tests.
    assert format_json_compact('{ "name": "John", "age": 30 }') == '{"name": "John", "age": 30}'
    assert (
        format_json_compact('{ "user": { "name": "John", "details": { "age": 30, "city": "NYC" } } }')
        == '{"user": {"name": "John", "details": {"age": 30, "city": "NYC"}}}'
    )
    assert format_json_compact("[ 1, 2, { \"key\": \"value\" }, \"string\" ]") == '[1, 2, {"key": "value"}, "string"]'
    assert format_json_compact('{"compact":true}') == '{"compact": true}'
    assert format_json_compact('{"invalid": json syntax}') is None
    assert format_json_compact("{}") == "{}"
    assert format_json_compact("[]") == "[]"
    assert format_json_compact("42") == "42"
    assert format_json_compact("true") == "true"
    assert format_json_compact("false") == "false"
    assert format_json_compact("null") == "null"
    assert format_json_compact('"string"') == '"string"'


def test_format_json_compact_with_multiline_whitespace() -> None:
    # Rust: text_formatting.rs::tests::test_format_json_compact_with_whitespace.
    json_text = """
        {
            "name": "John",
            "hobbies": [
                "reading",
                "coding"
            ]
        }
        """
    assert format_json_compact(json_text) == '{"name": "John", "hobbies": ["reading", "coding"]}'


def test_format_json_compact_preserves_commas_colons_and_escapes_inside_strings() -> None:
    # Rust: text_formatting.rs format_json_compact tracks in-string and escape
    # state while inserting spaces after structural JSON separators.
    assert (
        format_json_compact(r'{"message":"a,b:c","quote":"say \"hi, ok\""}')
        == r'{"message": "a,b:c", "quote": "say \"hi, ok\""}'
    )


def test_format_and_truncate_tool_result_compacts_json_before_truncating() -> None:
    # Rust: format_and_truncate_tool_result uses max_lines * line_width - max_lines grapheme budget.
    assert format_and_truncate_tool_result('{"compact":true}', 2, 10) == '{"compact": true}'
    assert format_and_truncate_tool_result('{"compact":true,"extra":false}', 1, 12) == '{"compac...'
    assert format_and_truncate_tool_result("Hello, world!", 1, 8) == "Hell..."


def test_center_truncate_path_examples() -> None:
    # Rust: text_formatting.rs center_truncate_path representative behavior.
    sep = os.sep
    short_path = f"{sep}Users{sep}codex{sep}Public"
    assert center_truncate_path(short_path, 40) == short_path
    path = f"~{sep}hello{sep}the{sep}fox{sep}is{sep}very{sep}fast"
    assert center_truncate_path(path, 24) == f"~{sep}hello{sep}the{sep}…{sep}very{sep}fast"
    long_segment = f"~{sep}supercalifragilisticexpialidocious"
    assert center_truncate_path(long_segment, 18) == f"~{sep}…cexpialidocious"
    assert center_truncate_path(long_segment, 1) == "…"
    assert center_truncate_path(long_segment, 0) == ""


def test_center_truncate_long_windows_style_path_on_current_separator() -> None:
    # Rust builds this test with std::path::MAIN_SEPARATOR, so the expected
    # separator follows the platform where the test is run.
    sep = os.sep
    path = f"C:{sep}Users{sep}codex{sep}Projects{sep}super{sep}long{sep}windows{sep}path{sep}file.txt"
    assert center_truncate_path(path, 36) == f"C:{sep}Users{sep}codex{sep}…{sep}path{sep}file.txt"


def test_proper_join() -> None:
    # Rust: codex-rs/tui/src/text_formatting.rs::tests::test_proper_join
    assert proper_join([]) == ""
    assert proper_join(["apple"]) == "apple"
    assert proper_join(["apple", "banana"]) == "apple and banana"
    assert proper_join(["apple", "banana", "cherry"]) == "apple, banana and cherry"
    assert proper_join(["apple", "banana", "cherry", "date"]) == "apple, banana, cherry and date"
