"""Unit-level import contracts for every ``pycodex.core`` module.

These tests are intentionally broad but shallow: each core module must be safe
to import in isolation, and package/module public export lists must only expose
string names.  Deeper behavior remains covered by the focused ``test_core_*``
files for each Rust-aligned module.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

import pycodex.core as core


def _core_module_names() -> list[str]:
    prefix = core.__name__ + "."
    return sorted(
        module_info.name
        for module_info in pkgutil.walk_packages(core.__path__, prefix)
    )


def test_every_core_module_imports() -> None:
    failures: list[tuple[str, str]] = []
    for module_name in _core_module_names():
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - assertion reports module name
            failures.append((module_name, f"{type(exc).__name__}: {exc}"))

    assert failures == []


def test_core_module_all_exports_are_string_names() -> None:
    failures: list[tuple[str, object]] = []
    for module_name in _core_module_names():
        module = importlib.import_module(module_name)
        exported = getattr(module, "__all__", None)
        if exported is None:
            continue
        if not isinstance(exported, (list, tuple)):
            failures.append((module_name, exported))
            continue
        bad_names = [name for name in exported if not isinstance(name, str)]
        if bad_names:
            failures.append((module_name, bad_names))

    assert failures == []


def test_core_root_exports_resolve_to_objects() -> None:
    exported = getattr(core, "__all__", ())
    missing = [name for name in exported if not hasattr(core, name)]

    assert missing == []
    assert isinstance(core, ModuleType)
