# 2026-06-03 — Core approval/network/config export stability fix

## What changed
- Fixed `canonicalize_command_for_approval` export shadowing in `pycodex/core/__init__.py` by aliasing runtime import and removing duplicate `__all__` export.
- Added missing `ConfigEdit` helpers in `pycodex/core/config_edit.py` for notice/migration state and made `ConfigEdit.set_path` validate mapping values immediately.
- Finished `pycodex/core/network_approval.py` parity fixes:
  - corrected approval service type error text,
  - hardened policy argument normalization,
  - fixed owner/non-owner denial flow for policy-based cached host blocks,
  - preserved expected normalized target behavior for denied policy decisions,
  - adjusted pending cleanup semantics around review amendment.

## Validation
- `python -m pytest -q tests/test_core_network_approval.py`
- `python -m pytest -q tests/test_core_config_edit.py tests/test_core_command_canonicalization.py`

## Notes
- Full suite remains with many fails in app-server/plugin/streaming/depth areas that are outside the current core slice.
