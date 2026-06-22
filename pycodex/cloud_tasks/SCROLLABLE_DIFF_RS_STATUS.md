# codex-cloud-tasks src/scrollable_diff.rs status

Rust crate: `codex-cloud-tasks`

Rust module: `codex/codex-rs/cloud-tasks/src/scrollable_diff.rs`

Python module: `pycodex/cloud_tasks/scrollable_diff.py`

Status: `complete`

## Anchors

- `ScrollViewState`
- `ScrollViewState::clamp`
- `ScrollableDiff`
- `ScrollableDiff::{new,set_content,set_width,set_viewport,wrapped_lines,wrapped_src_indices,raw_line_at,scroll_by,page_by,scroll_to_top,scroll_to_bottom,percent_scrolled}`
- internal `rewrap` and `max_scroll`

## Ported behavior

- Saturating scroll clamp.
- Content replacement clears wrapped cache and forces width-based rewrap.
- Width changes rebuild wrapped lines and clamp scroll.
- Viewport changes clamp scroll.
- Raw-line lookup returns an empty string for out-of-range indices.
- Signed scroll/page movement clamps to `[0, max_scroll]`.
- Bottom/top scroll helpers.
- Percent scrolled returns `None` for missing geometry or fully visible content, otherwise rounded visible-bottom percentage clamped to 0..100.
- Rewrap handles width zero like Rust's branch, including preserving stale wrapped source indices.
- Rewrap normalizes tabs to four spaces, splits embedded newlines, tracks source raw-line indices, soft-breaks on whitespace and punctuation, and counts wide characters as display width 2.

## Evidence

- Rust source: `codex/codex-rs/cloud-tasks/src/scrollable_diff.rs`
- Python source: `pycodex/cloud_tasks/scrollable_diff.py`
- Python test: `tests/test_cloud_tasks_scrollable_diff_rs.py`

## Validation

- `python -m pytest tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py -q --tb=short` -> `30 passed`
- `python -m py_compile pycodex/cloud_tasks/__init__.py pycodex/cloud_tasks/scrollable_diff.py tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py` -> passed

## Remaining crate gaps

`codex-cloud-tasks` remains `module_progress`; remaining modules include `src/app.rs`, `src/cli.rs`, `src/new_task.rs`, `src/ui.rs`, and broader runtime command orchestration in `src/lib.rs`.
