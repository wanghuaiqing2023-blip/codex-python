"""Parity tests for Rust ``codex-login::auth::external_bearer``.

Rust source:
- ``codex/codex-rs/login/src/auth/external_bearer.rs``
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

from pycodex.login.auth.external_bearer import (
    BearerTokenRefresher,
    resolve_provider_auth_program,
    run_provider_auth_command,
)


def _run(coro):
    return asyncio.run(coro)


def _python_command(*args: str, tmp_path: Path) -> dict[str, object]:
    return {
        "command": sys.executable,
        "args": list(args),
        "cwd": tmp_path,
        "timeout_ms": 5000,
        "refresh_interval_ms": 300000,
    }


def _counter_script(tmp_path: Path) -> Path:
    script = tmp_path / "token_counter.py"
    script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import sys",
                "path = Path(sys.argv[1])",
                "raw = path.read_text() if path.exists() else '0'",
                "value = int(raw or '0') + 1",
                "path.write_text(str(value))",
                "print(f'token-{value}')",
            ]
        ),
        encoding="utf-8",
    )
    return script


def test_resolve_provider_auth_program_matches_rust_path_rules(tmp_path: Path) -> None:
    absolute = tmp_path / "provider-auth"

    assert resolve_provider_auth_program(str(absolute), tmp_path) == absolute
    assert resolve_provider_auth_program("scripts/provider-auth", tmp_path) == (
        tmp_path / "scripts/provider-auth"
    )
    assert resolve_provider_auth_program("provider-auth", tmp_path) == Path("provider-auth")


def test_run_provider_auth_command_trims_stdout(tmp_path: Path) -> None:
    config = _python_command("-c", "print('  token-value  ')", tmp_path=tmp_path)

    assert _run(run_provider_auth_command(config)) == "token-value"


def test_run_provider_auth_command_rejects_empty_token(tmp_path: Path) -> None:
    config = _python_command("-c", "print('   ')", tmp_path=tmp_path)

    with pytest.raises(OSError, match="produced an empty token"):
        _run(run_provider_auth_command(config))


def test_run_provider_auth_command_reports_stderr_for_nonzero_exit(tmp_path: Path) -> None:
    config = _python_command(
        "-c",
        "import sys; sys.stderr.write('bad token source'); sys.exit(7)",
        tmp_path=tmp_path,
    )

    with pytest.raises(OSError) as exc_info:
        _run(run_provider_auth_command(config))

    message = str(exc_info.value)
    assert "exited with status" in message
    assert "bad token source" in message


def test_run_provider_auth_command_reports_non_utf8_stdout(tmp_path: Path) -> None:
    config = _python_command(
        "-c",
        "import sys; sys.stdout.buffer.write(b'\\xff')",
        tmp_path=tmp_path,
    )

    with pytest.raises(OSError, match="wrote non-UTF-8 data to stdout"):
        _run(run_provider_auth_command(config))


def test_run_provider_auth_command_times_out(tmp_path: Path) -> None:
    config = _python_command("-c", "import time; time.sleep(1)", tmp_path=tmp_path)
    config["timeout_ms"] = 50

    with pytest.raises(OSError, match="timed out after 50 ms"):
        _run(run_provider_auth_command(config))


def test_bearer_token_refresher_caches_and_refresh_forces_command(tmp_path: Path) -> None:
    counter = tmp_path / "counter.txt"
    script = _counter_script(tmp_path)
    config = _python_command(str(script), str(counter), tmp_path=tmp_path)
    refresher = BearerTokenRefresher.new(config)

    assert refresher.auth_mode() == "api_key"
    assert _run(refresher.resolve()).access_token == "token-1"
    assert _run(refresher.resolve()).access_token == "token-1"
    assert counter.read_text(encoding="utf-8") == "1"

    assert _run(refresher.refresh()).access_token == "token-2"
    assert _run(refresher.resolve()).access_token == "token-2"
    assert counter.read_text(encoding="utf-8") == "2"


def test_bearer_token_refresher_zero_refresh_interval_never_expires_cache(
    tmp_path: Path,
) -> None:
    counter = tmp_path / "counter.txt"
    script = _counter_script(tmp_path)
    config = _python_command(str(script), str(counter), tmp_path=tmp_path)
    config["refresh_interval_ms"] = 0
    refresher = BearerTokenRefresher.new(config)

    assert _run(refresher.resolve()).access_token == "token-1"
    time.sleep(0.01)
    assert _run(refresher.resolve()).access_token == "token-1"
    assert counter.read_text(encoding="utf-8") == "1"


def test_bearer_token_refresher_expired_cache_refetches(tmp_path: Path) -> None:
    counter = tmp_path / "counter.txt"
    script = _counter_script(tmp_path)
    config = _python_command(str(script), str(counter), tmp_path=tmp_path)
    config["refresh_interval_ms"] = 1
    refresher = BearerTokenRefresher.new(config)

    assert _run(refresher.resolve()).access_token == "token-1"
    time.sleep(0.01)
    assert _run(refresher.resolve()).access_token == "token-2"
    assert counter.read_text(encoding="utf-8") == "2"
