"""Path policy for read-only repository inputs and harness-owned artifacts."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile


HARNESS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = HARNESS_ROOT.parent
ARTIFACT_ROOT = HARNESS_ROOT / ".artifacts"


def artifact_path(*parts: str) -> Path:
    path = (ARTIFACT_ROOT.joinpath(*parts)).resolve()
    if path != ARTIFACT_ROOT.resolve() and ARTIFACT_ROOT.resolve() not in path.parents:
        raise ValueError(f"artifact path escapes .artifacts: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class ArtifactWorkspace:
    """Temporary workspace guaranteed to live below the harness artifact root."""

    def __init__(self, prefix: str = "scenario-") -> None:
        self._prefix = prefix
        self.path: Path | None = None

    def __enter__(self) -> Path:
        base = artifact_path("tmp")
        base.mkdir(parents=True, exist_ok=True)
        self.path = Path(tempfile.mkdtemp(prefix=self._prefix, dir=base))
        return self.path

    def __exit__(self, *_: object) -> None:
        if self.path is not None:
            shutil.rmtree(self.path, ignore_errors=True)


def repo_path(relative: str) -> Path:
    path = (REPO_ROOT / relative).resolve()
    if path != REPO_ROOT.resolve() and REPO_ROOT.resolve() not in path.parents:
        raise ValueError(f"repository path escapes root: {relative}")
    return path

