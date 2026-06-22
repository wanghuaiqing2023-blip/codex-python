import pytest

from pycodex.linux_sandbox import __main__ as linux_sandbox_main


def test_main_delegates_to_crate_root_run_main(monkeypatch) -> None:
    # Rust crate/module: codex-linux-sandbox/src/main.rs main delegates to
    # codex_linux_sandbox::run_main without argument transformation.
    called = []

    def fake_run_main():
        called.append(True)
        raise SystemExit(42)

    monkeypatch.setattr(linux_sandbox_main, "run_main", fake_run_main)

    with pytest.raises(SystemExit) as exc:
        linux_sandbox_main.main()

    assert exc.value.code == 42
    assert called == [True]
