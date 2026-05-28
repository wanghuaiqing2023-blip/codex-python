"""Python port of Codex.

The package keeps its public entry surfaces close to the upstream layout where
common modules can be imported directly from :mod:`pycodex`.
"""

from __future__ import annotations

from importlib import import_module

__version__ = "0.1.0"

_TOP_LEVEL_MODULES = ("cli", "core", "protocol", "login", "tui", "sandboxing")

__all__ = ["__version__", *_TOP_LEVEL_MODULES]


def __getattr__(name: str):
    if name in _TOP_LEVEL_MODULES:
        return import_module(f"{__name__}.{name}")
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(__all__)
