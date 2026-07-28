"""Rust-aligned owner for ``codex-otel::metrics.timer``."""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import http.client
import contextvars
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

class Timer:
    def __init__(
        self,
        name: str | None = None,
        tags: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
        client: Any | None = None,
    ) -> None:
        self.name = name
        self.tags = [(str(key), str(value)) for key, value in tags]
        self.client = client
        self.started_at = time.monotonic()

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started_at) * 1000)

    def record(self, additional_tags: list[tuple[str, str]] | tuple[tuple[str, str], ...] = ()) -> None:
        if self.client is None or self.name is None:
            return
        tags = [(str(key), str(value)) for key, value in additional_tags]
        tags.extend(self.tags)
        self.client.record_duration(self.name, self.elapsed_ms(), tags)

    def __del__(self) -> None:
        try:
            self.record(())
        except Exception:
            return


__all__ = [name for name in globals() if not name.startswith("_")]
