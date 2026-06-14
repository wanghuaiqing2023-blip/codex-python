"""Vendored third-party package import helpers.

This module owns access to packages extracted under ``pycodex/vendor/_packages``.
It intentionally centralizes path setup and provenance checks so project code
can avoid accidental imports from globally installed packages.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Iterable

_VENDOR_ROOT = Path(__file__).resolve().parent
_VENDOR_PACKAGES = _VENDOR_ROOT / "_packages"
_VENDOR_DIST_INFO = _VENDOR_ROOT / "_dist_info"


class VendoredImportError(ImportError):
    """Raised when a vendored package cannot be imported safely."""


def vendor_packages_path() -> Path:
    """Return the directory containing extracted vendored import roots."""

    return _VENDOR_PACKAGES


def ensure_vendor_packages_on_path() -> Path:
    """Prepend the vendored package root to ``sys.path`` if needed.

    Textual and its dependencies use normal top-level imports internally. Once a
    vendored framework is selected, the vendored root must stay ahead of site
    packages so lazy imports continue to resolve to the audited copies.
    """

    path = str(_VENDOR_PACKAGES)
    if path not in sys.path:
        sys.path.insert(0, path)
    elif sys.path[0] != path:
        sys.path.remove(path)
        sys.path.insert(0, path)
    dist_info_path = str(_VENDOR_DIST_INFO)
    if dist_info_path not in sys.path:
        sys.path.insert(1, dist_info_path)
    elif sys.path.index(dist_info_path) != 1:
        sys.path.remove(dist_info_path)
        sys.path.insert(1, dist_info_path)
    return _VENDOR_PACKAGES


def import_vendored(module_name: str) -> ModuleType:
    """Import ``module_name`` from the vendored package root.

    The loaded module, and any already-loaded parent package, must resolve under
    ``pycodex/vendor/_packages``. This catches accidental use of globally
    installed packages with the same top-level name.
    """

    ensure_vendor_packages_on_path()
    module = importlib.import_module(module_name)
    assert_vendored_module(module, module_name)
    return module


def assert_vendored_module(module: ModuleType, module_name: str | None = None) -> None:
    """Ensure ``module`` was loaded from the vendored package tree."""

    origin = getattr(module, "__file__", None)
    if origin is None:
        raise VendoredImportError(f"vendored module {module_name or module.__name__!r} has no __file__")
    try:
        Path(origin).resolve().relative_to(_VENDOR_PACKAGES.resolve())
    except ValueError as exc:
        raise VendoredImportError(
            f"module {module_name or module.__name__!r} was not loaded from vendored packages: {origin}"
        ) from exc


def assert_vendored_modules(module_names: Iterable[str]) -> None:
    """Import and validate several vendored modules."""

    for module_name in module_names:
        import_vendored(module_name)


__all__ = [
    "VendoredImportError",
    "assert_vendored_module",
    "assert_vendored_modules",
    "ensure_vendor_packages_on_path",
    "import_vendored",
    "vendor_packages_path",
]
