# codex-api/src/files.rs status

Rust module: `codex/codex-rs/codex-api/src/files.rs`

Python module: `pycodex/codex_api/files.py`

Status: `complete`

Ported contract:

- `openai_file_uri` and `OPENAI_FILE_URI_PREFIX` preserve the `sediment://`
  file URI shape.
- `UploadedOpenAiFile` mirrors the Rust return payload fields.
- `OpenAiFileError` mirrors the Rust error variants and display strings for
  missing paths, non-files, read failures, over-limit files, request failures,
  unexpected statuses, decode failures, not-ready finalization, and failed
  finalization.
- `upload_local_file` validates the local path and size before request work,
  sends create/upload/finalize operations through an injectable transport
  boundary, applies auth headers to create/finalize requests, sends the blob
  upload headers from Rust, retries `status: retry` finalization responses,
  and returns the canonical uploaded-file payload on `status: success`.
- `DownloadLinkResponse`-style finalization payload decoding rejects present
  non-string optional fields before success/failure branch handling, while
  missing successful `file_name` falls back to the local file name.

Intentional adaptation:

- Rust uses `reqwest` and Azure blob streaming directly. Python keeps the HTTP
  boundary injectable through `OpenAiFileTransport` so the module can be tested
  without adding a third-party HTTP dependency or performing network IO.

Validation:

- `python -m pytest tests/test_codex_api_files_rs.py -q --tb=short` passed on
  2026-06-21 with `6 passed, 4 subtests passed`.
- `python -m py_compile pycodex/codex_api/files.py tests/test_codex_api_files_rs.py`
  passed on 2026-06-21.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api_*_rs.py -q --tb=short` passed on
  2026-06-21 with `238 passed, 69 subtests passed`.
