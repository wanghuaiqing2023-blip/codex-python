"""Codex Desktop app command helpers.

Ported from ``codex/codex-rs/cli/src/app_cmd.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CODEX_DMG_URL_ARM64 = "https://persistent.oaistatic.com/codex-app-prod/Codex.dmg"
CODEX_DMG_URL_X64 = "https://persistent.oaistatic.com/codex-app-prod/Codex-latest-x64.dmg"


@dataclass(frozen=True)
class AppCommand:
    path: Path = Path(".")
    download_url_override: str | None = None


@dataclass(frozen=True)
class MacAppInstallPlan:
    dmg_url: str
    temp_dir_prefix: str
    dmg_filename: str
    mount_message: str


def workspace_for_app_command(path: str | Path = ".") -> Path:
    """Return the workspace path passed to the desktop app launcher."""

    workspace = Path(path)
    try:
        return workspace.resolve(strict=True)
    except OSError:
        return workspace


def display_windows_workspace_path(workspace: str | Path) -> str:
    """Return the workspace path text shown by the Windows desktop app launcher."""

    path = str(workspace)
    unc_prefix = "\\\\?\\UNC\\"
    extended_prefix = "\\\\?\\"
    if path.startswith(unc_prefix):
        return r"\\" + path[len(unc_prefix) :]
    if path.startswith(extended_prefix):
        return path[len(extended_prefix) :]
    return path


def parse_hdiutil_attach_mount_point(output: str) -> str | None:
    """Return the mounted volume path from ``hdiutil attach`` output."""

    for line in output.splitlines():
        if "/Volumes/" not in line:
            continue
        if "\t" in line:
            return line.rsplit("\t", 1)[1].strip()
        for field in line.split():
            if field.startswith("/Volumes/"):
                return field
    return None


def candidate_codex_app_paths(home: str | Path | None = None) -> tuple[Path, ...]:
    paths = [Path("/Applications/Codex.app")]
    if home is not None:
        paths.append(Path(home) / "Applications" / "Codex.app")
    return tuple(paths)


def candidate_applications_dirs(home: str | Path) -> tuple[Path, ...]:
    return (Path("/Applications"), Path(home) / "Applications")


def default_mac_dmg_url(machine: str, *, translated: bool = False, arm64_optional: bool = False) -> str:
    if machine in {"aarch64", "arm64"} or translated or arm64_optional:
        return CODEX_DMG_URL_ARM64
    return CODEX_DMG_URL_X64


def mac_open_app_command(app_path: str | Path, workspace: str | Path) -> tuple[str, ...]:
    return ("open", "-a", str(app_path), str(workspace))


def mac_download_dmg_command(url: str, dest: str | Path) -> tuple[str, ...]:
    return ("curl", "-fL", "--retry", "3", "--retry-delay", "1", "-o", str(dest), url)


def mac_mount_dmg_command(dmg_path: str | Path) -> tuple[str, ...]:
    return ("hdiutil", "attach", "-nobrowse", "-readonly", str(dmg_path))


def mac_detach_dmg_command(mount_point: str | Path) -> tuple[str, ...]:
    return ("hdiutil", "detach", str(mount_point))


def mac_copy_app_bundle_command(src_app: str | Path, dest_app: str | Path) -> tuple[str, ...]:
    return ("ditto", str(src_app), str(dest_app))


def find_codex_app_in_mount(mount_point: str | Path) -> Path:
    mount = Path(mount_point)
    direct = mount / "Codex.app"
    if direct.is_dir():
        return direct

    try:
        entries = list(mount.iterdir())
    except OSError as exc:
        raise ValueError(f"failed to read {mount}") from exc

    for path in entries:
        if path.suffix == ".app" and path.is_dir():
            return path

    raise ValueError(f"no .app bundle found at {mount}")


def mac_app_install_plan(dmg_url: str) -> MacAppInstallPlan:
    return MacAppInstallPlan(
        dmg_url=dmg_url,
        temp_dir_prefix="codex-app-installer-",
        dmg_filename="Codex.dmg",
        mount_message="Mounting Codex Desktop installer...",
    )
