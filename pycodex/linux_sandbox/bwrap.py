"""Bubblewrap argument construction helpers.

Port slice for ``codex/codex-rs/linux-sandbox/src/bwrap.rs``.

This module mirrors the Rust data model and the command wrapping fast paths
used before the native Linux mount overlay work. The full filesystem overlay
planner remains a follow-up boundary in this crate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence

from pycodex.protocol import FileSystemSandboxPolicy, WritableRoot, is_protected_metadata_name


class BwrapNetworkMode(str, Enum):
    FULL_ACCESS = "full_access"
    ISOLATED = "isolated"
    PROXY_ONLY = "proxy_only"

    def should_unshare_network(self) -> bool:
        return self is not BwrapNetworkMode.FULL_ACCESS


@dataclass(frozen=True)
class BwrapOptions:
    mount_proc: bool = True
    network_mode: BwrapNetworkMode = BwrapNetworkMode.FULL_ACCESS
    glob_scan_max_depth: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mount_proc, bool):
            raise TypeError("mount_proc must be a bool")
        if not isinstance(self.network_mode, BwrapNetworkMode):
            raise TypeError("network_mode must be BwrapNetworkMode")
        if self.glob_scan_max_depth is not None:
            if isinstance(self.glob_scan_max_depth, bool) or not isinstance(self.glob_scan_max_depth, int):
                raise TypeError("glob_scan_max_depth must be an integer")
            if self.glob_scan_max_depth < 0:
                raise ValueError("glob_scan_max_depth must be non-negative")


class SyntheticMountTargetKind(str, Enum):
    EMPTY_FILE = "empty_file"
    EMPTY_DIRECTORY = "empty_directory"


@dataclass(frozen=True)
class FileIdentity:
    dev: int
    ino: int

    @classmethod
    def from_path(cls, path: Path | str) -> "FileIdentity":
        stat = Path(path).stat()
        return cls(stat.st_dev, stat.st_ino)


@dataclass(frozen=True)
class SyntheticMountTarget:
    _path: Path
    _kind: SyntheticMountTargetKind
    pre_existing_path: FileIdentity | None = None

    @classmethod
    def missing(cls, path: Path | str) -> "SyntheticMountTarget":
        return cls(Path(path), SyntheticMountTargetKind.EMPTY_FILE)

    @classmethod
    def missing_empty_directory(cls, path: Path | str) -> "SyntheticMountTarget":
        return cls(Path(path), SyntheticMountTargetKind.EMPTY_DIRECTORY)

    @classmethod
    def existing_empty_file(cls, path: Path | str) -> "SyntheticMountTarget":
        return cls(Path(path), SyntheticMountTargetKind.EMPTY_FILE, FileIdentity.from_path(path))

    @classmethod
    def existing_empty_directory(cls, path: Path | str) -> "SyntheticMountTarget":
        return cls(Path(path), SyntheticMountTargetKind.EMPTY_DIRECTORY, FileIdentity.from_path(path))

    def preserves_pre_existing_path(self) -> bool:
        return self.pre_existing_path is not None

    def path(self) -> Path:
        return self._path

    def kind(self) -> SyntheticMountTargetKind:
        return self._kind

    def should_remove_after_bwrap(self, path: Path | str | None = None) -> bool:
        target = self._path if path is None else Path(path)
        if self._kind is SyntheticMountTargetKind.EMPTY_FILE:
            if not target.is_file() or target.stat().st_size != 0:
                return False
        else:
            if not target.is_dir():
                return False
        if self.pre_existing_path is None:
            return True
        return FileIdentity.from_path(target) != self.pre_existing_path


@dataclass(frozen=True)
class ProtectedCreateTarget:
    _path: Path

    @classmethod
    def missing(cls, path: Path | str) -> "ProtectedCreateTarget":
        return cls(Path(path))

    def path(self) -> Path:
        return self._path


@dataclass(frozen=True)
class BwrapArgs:
    args: tuple[str, ...]
    preserved_files: tuple[object, ...] = ()
    synthetic_mount_targets: tuple[SyntheticMountTarget, ...] = ()
    protected_create_targets: tuple[ProtectedCreateTarget, ...] = ()


def create_bwrap_command_args(
    command: Sequence[str],
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    sandbox_policy_cwd: Path | str,
    command_cwd: Path | str,
    options: BwrapOptions | None = None,
) -> BwrapArgs:
    """Return bubblewrap argv flags for the selected filesystem/network policy."""

    command_tuple = _string_sequence(command, "command")
    if not isinstance(file_system_sandbox_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_sandbox_policy must be FileSystemSandboxPolicy")
    options = options or BwrapOptions()
    if not isinstance(options, BwrapOptions):
        raise TypeError("options must be BwrapOptions")
    sandbox_policy_cwd = Path(sandbox_policy_cwd)
    command_cwd = Path(command_cwd)
    unreadable_globs = file_system_sandbox_policy.get_unreadable_globs_with_cwd(sandbox_policy_cwd)
    if file_system_sandbox_policy.has_full_disk_write_access() and not unreadable_globs:
        if options.network_mode is BwrapNetworkMode.FULL_ACCESS:
            return BwrapArgs(command_tuple)
        return _create_bwrap_flags_full_filesystem(command_tuple, options)
    return _create_bwrap_flags(
        command_tuple,
        file_system_sandbox_policy,
        sandbox_policy_cwd,
        command_cwd,
        options,
    )


def create_bwrap_flags_full_filesystem(command: Sequence[str], options: BwrapOptions | None = None) -> BwrapArgs:
    return _create_bwrap_flags_full_filesystem(_string_sequence(command, "command"), options or BwrapOptions())


def create_filesystem_args(
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    cwd: Path | str,
    glob_scan_max_depth: int | None = None,
) -> BwrapArgs:
    if not isinstance(file_system_sandbox_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_sandbox_policy must be FileSystemSandboxPolicy")
    return _create_filesystem_args(file_system_sandbox_policy, Path(cwd), glob_scan_max_depth)


def split_pattern_for_ripgrep(pattern: str | Path, cwd: str | Path) -> tuple[Path, str] | None:
    absolute_pattern = _resolve_against_base(Path(pattern), Path(cwd)).as_posix()
    first_glob_index = next(
        (index for index, char in enumerate(absolute_pattern) if char in "*?[]"),
        None,
    )
    if first_glob_index is None:
        return None
    static_prefix = absolute_pattern[:first_glob_index]
    if static_prefix in {"", "/"}:
        return None
    search_root_end = len(static_prefix) - 1 if static_prefix.endswith("/") else static_prefix.rfind("/")
    search_root = Path("/") if search_root_end == 0 else Path(absolute_pattern[:search_root_end])
    glob = escape_unclosed_glob_classes(absolute_pattern[search_root_end + 1 :])
    if not glob:
        return None
    return search_root, glob


def escape_unclosed_glob_classes(glob: str) -> str:
    escaped: list[str] = []
    index = 0
    while index < len(glob):
        char = glob[index]
        if char != "[":
            escaped.append(char)
            index += 1
            continue
        close = glob.find("]", index + 1)
        if close == -1:
            escaped.append(r"\[")
            escaped.append(glob[index + 1 :])
            break
        escaped.append(glob[index : close + 1])
        index = close + 1
    return "".join(escaped)


def normalize_command_cwd_for_bwrap(command_cwd: Path | str) -> Path:
    path = Path(command_cwd)
    try:
        return path.resolve(strict=True)
    except OSError:
        return path


def path_to_string(path: Path | str) -> str:
    return Path(path).as_posix()


def _create_bwrap_flags_full_filesystem(command: tuple[str, ...], options: BwrapOptions) -> BwrapArgs:
    args = [
        "--new-session",
        "--die-with-parent",
        "--bind",
        "/",
        "/",
        "--unshare-user",
        "--unshare-pid",
    ]
    if options.network_mode.should_unshare_network():
        args.append("--unshare-net")
    if options.mount_proc:
        args.extend(["--proc", "/proc"])
    args.append("--")
    args.extend(command)
    return BwrapArgs(tuple(args))


def _create_bwrap_flags(
    command: tuple[str, ...],
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    sandbox_policy_cwd: Path,
    command_cwd: Path,
    options: BwrapOptions,
) -> BwrapArgs:
    filesystem = _create_filesystem_args(
        file_system_sandbox_policy,
        sandbox_policy_cwd,
        options.glob_scan_max_depth
        if options.glob_scan_max_depth is not None
        else file_system_sandbox_policy.glob_scan_max_depth,
    )
    wrapped = ["--new-session", "--die-with-parent", *filesystem.args, "--unshare-user", "--unshare-pid"]
    if options.network_mode.should_unshare_network():
        wrapped.append("--unshare-net")
    if options.mount_proc:
        wrapped.extend(["--proc", "/proc"])
    normalized_command_cwd = normalize_command_cwd_for_bwrap(command_cwd)
    if normalized_command_cwd != command_cwd:
        wrapped.extend(["--chdir", path_to_string(normalized_command_cwd)])
    wrapped.append("--")
    wrapped.extend(command)
    return BwrapArgs(
        tuple(wrapped),
        preserved_files=filesystem.preserved_files,
        synthetic_mount_targets=filesystem.synthetic_mount_targets,
        protected_create_targets=filesystem.protected_create_targets,
    )


def _create_filesystem_args(
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    cwd: Path,
    glob_scan_max_depth: int | None,
) -> BwrapArgs:
    synthetic_targets: list[SyntheticMountTarget] = []
    protected_targets: list[ProtectedCreateTarget] = []
    preserved_files: list[object] = []
    has_linux_root_read = _has_linux_root_access(file_system_sandbox_policy, "read")
    if file_system_sandbox_policy.has_full_disk_read_access() or has_linux_root_read:
        args = ["--ro-bind", "/", "/", "--dev", "/dev"]
    else:
        args = ["--tmpfs", "/", "--dev", "/dev"]
        readable_roots = list(file_system_sandbox_policy.get_readable_roots_with_cwd(cwd))
        if any(_is_linux_root_path(root) for root in readable_roots):
            args = ["--ro-bind", "/", "/", "--dev", "/dev"]
        else:
            if file_system_sandbox_policy.include_platform_defaults():
                for default_root in LINUX_PLATFORM_DEFAULT_READ_ROOTS:
                    if default_root.exists() and default_root not in readable_roots:
                        readable_roots.append(default_root)
            for root in sorted(readable_roots, key=_path_depth):
                if root.exists():
                    root_string = path_to_string(root)
                    args.extend(["--ro-bind", root_string, root_string])

    writable_roots = [
        _PlannedWritableRoot.from_writable_root(writable_root)
        for writable_root in file_system_sandbox_policy.get_writable_roots_with_cwd(cwd)
        if writable_root.root.exists()
    ]
    if (
        not writable_roots
        and (
            file_system_sandbox_policy.has_full_disk_write_access()
            or _has_linux_root_access(file_system_sandbox_policy, "write")
        )
        and file_system_sandbox_policy.get_unreadable_globs_with_cwd(cwd)
    ):
        writable_roots = [
            _PlannedWritableRoot.from_writable_root(
                WritableRoot(Path("/"), read_only_subpaths=(), protected_metadata_names=())
            )
        ]

    allowed_write_paths = tuple(writable_root.mount_root for writable_root in writable_roots)
    unreadable_roots = tuple(
        sorted(
            _remap_paths_for_planned_roots(file_system_sandbox_policy.get_unreadable_roots_with_cwd(cwd), writable_roots),
            key=_path_depth,
        )
    )
    prebound_unreadable_roots: set[Path] = set()

    for unreadable_root in unreadable_roots:
        if any(_path_starts_with(writable_root.mount_root, unreadable_root) for writable_root in writable_roots):
            _append_unreadable_path_args(args, preserved_files, synthetic_targets, unreadable_root, allowed_write_paths)
            prebound_unreadable_roots.add(unreadable_root)

    for writable_root in sorted(writable_roots, key=lambda root: _path_depth(root.mount_root)):
        root = writable_root.mount_root
        root_string = path_to_string(root)
        args.extend(["--bind", root_string, root_string])

        read_only_subpaths = list(_dedup_ordered_paths(_remap_paths_for_planned_roots(writable_root.read_only_subpaths, (writable_root,))))
        metadata_paths: set[Path] = set()
        for metadata_name in writable_root.protected_metadata_names:
            metadata_path = root / metadata_name
            metadata_paths.add(metadata_path)
            if metadata_path.exists():
                if metadata_path not in read_only_subpaths:
                    read_only_subpaths.append(metadata_path)
            elif metadata_name == ".git" and _has_parent_git_metadata(metadata_path):
                protected_targets.append(ProtectedCreateTarget.missing(metadata_path))
            else:
                _append_empty_directory(args, synthetic_targets, metadata_path)

        for subpath in read_only_subpaths:
            if subpath in metadata_paths and not subpath.exists():
                continue
            _append_read_only_path_args(
                args,
                preserved_files,
                synthetic_targets,
                protected_targets,
                subpath,
                allowed_write_paths,
            )

    for unreadable_root in unreadable_roots:
        if unreadable_root not in prebound_unreadable_roots:
            _append_unreadable_path_args(args, preserved_files, synthetic_targets, unreadable_root, allowed_write_paths)

    for pattern in file_system_sandbox_policy.get_unreadable_globs_with_cwd(cwd):
        for match in _expand_unreadable_glob(pattern, cwd, glob_scan_max_depth):
            _append_unreadable_path_args(args, preserved_files, synthetic_targets, match, allowed_write_paths)

    if _has_linux_path_access(file_system_sandbox_policy, "/dev", "write"):
        args.extend(["--bind", "/dev", "/dev"])

    return BwrapArgs(
        tuple(args),
        preserved_files=tuple(preserved_files),
        synthetic_mount_targets=tuple(synthetic_targets),
        protected_create_targets=tuple(protected_targets),
    )


LINUX_PLATFORM_DEFAULT_READ_ROOTS = (
    Path("/bin"),
    Path("/sbin"),
    Path("/usr"),
    Path("/etc"),
    Path("/lib"),
    Path("/lib64"),
    Path("/nix/store"),
    Path("/run/current-system/sw"),
)


def _append_read_only_path_args(
    args: list[str],
    preserved_files: list[object],
    synthetic_targets: list[SyntheticMountTarget],
    protected_targets: list[ProtectedCreateTarget],
    path: Path,
    allowed_write_paths: tuple[Path, ...],
) -> None:
    symlink = _first_writable_symlink_component_in_path(path, allowed_write_paths)
    if symlink is not None:
        raise RuntimeError(f"cannot enforce sandbox read-only path {path} because it crosses writable symlink {symlink}")
    if path.exists():
        if _is_transient_empty_metadata_path(path):
            _append_preserved_empty_path(args, preserved_files, synthetic_targets, path)
            return
        path_string = path_to_string(path)
        args.extend(["--ro-bind", path_string, path_string])
        return
    if path.name == ".git" and _has_parent_git_metadata(path):
        protected_targets.append(ProtectedCreateTarget.missing(path))
        return
    _append_missing_empty_file(args, preserved_files, synthetic_targets, path)


def _append_unreadable_path_args(
    args: list[str],
    preserved_files: list[object],
    synthetic_targets: list[SyntheticMountTarget],
    path: Path,
    allowed_write_paths: tuple[Path, ...],
) -> None:
    symlink = _first_writable_symlink_component_in_path(path, allowed_write_paths)
    if symlink is not None:
        raise RuntimeError(f"cannot enforce sandbox deny-read path {path} because it crosses writable symlink {symlink}")
    if path.exists():
        if path.is_dir():
            writable_descendants = tuple(
                sorted(
                    (
                        allowed_path
                        for allowed_path in allowed_write_paths
                        if allowed_path != path and _path_starts_with(allowed_path, path)
                    ),
                    key=_path_depth,
                )
            )
            perms = "111" if writable_descendants else "000"
            path_string = path_to_string(path)
            args.extend(["--perms", perms, "--tmpfs", path_string])
            for writable_descendant in writable_descendants:
                _append_mount_target_parent_dir_args(args, writable_descendant, path)
            args.extend(["--remount-ro", path_string])
        else:
            path_string = path_to_string(path)
            preserved_files.append(path)
            args.extend(["--perms", "000", "--ro-bind-data", str(len(preserved_files) - 1), path_string])
        return
    _append_missing_empty_file(args, preserved_files, synthetic_targets, path)


@dataclass(frozen=True)
class _PlannedWritableRoot:
    logical_root: Path
    mount_root: Path
    read_only_subpaths: tuple[Path, ...]
    protected_metadata_names: tuple[str, ...]

    @classmethod
    def from_writable_root(cls, writable_root: object) -> "_PlannedWritableRoot":
        logical_root = writable_root.root
        mount_root = _canonical_target_if_symlinked_path(logical_root) or logical_root
        return cls(
            logical_root=logical_root,
            mount_root=mount_root,
            read_only_subpaths=tuple(writable_root.read_only_subpaths),
            protected_metadata_names=tuple(writable_root.protected_metadata_names),
        )


def _append_missing_empty_file(
    args: list[str],
    preserved_files: list[object],
    synthetic_targets: list[SyntheticMountTarget],
    path: Path,
) -> None:
    path_string = path_to_string(path)
    preserved_files.append(path)
    synthetic_targets.append(SyntheticMountTarget.missing(path))
    args.extend(["--ro-bind-data", str(len(preserved_files) - 1), path_string])


def _append_preserved_empty_path(
    args: list[str],
    preserved_files: list[object],
    synthetic_targets: list[SyntheticMountTarget],
    path: Path,
) -> None:
    if path.is_dir():
        synthetic_targets.append(SyntheticMountTarget.existing_empty_directory(path))
        _append_empty_directory(args, synthetic_targets, path)
        return
    path_string = path_to_string(path)
    preserved_files.append(path)
    synthetic_targets.append(SyntheticMountTarget.existing_empty_file(path))
    args.extend(["--ro-bind-data", str(len(preserved_files) - 1), path_string])


def _append_empty_directory(
    args: list[str],
    synthetic_targets: list[SyntheticMountTarget],
    path: Path,
    *,
    protected: bool = False,
) -> None:
    path_string = path_to_string(path)
    if not protected:
        synthetic_targets.append(SyntheticMountTarget.missing_empty_directory(path))
    args.extend(["--perms", "555", "--tmpfs", path_string, "--remount-ro", path_string])


def _is_transient_empty_metadata_path(path: Path) -> bool:
    if not is_protected_metadata_name(path.name):
        return False
    if path.is_file():
        return path.stat().st_size == 0
    if path.is_dir():
        try:
            return not any(path.iterdir())
        except OSError:
            return False
    return False


def _has_parent_git_metadata(path: Path) -> bool:
    home = Path.home()
    for parent in path.parents:
        if parent == home:
            break
        git = parent / ".git"
        if git.exists():
            return True
    return False


def _expand_unreadable_glob(pattern: str, cwd: Path, max_depth: int | None) -> tuple[Path, ...]:
    import glob

    split = split_pattern_for_ripgrep(pattern, cwd)
    if split is None:
        return ()
    search_root, _ = split
    try:
        raw_matches = glob.glob(str(_resolve_against_base(Path(pattern), cwd)), recursive=True, include_hidden=True)
    except TypeError:
        raw_matches = glob.glob(str(_resolve_against_base(Path(pattern), cwd)), recursive=True)
    matches = sorted(Path(match) for match in raw_matches)
    expanded: set[Path] = set()
    for match in matches:
        if not match.exists() or search_root not in (match, *match.parents):
            continue
        if max_depth is not None and _relative_depth(match, search_root) > max_depth:
            continue
        expanded.add(match)
        try:
            target = match.resolve(strict=True)
        except OSError:
            continue
        if target != match:
            expanded.add(target)
    return tuple(sorted(expanded))


def _path_depth(path: Path) -> int:
    return len(path.parts)


def _relative_depth(path: Path, root: Path) -> int:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return _path_depth(path)
    return len(relative.parts)


def _append_mount_target_parent_dir_args(args: list[str], mount_target: Path, anchor: Path) -> None:
    mount_target_dir = mount_target if mount_target.is_dir() else mount_target.parent
    if mount_target_dir is None:
        return
    dirs = []
    current = mount_target_dir
    while current != anchor and _path_starts_with(current, anchor):
        dirs.append(current)
        current = current.parent
    for directory in reversed(dirs):
        args.extend(["--dir", path_to_string(directory)])


def _canonical_target_if_symlinked_path(path: Path) -> Path | None:
    current = Path()
    saw_symlink = False
    for part in path.parts:
        current = Path(part) if current == Path() else current / part
        if current.is_symlink():
            saw_symlink = True
            break
        if not current.exists():
            return None
    if not saw_symlink:
        return None
    try:
        target = path.resolve(strict=True)
    except OSError:
        return None
    return None if target == path else target


def _remap_paths_for_planned_roots(
    paths: Sequence[Path],
    planned_roots: Sequence[_PlannedWritableRoot],
) -> tuple[Path, ...]:
    remapped: list[Path] = []
    for path in paths:
        remapped_path = path
        for root in planned_roots:
            try:
                relative = path.relative_to(root.logical_root)
            except ValueError:
                continue
            remapped_path = root.mount_root / relative
            break
        remapped.append(remapped_path)
    return tuple(remapped)


def _first_writable_symlink_component_in_path(path: Path, allowed_write_paths: tuple[Path, ...]) -> Path | None:
    current = Path()
    for part in path.parts:
        current = Path(part) if current == Path() else current / part
        if not current.exists():
            return None
        if current.is_symlink() and any(_path_starts_with(current, root) for root in allowed_write_paths):
            return current
    return None


def _path_starts_with(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _dedup_ordered_paths(paths: Sequence[Path]) -> tuple[Path, ...]:
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = path.as_posix()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return tuple(deduped)


def _is_linux_root_path(path: Path) -> bool:
    return path.as_posix() == "/"


def _has_linux_root_access(file_system_sandbox_policy: FileSystemSandboxPolicy, access: str) -> bool:
    return _has_linux_path_access(file_system_sandbox_policy, "/", access)


def _has_linux_path_access(file_system_sandbox_policy: FileSystemSandboxPolicy, linux_path: str, access: str) -> bool:
    for entry in getattr(file_system_sandbox_policy, "entries", ()):
        entry_path = getattr(entry, "path", None)
        if getattr(entry_path, "type", None) != "path":
            continue
        path = getattr(entry_path, "path", None)
        if not isinstance(path, Path) or path.as_posix() != linux_path:
            continue
        entry_access = getattr(entry, "access", None)
        if access == "write" and getattr(entry_access, "can_write", lambda: False)():
            return True
        if access == "read" and getattr(entry_access, "can_read", lambda: False)():
            return True
    return False


def _resolve_against_base(path: Path, cwd: Path) -> Path:
    if path.is_absolute():
        return path
    return cwd / path


def _string_sequence(value: object, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of strings")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{label} must contain only strings")
    return tuple(value)


__all__ = [
    "BwrapArgs",
    "BwrapNetworkMode",
    "BwrapOptions",
    "FileIdentity",
    "ProtectedCreateTarget",
    "SyntheticMountTarget",
    "SyntheticMountTargetKind",
    "create_bwrap_command_args",
    "create_bwrap_flags_full_filesystem",
    "create_filesystem_args",
    "escape_unclosed_glob_classes",
    "normalize_command_cwd_for_bwrap",
    "path_to_string",
    "split_pattern_for_ripgrep",
]
