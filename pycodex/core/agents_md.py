"""AGENTS.md discovery and instruction assembly ported from ``core/src/agents_md.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_PROJECT_DOC_MAX_BYTES = 32 * 1024
DEFAULT_PROJECT_ROOT_MARKERS = (".git",)
DEFAULT_AGENTS_MD_FILENAME = "AGENTS.md"
LOCAL_AGENTS_MD_FILENAME = "AGENTS.override.md"
AGENTS_MD_SEPARATOR = "\n\n--- project-doc ---\n\n"
HIERARCHICAL_AGENTS_MESSAGE = (
    "Files called AGENTS.md commonly appear in many places inside a container - at \"/\", in \"~\", "
    "deep within git repositories, or in any other directory; their location is not limited to "
    "version-controlled folders.\n\n"
    "Their purpose is to pass along human guidance to you, the agent. Such guidance can include coding "
    "standards, explanations of the project layout, steps for building or testing, and even wording that "
    "must accompany a GitHub pull-request description produced by the agent; all of it is to be followed.\n\n"
    "Each AGENTS.md governs the entire directory that contains it and every child directory beneath that "
    "point. Whenever you change a file, you have to comply with every AGENTS.md whose scope covers that "
    "file. Naming conventions, stylistic rules and similar directives are restricted to the code that "
    "falls inside that scope unless the document explicitly states otherwise.\n\n"
    "When two AGENTS.md files disagree, the one located deeper in the directory structure overrides the "
    "higher-level file, while instructions given directly in the prompt by the system, developer, or user "
    "outrank any AGENTS.md content."
)


@dataclass(frozen=True)
class AgentsMdConfig:
    cwd: Path
    codex_home: Path | None = None
    user_instructions: str | None = None
    project_doc_max_bytes: int = DEFAULT_PROJECT_DOC_MAX_BYTES
    project_doc_fallback_filenames: tuple[str, ...] = ()
    project_root_markers: tuple[str, ...] | None = None
    child_agents_md: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "cwd", Path(self.cwd))
        if self.codex_home is not None:
            object.__setattr__(self, "codex_home", Path(self.codex_home))
        object.__setattr__(
            self,
            "project_doc_fallback_filenames",
            tuple(str(name) for name in self.project_doc_fallback_filenames),
        )
        if self.project_root_markers is not None:
            object.__setattr__(
                self,
                "project_root_markers",
                tuple(str(marker) for marker in self.project_root_markers),
            )


@dataclass(frozen=True)
class LoadedAgentsMd:
    contents: str
    path: Path


class AgentsMdManager:
    def __init__(self, config: AgentsMdConfig) -> None:
        self.config = config

    @staticmethod
    def load_global_instructions(
        codex_dir: Path | str | None,
        startup_warnings: list[str] | None = None,
    ) -> LoadedAgentsMd | None:
        if codex_dir is None:
            return None
        warnings = startup_warnings if startup_warnings is not None else []
        base = Path(codex_dir)
        for candidate in (LOCAL_AGENTS_MD_FILENAME, DEFAULT_AGENTS_MD_FILENAME):
            path = base / candidate
            try:
                if not path.is_file():
                    continue
                data = path.read_bytes()
            except FileNotFoundError:
                continue
            except IsADirectoryError:
                continue
            except OSError as exc:
                warnings.append(f"Failed to read global AGENTS.md instructions from `{path}`: {exc}")
                continue

            _warn_invalid_utf8(path, data, "Global", warnings)
            contents = _decode_lossy(data).strip()
            if contents:
                return LoadedAgentsMd(contents, path)
        return None

    def user_instructions(self, startup_warnings: list[str] | None = None) -> str | None:
        warnings = startup_warnings if startup_warnings is not None else []
        docs = self.read_agents_md(warnings)
        output = self.config.user_instructions or ""

        if docs:
            if output:
                output += AGENTS_MD_SEPARATOR
            output += docs

        if self.config.child_agents_md:
            if output:
                output += "\n\n"
            output += HIERARCHICAL_AGENTS_MESSAGE

        return output or None

    def instruction_sources(self) -> list[Path]:
        warnings: list[str] = []
        paths: list[Path] = []
        loaded = self.load_global_instructions(self.config.codex_home, warnings)
        if loaded is not None:
            paths.append(loaded.path)
        paths.extend(self.agents_md_paths())
        return paths

    def read_agents_md(self, startup_warnings: list[str] | None = None) -> str | None:
        warnings = startup_warnings if startup_warnings is not None else []
        max_total = self.config.project_doc_max_bytes
        if max_total == 0:
            return None

        paths = self.agents_md_paths()
        if not paths:
            return None

        remaining = max_total
        parts: list[str] = []
        for path in paths:
            if remaining == 0:
                break
            try:
                if not path.is_file():
                    continue
                data = path.read_bytes()
            except FileNotFoundError:
                continue

            _warn_invalid_utf8(path, data, "Project", warnings)
            if len(data) > remaining:
                data = data[:remaining]
            text = _decode_lossy(data)
            if text.strip():
                parts.append(text)
                remaining = max(remaining - len(data), 0)

        if not parts:
            return None
        return "\n\n".join(parts)

    def agents_md_paths(self) -> list[Path]:
        if self.config.project_doc_max_bytes == 0:
            return []

        current_dir = _normalize_existing_path(self.config.cwd)
        markers = self.config.project_root_markers
        if markers is None:
            markers = DEFAULT_PROJECT_ROOT_MARKERS

        project_root: Path | None = None
        if markers:
            for ancestor in _ancestors(current_dir):
                for marker in markers:
                    if (ancestor / marker).exists():
                        project_root = ancestor
                        break
                if project_root is not None:
                    break

        if project_root is None:
            search_dirs = [current_dir]
        else:
            search_dirs = []
            cursor = current_dir
            while True:
                search_dirs.append(cursor)
                if _same_path(cursor, project_root):
                    break
                parent = cursor.parent
                if parent == cursor:
                    break
                cursor = parent
            search_dirs.reverse()

        found: list[Path] = []
        candidate_names = self.candidate_filenames()
        for directory in search_dirs:
            for name in candidate_names:
                candidate = directory / name
                if candidate.is_file():
                    found.append(candidate)
                    break
        return found

    def candidate_filenames(self) -> tuple[str, ...]:
        names = [LOCAL_AGENTS_MD_FILENAME, DEFAULT_AGENTS_MD_FILENAME]
        for candidate in self.config.project_doc_fallback_filenames:
            if candidate and candidate not in names:
                names.append(candidate)
        return tuple(names)


def _warn_invalid_utf8(
    path: Path,
    data: bytes,
    source: str,
    startup_warnings: list[str],
) -> None:
    try:
        data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        startup_warnings.append(
            f"{source} AGENTS.md instructions from `{path}` contain invalid UTF-8: {exc}. "
            "Invalid byte sequences were replaced."
        )


def _decode_lossy(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _normalize_existing_path(path: Path) -> Path:
    try:
        return path.resolve(strict=True)
    except OSError:
        return path.absolute()


def _ancestors(path: Path) -> tuple[Path, ...]:
    return (path, *path.parents)


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return left == right


__all__ = [
    "AGENTS_MD_SEPARATOR",
    "DEFAULT_AGENTS_MD_FILENAME",
    "DEFAULT_PROJECT_DOC_MAX_BYTES",
    "DEFAULT_PROJECT_ROOT_MARKERS",
    "HIERARCHICAL_AGENTS_MESSAGE",
    "LOCAL_AGENTS_MD_FILENAME",
    "AgentsMdConfig",
    "AgentsMdManager",
    "LoadedAgentsMd",
]
