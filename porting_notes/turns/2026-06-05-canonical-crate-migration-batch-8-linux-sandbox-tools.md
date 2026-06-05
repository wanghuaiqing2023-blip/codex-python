# 2026-06-05 canonical crate migration batch 8: linux-sandbox and tools helpers

## Scope

Move two small old-coordinate helpers into canonical crate-level Python packages.

## Rust source coordinates

- `codex/codex-rs/linux-sandbox` -> `pycodex/linux_sandbox`
- `codex/codex-rs/tools` selected image-detail behavior -> `pycodex/tools/original_image_detail.py`

## Python old coordinates

- `pycodex/core/landlock.py`
- `pycodex/core/original_image_detail.py`

## Python target coordinates

- `pycodex/linux_sandbox/__init__.py`
- `pycodex/tools/original_image_detail.py`

## Migration policy

Keep old files only until focused validation passes, then delete them to avoid dual coordinates.

## Validation before deleting old coordinates

- `python -m pytest tests/test_core_spawn_landlock.py tests/test_core_original_image_detail.py -q`: 12 passed.
- Import smoke for `pycodex.linux_sandbox`, `pycodex.tools.original_image_detail`, and dependent core modules: passed.

## Old coordinate deletion

Deleted `pycodex/core/landlock.py` and `pycodex/core/original_image_detail.py` after focused validation.

## Validation after deleting old coordinates

- Focused tests: 12 passed.
- Import smoke after deletion: passed.
- Residual old-coordinate check: no matches for `pycodex.core.landlock` or `pycodex.core.original_image_detail` imports.
