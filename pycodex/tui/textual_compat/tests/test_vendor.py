from __future__ import annotations

from pathlib import Path

from pycodex.vendor import import_vendored, vendor_packages_path
from pycodex.tui import textual_compat


def _assert_under_vendor(module) -> None:
    origin = Path(module.__file__).resolve()
    origin.relative_to(vendor_packages_path().resolve())


def test_import_vendored_loads_textual_and_rich_from_vendor_tree() -> None:
    textual = import_vendored("textual")
    rich = import_vendored("rich")

    _assert_under_vendor(textual)
    _assert_under_vendor(rich)
    assert textual.__version__ == "0.43.2"


def test_textual_compat_lazy_exports_core_textual_api_from_vendor_tree() -> None:
    app_module = textual_compat.load_textual_module("textual.app")
    widget_module = textual_compat.load_textual_module("textual.widget")
    events_module = textual_compat.events

    _assert_under_vendor(app_module)
    _assert_under_vendor(widget_module)
    _assert_under_vendor(events_module)
    assert textual_compat.App.__module__ == "textual.app"
    assert textual_compat.Widget.__module__ == "textual.widget"
    assert textual_compat.ComposeResult is app_module.ComposeResult
    assert textual_compat.TextArea.__module__ == "textual.widgets._text_area"


def test_textual_compat_lazy_exports_rich_api_from_vendor_tree() -> None:
    text_module = textual_compat.load_textual_module("rich.text")
    style_module = textual_compat.load_textual_module("rich.style")

    _assert_under_vendor(text_module)
    _assert_under_vendor(style_module)
    assert textual_compat.Text.__module__ == "rich.text"
    assert textual_compat.Style.__module__ == "rich.style"


def test_verify_textual_runtime_checks_core_modules() -> None:
    textual_compat.verify_textual_runtime()
