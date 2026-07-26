from __future__ import annotations

from io import StringIO
from pathlib import Path


class _Metrics:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, tuple[tuple[str, str], ...]]] = []

    def counter(
        self,
        name: str,
        inc: int,
        tags: tuple[tuple[str, str], ...],
    ) -> None:
        self.calls.append((name, inc, tags))


def test_wfp_setup_success_logs_and_emits_metric(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from pycodex.windows_sandbox import wfp_setup

    messages: list[str] = []
    metrics = _Metrics()
    monkeypatch.setattr(
        wfp_setup,
        "install_wfp_filters_for_account",
        lambda _account: 12,
    )

    wfp_setup.install_wfp_filters(
        tmp_path,
        "Codex Offline",
        metrics,
        messages.append,
    )

    assert messages == [
        "WFP setup succeeded for Codex Offline with 12 installed filters"
    ]
    assert metrics.calls == [
        (
            "codex.windows_sandbox.wfp_setup_success",
            1,
            (
                ("target_account", "Codex_Offline"),
                ("installed_filter_count", "12"),
            ),
        )
    ]


def test_wfp_setup_failure_is_nonfatal_and_emits_metric(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from pycodex.windows_sandbox import wfp_setup

    messages: list[str] = []
    metrics = _Metrics()

    def fail(_account: str) -> int:
        raise OSError("access denied")

    monkeypatch.setattr(wfp_setup, "install_wfp_filters_for_account", fail)
    wfp_setup.install_wfp_filters(
        tmp_path,
        "offline",
        metrics,
        messages.append,
    )

    assert messages == [
        "WFP setup failed for offline: access denied; continuing elevated setup"
    ]
    assert metrics.calls == [
        (
            "codex.windows_sandbox.wfp_setup_failure",
            1,
            (
                ("target_account", "offline"),
                ("message", "access_denied"),
            ),
        )
    ]


def test_setup_binary_routes_wfp_through_wfp_setup_owner(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from pycodex.windows_sandbox.bin.setup_main import win

    calls: list[tuple[Path, str, object]] = []
    monkeypatch.setattr(win, "provision_sandbox_users", lambda *_args: ("a", "b"))
    monkeypatch.setattr(win, "hide_newly_created_users", lambda *_args: None)
    monkeypatch.setattr(win, "resolve_account_sid_string", lambda value: value)
    monkeypatch.setattr(win, "install_offline_firewall_rules", lambda *_args: None)
    monkeypatch.setattr(
        win,
        "install_wfp_filters",
        lambda home, account, otel, log: calls.append((home, account, otel)),
    )
    monkeypatch.setattr(win, "_apply_deny_read_acls", lambda *_args: None)
    monkeypatch.setattr(win, "_spawn_read_acl_helper_if_needed", lambda *_args: None)
    monkeypatch.setattr(win, "_apply_write_acls", lambda *_args: None)
    monkeypatch.setattr(win, "_write_setup_state", lambda *_args: None)
    monkeypatch.setattr(win, "_lock_setup_dirs", lambda *_args: None)

    win._run_setup_full(
        {
            "codex_home": str(tmp_path),
            "offline_username": "offline",
            "online_username": "online",
            "command_cwd": str(tmp_path),
            "read_roots": [],
            "write_roots": [],
            "deny_read_paths": [],
            "deny_write_paths": [],
            "proxy_ports": [],
            "allow_local_binding": False,
            "refresh_only": False,
            "otel": {"environment": "test"},
        },
        StringIO(),
    )

    assert calls == [(tmp_path, "offline", {"environment": "test"})]


def test_setup_metric_sanitizer_is_owned_by_setup_error() -> None:
    import pycodex.windows_sandbox as sandbox
    from pycodex.windows_sandbox import setup_error

    assert (
        sandbox.sanitize_setup_metric_tag_value
        is setup_error.sanitize_setup_metric_tag_value
    )
    assert setup_error.sanitize_setup_metric_tag_value("a b/c") == "a_b_c"
