# codex-utils-template Test Alignment

Status: complete

Rust module:

- `codex/codex-rs/utils/template/src/lib.rs`

Python module:

- `pycodex/utils/template/__init__.py`

Parity evidence:

- `tests/test_utils_template.py`

Rust-derived coverage:

- `render_replaces_placeholders_with_and_without_whitespace`
- `parsed_templates_can_be_reused`
- `placeholders_are_sorted_and_unique`
- `render_supports_multiline_templates_and_adjacent_placeholders`
- `render_supports_literal_delimiter_escapes`
- empty, unterminated, nested, and unmatched delimiter parse errors
- missing, extra, and duplicate value render errors
- render function wrapping for parse and render errors

Additional Python boundary coverage:

- parse error offsets are UTF-8 byte offsets, matching Rust byte-indexed errors.

Validation:

- `python -m pytest tests\test_utils_template.py -q` -> `15 passed`
- `python -m py_compile pycodex\utils\template\__init__.py tests\test_utils_template.py` -> passed

Known adaptations:

- Rust uses enum variants for parse/render/template errors; Python uses dataclass exception values with equivalent kind and payload fields.

