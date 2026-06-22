# `codex-utils-stream-parser/src/lib.rs` alignment status

Rust crate: `codex-utils-stream-parser`

Rust module boundary: `src/lib.rs` and the modules it re-exports:
`assistant_text`, `citation`, `inline_hidden_tag`, `proposed_plan`,
`stream_text`, `tagged_line_parser`, and `utf8_stream`.

Python module: `pycodex/utils/stream_parser/__init__.py`

Status: `complete`

Implemented behavior:

- `StreamTextChunk` and `StreamTextParser`-style incremental text parser
  protocol.
- Generic literal inline hidden tag parsing with chunk-boundary buffering,
  longest opener preference, non-nested semantics, non-ASCII delimiter support,
  and EOF auto-close for active tags.
- Citation parsing and one-shot `strip_citations(...)` over
  `<oai-mem-citation>...</oai-mem-citation>`.
- UTF-8 byte-stream adapter behavior for split code points, invalid-chunk
  rollback, EOF errors for incomplete code points, and lossy inner return.
- Line-based proposed-plan parsing through the internal tagged-line parser,
  including tag-only trimmed line recognition, prefix buffering, visible text
  preservation, block stripping, extraction, and EOF auto-close.
- Assistant text parsing composition: citations are stripped first; proposed
  plan blocks are parsed only in plan mode.

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_utils_stream_parser -v`
  passed on 2026-06-20 with `20 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/utils/stream_parser/__init__.py tests/test_utils_stream_parser.py`
  passed on 2026-06-20.

Focused pytest remains environment-dependent in this workspace because
`python`, `py`, `python3`, and `pytest` were not available on PATH and the
available fallback Python runtime did not include `pytest`.
