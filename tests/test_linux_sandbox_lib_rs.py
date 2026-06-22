import sys
import types

import pytest

from pycodex import linux_sandbox


def test_run_main_rejects_non_linux_targets(monkeypatch) -> None:
    # Rust crate/module: codex-linux-sandbox/src/lib.rs run_main on non-Linux targets.
    monkeypatch.setattr(linux_sandbox.sys, "platform", "win32")

    with pytest.raises(RuntimeError, match="codex-linux-sandbox is only supported on Linux"):
        linux_sandbox.run_main()


def test_run_main_delegates_to_linux_run_main_on_linux(monkeypatch) -> None:
    # Rust crate/module: codex-linux-sandbox/src/lib.rs run_main delegates to
    # linux_run_main::run_main on Linux.
    module_name = "pycodex.linux_sandbox.linux_run_main"
    fake_module = types.ModuleType(module_name)

    def fake_run_main():
        raise SystemExit(27)

    fake_module.run_main = fake_run_main
    monkeypatch.setattr(linux_sandbox.sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, module_name, fake_module)

    with pytest.raises(SystemExit) as exc:
        linux_sandbox.run_main()

    assert exc.value.code == 27
