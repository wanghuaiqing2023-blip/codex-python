"""Process exit status helpers.

Ported from ``codex/codex-rs/cli/src/exit_status.rs``.
"""

from __future__ import annotations


def exit_code_from_returncode(returncode: int | None) -> int:
    """Return the Codex CLI process exit code for a subprocess return code.

    Rust's Unix implementation preserves normal process exit codes and maps
    signal termination to ``128 + signal``. Python represents signal
    termination as a negative return code, so ``-15`` maps to ``143``.
    Missing status information falls back to ``1``.
    """

    if returncode is None:
        return 1
    if not isinstance(returncode, int):
        raise TypeError("returncode must be an integer or None")
    if returncode < 0:
        return 128 + abs(returncode)
    return returncode
