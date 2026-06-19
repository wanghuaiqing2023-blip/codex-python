"""Config namespace ported from ``app-server/src/config/mod.rs``.

The Rust parent module only declares the crate-private
``external_agent_config`` child module. Python keeps the same namespace shape
so the child implementation can live under ``pycodex.app_server.config`` when
ported.
"""

from __future__ import annotations

from dataclasses import dataclass

RUST_MODULE = "codex-app-server/src/config/mod.rs"
EXTERNAL_AGENT_CONFIG_MODULE = "external_agent_config"


@dataclass(frozen=True)
class ConfigChildModule:
    rust_name: str
    python_name: str
    visibility: str


CHILD_MODULES: tuple[ConfigChildModule, ...] = (
    ConfigChildModule(
        rust_name=EXTERNAL_AGENT_CONFIG_MODULE,
        python_name="pycodex.app_server.config.external_agent_config",
        visibility="pub(crate)",
    ),
)


def child_module_names() -> tuple[str, ...]:
    return tuple(child.rust_name for child in CHILD_MODULES)


__all__ = [
    "CHILD_MODULES",
    "EXTERNAL_AGENT_CONFIG_MODULE",
    "ConfigChildModule",
    "RUST_MODULE",
    "child_module_names",
]
