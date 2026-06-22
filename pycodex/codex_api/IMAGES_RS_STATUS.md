# codex-api/src/images.rs status

Rust module: `codex/codex-rs/codex-api/src/images.rs`

Python module: `pycodex/codex_api/images.py`

Status: `complete`

Ported contract:

- `ImageGenerationRequest` serializes prompt/model plus optional background,
  `n`, quality, and size fields, skipping absent options.
- `ImageEditRequest` serializes image URL entries, prompt/model, and skips
  absent options.
- `ImageUrl` preserves the `image_url` wire field.
- `ImageBackground` and `ImageQuality` use lowercase wire values.
- `ImageResponse` requires `created` and `data`, while `background`,
  `quality`, and `size` default to `None` when absent; `created` follows Rust
  `u64` deserialization and rejects negative values.
- `ImageData` preserves the `b64_json` wire field.
- All `ImageBackground` and `ImageQuality` variants expose lowercase wire
  values.
- `ImageData` requires the `b64_json` field.

Validation:

- `python -m pytest tests/test_codex_api_images_rs.py -q --tb=short` passed
  on 2026-06-21 with `8 passed`.
- `python -m py_compile pycodex/codex_api/images.py tests/test_codex_api_images_rs.py`
  passed on 2026-06-21.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api_*_rs.py -q --tb=short` passed on
  2026-06-21 with `234 passed, 49 subtests passed`.
