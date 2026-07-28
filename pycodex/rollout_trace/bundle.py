"""Rust-aligned owner for ``codex-rollout-trace::bundle``."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

MANIFEST_FILE_NAME = "manifest.json"

RAW_EVENT_LOG_FILE_NAME = "trace.jsonl"

PAYLOADS_DIR_NAME = "payloads"

REDUCED_STATE_FILE_NAME = "state.json"
