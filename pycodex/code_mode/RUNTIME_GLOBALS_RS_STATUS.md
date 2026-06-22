# codex-code-mode runtime/globals.rs status

Rust crate: `codex-code-mode`

Rust module: `codex/codex-rs/code-mode/src/runtime/globals.rs`

Python module: `pycodex.core.tools.code_mode`

Status: `complete` for the dependency-light global registration projection
contract.

## Behavior Contract

- `install_globals(...)` removes the host globals `console`, `Atomics`,
  `SharedArrayBuffer`, and `WebAssembly`.
- It installs the fixed helper names `clearTimeout`, `setTimeout`, `text`,
  `image`, `store`, `load`, `notify`, `yield_control`, and `exit`.
- It exposes enabled tools under the `tools` global using each tool's
  normalized `global_name`.
- Tool callback data is the Rust `enumerate()` index serialized as a string.
- `ALL_TOOLS` is an ordered array of objects containing each enabled tool's
  `name` and `description`.
- Duplicate `global_name` values follow object-assignment semantics: later
  entries replace earlier entries in the `tools` object, while `ALL_TOOLS`
  keeps all entries in order.

Concrete V8 function-template creation, callback data attachment, object
mutation failure paths, and global object mutation remain non-blocking
operational/runtime checks.

## Evidence

- Rust source: `codex/codex-rs/code-mode/src/runtime/globals.rs`
- Rust anchors:
  - `install_globals`
  - `build_tools_object`
  - `build_all_tools_value`
  - `helper_function`
  - `tool_function`
  - `set_global`
  - `delete_global`
- Python implementation:
  - `RUNTIME_REMOVED_GLOBALS`
  - `RUNTIME_GLOBAL_HELPERS`
  - `build_all_tools_metadata(...)`
  - `build_runtime_globals_projection(...)`
- Python tests:
  - `tests/test_core_code_mode.py::CodeModeCoreTests::test_build_all_tools_metadata_matches_runtime_globals_shape`

## Validation

```powershell
python -m pytest tests/test_core_code_mode.py -q --tb=short
python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short
python -m pytest tests/test_external_crate_interfaces.py -k code_mode -q --tb=short
python -m py_compile pycodex\core\tools\code_mode\__init__.py pycodex\code_mode\__init__.py tests\test_core_code_mode.py tests\test_codex_code_mode_lib_rs.py
```

Latest result on 2026-06-21:

- `python -m pytest tests/test_core_code_mode.py -q --tb=short`
  passed with `43 passed`.
- `python -m pytest tests/test_codex_code_mode_lib_rs.py tests/test_core_code_mode.py -q --tb=short`
  passed with `49 passed`.
- `python -m pytest tests/test_external_crate_interfaces.py -k code_mode -q --tb=short`
  passed with `1 passed, 17 deselected`.
- `python -m py_compile pycodex\core\tools\code_mode\__init__.py pycodex\code_mode\__init__.py tests\test_core_code_mode.py tests\test_codex_code_mode_lib_rs.py`
  passed.

## Non-blocking runtime notes

None for the dependency-light global registration projection contract.
Concrete V8 function allocation, callback installation, global object
mutation, and live JavaScript execution remain optional operational/runtime
checks for the broader crate.
