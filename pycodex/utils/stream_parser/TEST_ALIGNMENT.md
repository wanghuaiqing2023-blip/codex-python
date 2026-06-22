# codex-utils-stream-parser test alignment

Rust crate: `codex-utils-stream-parser`

Python package: `pycodex/utils/stream_parser`

Status: `complete`

Module mapping:

- `codex/codex-rs/utils/stream-parser/src/lib.rs` ->
  `pycodex/utils/stream_parser/__init__.py`
- `codex/codex-rs/utils/stream-parser/src/stream_text.rs` ->
  `pycodex/utils/stream_parser/__init__.py`
- `codex/codex-rs/utils/stream-parser/src/inline_hidden_tag.rs` ->
  `pycodex/utils/stream_parser/__init__.py`
- `codex/codex-rs/utils/stream-parser/src/citation.rs` ->
  `pycodex/utils/stream_parser/__init__.py`
- `codex/codex-rs/utils/stream-parser/src/utf8_stream.rs` ->
  `pycodex/utils/stream_parser/__init__.py`
- `codex/codex-rs/utils/stream-parser/src/tagged_line_parser.rs` ->
  internal helpers in `pycodex/utils/stream_parser/__init__.py`
- `codex/codex-rs/utils/stream-parser/src/proposed_plan.rs` ->
  `pycodex/utils/stream_parser/__init__.py`
- `codex/codex-rs/utils/stream-parser/src/assistant_text.rs` ->
  `pycodex/utils/stream_parser/__init__.py`

Rust behavior covered in `tests/test_utils_stream_parser.py`:

- Citation parser streams tags across chunk boundaries.
- Citation parser buffers partial opener prefixes and flushes non-tag EOF
  prefixes.
- `strip_citations(...)` collects all citations, auto-closes unterminated
  citations at EOF, and preserves Rust's non-nested matching semantics.
- Generic inline hidden tag parser supports multiple tags, longest opener
  preference, non-ASCII delimiters, and constructor assertions for empty specs
  or delimiters.
- UTF-8 stream parser buffers split code points, rolls back invalid pushed
  chunks, reports invalid offsets/error lengths, reports incomplete EOF, and
  supports strict/lossy inner return.
- Proposed-plan parser streams visible text and ordered plan segments, preserves
  non-tag lines, rejects tag lines with extra text, buffers tag prefixes until
  decided, auto-closes unterminated plan blocks, strips plan blocks, and
  extracts the last proposed-plan block text.
- Assistant text parser strips citations across chunks, parses proposed-plan
  segments after citation stripping in plan mode, and leaves plan tags visible
  when plan mode is disabled.

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_utils_stream_parser -v`
  passed on 2026-06-20 with `20 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/utils/stream_parser/__init__.py tests/test_utils_stream_parser.py`
  passed on 2026-06-20.

Notes:

- The Rust crate is dependency-free aside from dev-test dependencies and has no
  runtime OS boundary. Python keeps the implementation standard-library only.
- Focused pytest was not available in this workspace; the fallback Python
  runtime supports `unittest` and `py_compile` but has no `pytest` module.
