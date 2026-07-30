from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class DaemonSettings:
    remote_control_enabled: bool = False

    @classmethod
    async def load(cls, path: Path) -> "DaemonSettings":
        def read() -> DaemonSettings:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return cls()
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"failed to read daemon settings {path}: {exc}") from exc
            if not isinstance(raw, dict):
                raise RuntimeError(f"failed to parse daemon settings {path}: expected object")
            enabled = raw.get("remoteControlEnabled", False)
            if not isinstance(enabled, bool):
                raise RuntimeError(
                    f"failed to parse daemon settings {path}: "
                    "remoteControlEnabled must be a boolean"
                )
            return cls(remote_control_enabled=enabled)

        return await asyncio.to_thread(read)

    async def save(self, path: Path) -> None:
        def write() -> None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        {"remoteControlEnabled": self.remote_control_enabled},
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            except OSError as exc:
                raise RuntimeError(f"failed to write daemon settings {path}: {exc}") from exc

        await asyncio.to_thread(write)


__all__ = ["DaemonSettings"]
