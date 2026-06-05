# Canonical crate migration batch 5: remove apply_patch and execpolicy legacy shims

Date: 2026-06-05

## Summary

Removed two legacy `pycodex/core/*` compatibility shims after updating imports to the canonical Rust-tree-aligned packages.

## Removed legacy paths

| Rust crate | Deleted legacy Python path | Canonical Python path | Result |
|---|---|---|---|
| `codex-apply-patch` | `pycodex/core/apply_patch.py` | `pycodex/apply_patch` | deleted |
| `codex-execpolicy` | `pycodex/core/exec_policy.py` | `pycodex/execpolicy` | deleted |

## Import policy

Production and test imports now use canonical paths directly:

- `pycodex.apply_patch`
- `pycodex.execpolicy`

The legacy shim files were deleted. No long-term compatibility shim was retained.

## Additional cycle fixes

Making `pycodex.apply_patch` a true top-level package exposed old core-facade cycles. The following imports were made lazy or type-only:

- `pycodex/apply_patch/__init__.py`: lazy imports for selected `handler_utils` helpers.
- `pycodex/core/turn_diff_tracker.py`: removed top-level `ApplyPatchAction` import.
- `pycodex/core/spec_plan.py`: lazy import for `ApplyPatchHandler`.
- `pycodex/core/unified_exec_handler.py`: lazy imports for apply-patch command execution helpers.
- `pycodex/core/safety.py`: lazy import for `ApplyPatchAction`.

`pycodex.core.__init__` no longer re-exports the `codex-apply-patch` and `codex-execpolicy` symbol sets.

## Validation

- `python -m pytest tests/test_core_apply_patch.py tests/test_core_exec_policy.py tests/test_core_safety.py tests/test_core_network_proxy_loader.py tests/test_core_network_policy_decision.py tests/test_core_tool_runtimes.py tests/test_core_turn_diff_tracker.py tests/test_exec_local_runtime.py -q`: 431 passed, 35 subtests passed.
- After deleting legacy shim files, `python -m pytest tests/test_core_apply_patch.py tests/test_core_exec_policy.py tests/test_core_safety.py tests/test_core_network_proxy_loader.py -q`: 87 passed, 25 subtests passed.
- Post-delete canonical import smoke passed.
- Residual old-coordinate search in Python files for `pycodex.core.apply_patch` and `pycodex.core.exec_policy` returned no matches.