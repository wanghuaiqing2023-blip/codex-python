"""Independent Rust/Python parity evidence harness.

The package observes the product repository but never owns product behavior.
"""

from pathlib import Path
import sys


# Keep interpreter caches inside the Harness-owned artifact boundary.
sys.pycache_prefix = str(Path(__file__).resolve().parent / ".artifacts" / "pycache")
sys.dont_write_bytecode = True

from .model import Evidence, Finding, LayerResult, MappingStatus, Verdict

__all__ = [
    "Evidence",
    "Finding",
    "LayerResult",
    "MappingStatus",
    "Verdict",
]
