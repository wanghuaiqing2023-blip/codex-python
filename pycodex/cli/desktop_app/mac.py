"""Rust-aligned codex-cli desktop_app::mac implementation."""

from __future__ import annotations

import os
import platform
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

CODEX_DMG_URL_ARM64 = "https://persistent.oaistatic.com/codex-app-prod/Codex.dmg"

CODEX_DMG_URL_X64 = "https://persistent.oaistatic.com/codex-app-prod/Codex-latest-x64.dmg"

@dataclass(frozen=True)
class MacAppInstallPlan:
    dmg_url: str
    temp_dir_prefix: str
    dmg_filename: str
    mount_message: str

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

def run_mac_app_open_or_install(
    *,
    workspace: Path,
    download_url: str | None,
    stderr: TextIO,
) -> int:
    for app_path in candidate_codex_app_paths(os.environ.get("HOME")):
        if app_path.is_dir():
            return open_codex_app(app_path, workspace, stderr=stderr, announce_app=True)

    print("Codex Desktop not found; downloading installer...", file=stderr)
    installer_url = download_url if download_url is not None else default_macos_dmg_url()
    try:
        installed_app = download_and_install_codex_to_user_applications(
            installer_url,
            stderr=stderr,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"failed to download/install Codex Desktop: {exc}", file=stderr)
        return 2

    print(f"Launching Codex Desktop from {installed_app}...", file=stderr)
    return open_codex_app(installed_app, workspace, stderr=stderr, announce_app=False)

def default_macos_dmg_url() -> str:
    return default_mac_dmg_url(
        platform.machine(),
        translated=macos_sysctl_flag("sysctl.proc_translated") or False,
        arm64_optional=macos_sysctl_flag("hw.optional.arm64") or False,
    )

def macos_sysctl_flag(name: str) -> bool | None:
    try:
        result = subprocess.run(
            ("sysctl", "-in", name),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    if value == "0":
        return False
    if value:
        return True
    return None

def open_codex_app(app_path: Path, workspace: Path, *, stderr: TextIO, announce_app: bool) -> int:
    if announce_app:
        print(f"Opening Codex Desktop at {app_path}...", file=stderr)
    print(f"Opening workspace {workspace}...", file=stderr)
    try:
        result = subprocess.run(
            mac_open_app_command(app_path, workspace),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        print(f"Failed to launch Codex Desktop: {exc}", file=stderr)
        return 2

    if result.returncode == 0:
        return 0

    print(
        f"open command returned {result.returncode} while launching Codex Desktop.",
        file=stderr,
    )
    if result.stderr:
        print(result.stderr.strip(), file=stderr)
    return 2

def download_and_install_codex_to_user_applications(
    dmg_url: str,
    *,
    stderr: TextIO,
) -> Path:
    plan = mac_app_install_plan(dmg_url)
    with tempfile.TemporaryDirectory(prefix=plan.temp_dir_prefix) as tmp_root:
        dmg_path = Path(tmp_root) / plan.dmg_filename

        print("Downloading installer...", file=stderr)
        run_status_command(
            mac_download_dmg_command(plan.dmg_url, dmg_path),
            invoke_error="failed to invoke `curl`",
            status_error="curl download failed",
        )

        print(plan.mount_message, file=stderr)
        mount_point = mount_dmg(dmg_path)
        print(f"Installer mounted at {mount_point}.", file=stderr)

        try:
            app_in_volume = find_codex_app_in_mount(mount_point)
            return install_codex_app_bundle(app_in_volume, stderr=stderr)
        finally:
            try:
                run_status_command(
                    mac_detach_dmg_command(mount_point),
                    invoke_error="failed to invoke `hdiutil detach`",
                    status_error="hdiutil detach failed",
                )
            except (OSError, RuntimeError) as exc:
                print(f"warning: failed to detach dmg at {mount_point}: {exc}", file=stderr)

def mount_dmg(dmg_path: Path) -> Path:
    try:
        result = subprocess.run(
            mac_mount_dmg_command(dmg_path),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise OSError("failed to invoke `hdiutil attach`") from exc

    if result.returncode != 0:
        raise RuntimeError(
            "`hdiutil attach` failed with "
            f"exit status {result.returncode}: {result.stderr}"
        )

    mount_point = parse_hdiutil_attach_mount_point(result.stdout)
    if mount_point is None:
        raise RuntimeError(f"failed to parse mount point from hdiutil output:\n{result.stdout}")
    return Path(mount_point)

def install_codex_app_bundle(app_in_volume: Path, *, stderr: TextIO) -> Path:
    home = os.environ.get("HOME")
    if not home:
        raise RuntimeError("HOME is not set")

    for applications_dir in candidate_applications_dirs(home):
        print(f"Installing Codex Desktop into {applications_dir}...", file=stderr)
        try:
            applications_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OSError(f"failed to create applications dir {applications_dir}") from exc

        dest_app = applications_dir / "Codex.app"
        if dest_app.is_dir():
            return dest_app

        try:
            run_status_command(
                mac_copy_app_bundle_command(app_in_volume, dest_app),
                invoke_error="failed to invoke `ditto`",
                status_error="ditto copy failed",
            )
        except (OSError, RuntimeError) as exc:
            print(f"warning: failed to install Codex.app to {applications_dir}: {exc}", file=stderr)
            continue
        return dest_app

    raise RuntimeError("failed to install Codex.app to any applications directory")

def run_status_command(
    command: tuple[str, ...],
    *,
    invoke_error: str,
    status_error: str,
) -> None:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise OSError(invoke_error) from exc

    if result.returncode != 0:
        stderr_text = f": {result.stderr.strip()}" if result.stderr.strip() else ""
        raise RuntimeError(f"{status_error} with exit status {result.returncode}{stderr_text}")
