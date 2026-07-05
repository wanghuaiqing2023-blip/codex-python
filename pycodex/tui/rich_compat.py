"""Vendored Rich compatibility boundary for pycodex TUI."""

from __future__ import annotations

from types import ModuleType
from typing import Any

from pycodex.vendor import VendoredImportError
from pycodex.vendor import assert_vendored_module
from pycodex.vendor import ensure_vendor_packages_on_path
from pycodex.vendor import import_vendored
from pycodex.vendor import vendor_packages_path

_EXPORTS: dict[str, tuple[str, str | None]] = {
    "Text": ("rich.text", "Text"),
    "Style": ("rich.style", "Style"),
}


def load_rich_module(module_name: str) -> ModuleType:
    """Load a vendored Rich module and verify its origin."""

    return import_vendored(module_name)


def verify_rich_runtime() -> None:
    """Verify the core vendored Rich modules resolve locally."""

    for module_name in ("rich", "rich.text", "rich.style"):
        import_vendored(module_name)


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    module = import_vendored(module_name)
    if attr_name is None:
        return module
    return getattr(module, attr_name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))


__all__ = [
    "Style",
    "Text",
    "VendoredImportError",
    "assert_vendored_module",
    "ensure_vendor_packages_on_path",
    "load_rich_module",
    "vendor_packages_path",
    "verify_rich_runtime",
]
