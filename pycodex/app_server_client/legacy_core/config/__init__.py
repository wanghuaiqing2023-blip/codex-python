"""Re-exports owned by Rust ``legacy_core::config``."""

from pycodex.core.config import *

from . import edit

__all__ = [name for name in globals() if not name.startswith("_")]
