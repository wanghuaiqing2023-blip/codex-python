"""Textual compatibility boundary for pycodex TUI.

This package exposes the approved subset of vendored Textual. TUI modules
should import Textual APIs from here, not directly from ``textual`` or
``pycodex.vendor._packages``.
"""

from __future__ import annotations

from types import ModuleType
from typing import Any

from pycodex.vendor import VendoredImportError
from pycodex.vendor import assert_vendored_module
from pycodex.vendor import ensure_vendor_packages_on_path
from pycodex.vendor import import_vendored
from pycodex.vendor import vendor_packages_path

_EXPORTS: dict[str, tuple[str, str | None]] = {
    "App": ("textual.app", "App"),
    "ComposeResult": ("textual.app", "ComposeResult"),
    "Widget": ("textual.widget", "Widget"),
    "Container": ("textual.containers", "Container"),
    "Horizontal": ("textual.containers", "Horizontal"),
    "Vertical": ("textual.containers", "Vertical"),
    "Input": ("textual.widgets", "Input"),
    "RichLog": ("textual.widgets", "RichLog"),
    "Static": ("textual.widgets", "Static"),
    "TextArea": ("textual.widgets", "TextArea"),
    "events": ("textual.events", None),
    "Text": ("rich.text", "Text"),
    "Style": ("rich.style", "Style"),
}


def load_textual_module(module_name: str) -> ModuleType:
    """Load a vendored Textual/Rich module and verify its origin."""

    return import_vendored(module_name)


def verify_textual_runtime() -> None:
    """Verify the core vendored Textual runtime modules resolve locally."""

    for module_name in ("textual", "textual.app", "textual.widget", "rich", "rich.text"):
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
    "App",
    "ComposeResult",
    "Container",
    "Horizontal",
    "Input",
    "RichLog",
    "Style",
    "Static",
    "Text",
    "TextArea",
    "VendoredImportError",
    "Vertical",
    "Widget",
    "assert_vendored_module",
    "ensure_vendor_packages_on_path",
    "events",
    "load_textual_module",
    "vendor_packages_path",
    "verify_textual_runtime",
]
