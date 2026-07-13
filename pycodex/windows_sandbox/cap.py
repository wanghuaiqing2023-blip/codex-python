"""Persistent capability SIDs for Windows sandbox roots.

Rust owner: ``codex-windows-sandbox::cap`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .path_normalization import canonical_path_key, canonicalize_path


@dataclass
class CapSids:
    workspace: str
    readonly: str
    workspace_by_cwd: dict[str, str] = field(default_factory=dict)
    writable_root_by_path: dict[str, str] = field(default_factory=dict)


def cap_sid_file(codex_home: str | Path) -> Path:
    return Path(codex_home) / "cap_sid"


def load_or_create_cap_sids(codex_home: str | Path) -> CapSids:
    path = cap_sid_file(codex_home)
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    return CapSids(
                        workspace=str(data["workspace"]),
                        readonly=str(data["readonly"]),
                        workspace_by_cwd=_string_map(data.get("workspace_by_cwd", {})),
                        writable_root_by_path=_string_map(data.get("writable_root_by_path", {})),
                    )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                pass
        elif text:
            caps = CapSids(workspace=text, readonly=_make_random_cap_sid_string())
            _persist_caps(path, caps)
            return caps

    caps = CapSids(
        workspace=_make_random_cap_sid_string(),
        readonly=_make_random_cap_sid_string(),
    )
    _persist_caps(path, caps)
    return caps


def workspace_cap_sid_for_cwd(codex_home: str | Path, cwd: str | Path) -> str:
    path = cap_sid_file(codex_home)
    caps = load_or_create_cap_sids(codex_home)
    key = canonical_path_key(cwd)
    sid = caps.workspace_by_cwd.get(key)
    if sid is not None:
        return sid
    sid = _make_random_cap_sid_string()
    caps.workspace_by_cwd[key] = sid
    _persist_caps(path, caps)
    return sid


def writable_root_cap_sid_for_path(codex_home: str | Path, root: str | Path) -> str:
    path = cap_sid_file(codex_home)
    caps = load_or_create_cap_sids(codex_home)
    key = canonical_path_key(root)
    sid = caps.writable_root_by_path.get(key)
    if sid is not None:
        return sid
    sid = _make_random_cap_sid_string()
    caps.writable_root_by_path[key] = sid
    _persist_caps(path, caps)
    return sid


def workspace_write_cap_sid_for_root(
    codex_home: str | Path,
    cwd: str | Path,
    root: str | Path,
) -> str:
    if canonical_path_key(root) == canonical_path_key(cwd):
        return workspace_cap_sid_for_cwd(codex_home, cwd)
    return writable_root_cap_sid_for_path(codex_home, root)


def workspace_write_root_contains_path(root: str | Path, path: str | Path) -> bool:
    canonical_root = canonicalize_path(root)
    canonical_path = canonicalize_path(path)
    try:
        canonical_path.relative_to(canonical_root)
    except ValueError:
        return False
    return True


def workspace_write_root_overlaps_path(root: str | Path, path: str | Path) -> bool:
    return workspace_write_root_contains_path(root, path) or workspace_write_root_contains_path(path, root)


def workspace_write_root_specificity(root: str | Path) -> int:
    return len(canonicalize_path(root).parts)


def _make_random_cap_sid_string() -> str:
    values = (secrets.randbits(32) for _ in range(4))
    return "S-1-5-21-" + "-".join(str(value) for value in values)


def _persist_caps(path: Path, caps: CapSids) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(caps), separators=(",", ":")), encoding="utf-8")


def _string_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


__all__ = [
    "CapSids",
    "cap_sid_file",
    "load_or_create_cap_sids",
    "workspace_cap_sid_for_cwd",
    "workspace_write_cap_sid_for_root",
    "workspace_write_root_contains_path",
    "workspace_write_root_overlaps_path",
    "workspace_write_root_specificity",
    "writable_root_cap_sid_for_path",
]
