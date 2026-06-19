# codex-utils-template src/lib.rs Status

Status: complete

Rust source:

- `codex/codex-rs/utils/template/src/lib.rs`

Python target:

- `pycodex/utils/template/__init__.py`

Behavior contract covered:

- strict `{{ name }}` placeholder interpolation
- literal delimiter escapes with `{{{{` and `}}}}`
- sorted unique placeholder inventory
- reusable parsed templates
- strict render validation for missing, extra, and duplicate values
- parse errors with Rust-compatible byte offsets
- one-shot `render` wrapping parse and render errors

Tests:

- `tests/test_utils_template.py`

Last validation:

- 2026-06-17: `python -m pytest tests\test_utils_template.py -q` -> `15 passed`
- 2026-06-17: `python -m py_compile pycodex\utils\template\__init__.py tests\test_utils_template.py` -> passed

