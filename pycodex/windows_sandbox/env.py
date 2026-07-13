"""Environment preparation for restricted Windows processes.

Rust owner: ``codex-windows-sandbox::env`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import MutableMapping


def normalize_null_device_env(env_map: MutableMapping[str, str]) -> None:
    for key, value in tuple(env_map.items()):
        if value.strip().lower() in {"/dev/null", r"\\dev\\null"}:
            env_map[key] = "NUL"


def ensure_non_interactive_pager(env_map: MutableMapping[str, str]) -> None:
    env_map.setdefault("GIT_PAGER", "more.com")
    env_map.setdefault("PAGER", "more.com")
    env_map.setdefault("LESS", "")


def inherit_path_env(env_map: MutableMapping[str, str]) -> None:
    for key in ("PATH", "PATHEXT"):
        if key not in env_map and (value := os.environ.get(key)) is not None:
            env_map[key] = value


def apply_no_network_to_env(
    env_map: MutableMapping[str, str],
    *,
    denybin_dir: str | Path | None = None,
) -> Path:
    env_map["SBX_NONET_ACTIVE"] = "1"
    defaults = {
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "localhost,127.0.0.1,::1",
        "PIP_NO_INDEX": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "NPM_CONFIG_OFFLINE": "true",
        "CARGO_NET_OFFLINE": "true",
        "GIT_HTTP_PROXY": "http://127.0.0.1:9",
        "GIT_HTTPS_PROXY": "http://127.0.0.1:9",
        "GIT_SSH_COMMAND": "cmd /c exit 1",
        "GIT_ALLOW_PROTOCOLS": "",
    }
    for key, value in defaults.items():
        env_map.setdefault(key, value)

    base = Path(denybin_dir) if denybin_dir is not None else Path.home() / ".sbx-denybin"
    base.mkdir(parents=True, exist_ok=True)
    for tool in ("ssh", "scp"):
        for extension in (".bat", ".cmd"):
            path = base / f"{tool}{extension}"
            if not path.exists():
                path.write_bytes(b"@echo off\r\nexit /b 1\r\n")
    for tool in ("curl", "wget"):
        for extension in (".bat", ".cmd"):
            path = base / f"{tool}{extension}"
            if path.exists():
                path.unlink()

    existing_path = env_map.get("PATH", os.environ.get("PATH", ""))
    prefix = str(base)
    if not existing_path.split(";", 1)[0].lower() == prefix.lower():
        env_map["PATH"] = prefix + (";" + existing_path if existing_path else "")
    _reorder_pathext_for_stubs(env_map)
    return base


def _reorder_pathext_for_stubs(env_map: MutableMapping[str, str]) -> None:
    raw = env_map.get("PATHEXT", os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD"))
    extensions = [entry for entry in raw.split(";") if entry]
    front = [entry for wanted in (".BAT", ".CMD") for entry in extensions if entry.upper() == wanted]
    rest = [entry for entry in extensions if entry.upper() not in {".BAT", ".CMD"}]
    env_map["PATHEXT"] = ";".join((*front, *rest))


__all__ = [
    "apply_no_network_to_env",
    "ensure_non_interactive_pager",
    "inherit_path_env",
    "normalize_null_device_env",
]
