# pycodex.sandboxing Test Alignment

Rust crate: `codex-sandboxing`

## Module Status

| Rust module | Python mapping | Status | Evidence |
| --- | --- | --- | --- |
| `src/manager.rs` | `pycodex/sandboxing/manager.py`; existing compatibility helpers in `pycodex/core/sandboxing.py`, `pycodex/core/sandbox_tags.py`, `pycodex/linux_sandbox/__init__.py`, `pycodex/sandboxing/seatbelt.py`, `pycodex/sandboxing/bwrap.py`, and `pycodex/protocol/models.py` | complete_candidate | Rust manager selection, transform request/response shape, additional-permission effective profile behavior, macOS Seatbelt argv wrapping, Linux helper argv wrapping, WSL1/bubblewrap guard, arg0 aliasing, and legacy compatibility policy projection are represented. Existing Rust-derived tests in `tests/test_core_sandboxing.py` cover compatibility policy projection; broader pytest validation is deferred until the crate functional code is complete. |
| `src/policy_transforms.rs` | `pycodex/sandboxing/policy_transforms.py`; existing support in `pycodex/core/tools/handlers/utils.py`, `pycodex/core/sandbox_tags.py`, and `pycodex/protocol/models.py` | complete_candidate | Rust additional-permission normalization, merge/intersection helpers, glob scan-depth merging, effective file-system/network/permission-profile projection, and platform-sandbox requirement checks are exposed through the crate package. Existing Rust-derived coverage lives in `tests/test_core_sandbox_tags.py`, `tests/test_core_state_turn.py`, `tests/test_core_handler_utils.py`, and `tests/test_core_tool_runtimes.py`; actual pytest remains deferred until crate functional code is complete. |
| `src/landlock.rs` | `pycodex/sandboxing/landlock.py`; shared implementation in `pycodex/linux_sandbox/__init__.py` | complete_candidate | Rust `CODEX_LINUX_SANDBOX_ARG0`, `allow_network_for_proxy`, `create_linux_sandbox_command_args`, and `create_linux_sandbox_command_args_for_permission_profile` are exposed through the crate package. Existing Rust-derived coverage lives in `tests/test_core_spawn_landlock.py`; actual pytest remains deferred until crate functional code is complete. |
| `src/bwrap.rs` | `pycodex/sandboxing/bwrap.py` | complete_candidate | Rust bubblewrap warning constants, system-bwrap prerequisite decision, WSL1 `/proc/version` detection, user-namespace stderr failure detection, timeout/error-tolerant probe behavior, and PATH search excluding workspace-local `bwrap` candidates are represented. Actual pytest remains deferred until crate functional code is complete. |
| `src/seatbelt.rs` | `pycodex/sandboxing/seatbelt.py`; current debug-sandbox adapters in `pycodex/cli/debug_sandbox.py` | complete_candidate | Rust macOS `sandbox-exec` argv shape, proxy loopback-port extraction, managed/restricted/full-network dynamic policy rules, Unix-domain-socket allowlist/allow-all policy generation, protected metadata regex carveouts, unreadable glob regex translation, and split filesystem read/write policy sections are represented. Existing Rust-derived coverage for debug-sandbox adapter shape lives in `tests/test_cli_debug_sandbox.py`; actual pytest remains deferred until crate functional code is complete. |

## Crate Validation

After the crate functional modules reached complete-candidate, focused crate
validation was run:

```text
python -m pytest tests/test_core_sandboxing.py tests/test_core_spawn_landlock.py tests/test_core_sandbox_tags.py tests/test_protocol_permission_models.py
```

Result: `87 passed`.
