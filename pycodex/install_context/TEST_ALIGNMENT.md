# codex-install-context test alignment

Rust crate: `codex-install-context`

Python package: `pycodex/install_context`

Status: `complete`

Certified modules:

- `codex/codex-rs/install-context/src/lib.rs` -> `pycodex/install_context/__init__.py`

Rust-test/source-contract coverage:

- `detects_standalone_install_from_release_layout`.
- `standalone_rg_falls_back_when_resources_are_missing`.
- `detects_package_layout_independently_from_install_method`.
- `standalone_package_layout_keeps_standalone_install_method`.
- `npm_managed_package_keeps_package_layout`.
- `standalone_package_rg_falls_back_when_codex_path_is_missing`.
- `bundled_file_lookups_ignore_directories`.
- `npm_and_bun_take_precedence`.
- `brew_is_detected_on_macos_prefixes`.

Validation:

- `python -m pytest tests/test_install_context_lib_rs.py -q`
- `python -m py_compile pycodex/install_context/__init__.py tests/test_install_context_lib_rs.py`
