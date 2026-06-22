# codex-app-server-test-client src/main.rs status

Rust module: `codex/codex-rs/app-server-test-client/src/main.rs`

Python module: `pycodex/app_server_test_client/__main__.py`

Status: `complete`

## Contract

Rust `src/main.rs`:

- builds a current-thread Tokio runtime with all drivers enabled
- blocks on `codex_app_server_test_client::run()`
- returns the `anyhow::Result<()>` from that async run

Python mirrors this entrypoint as `main(run_callable=run)`, using
`asyncio.run(...)` as the single-thread event-loop boundary and returning the
async callable's result. The injectable callable keeps this module testable.

## Evidence

- Rust source: `codex/codex-rs/app-server-test-client/src/main.rs`
- Python source: `pycodex/app_server_test_client/__main__.py`
- Python test: `tests/test_app_server_test_client_main_rs.py`

Focused validation passed:

```text
python -m pytest -q tests/test_app_server_test_client_lib_rs.py tests/test_app_server_test_client_main_rs.py
45 passed
```
