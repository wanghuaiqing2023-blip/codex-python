"""Rust-aligned codex-cli desktop_app::windows implementation."""

from __future__ import annotations

import subprocess
import webbrowser
from pathlib import Path
from typing import TextIO

def display_workspace_path(workspace: str | Path) -> str:
    """Return the workspace path text shown by the Windows desktop app launcher."""

    path = str(workspace)
    unc_prefix = "\\\\?\\UNC\\"
    extended_prefix = "\\\\?\\"
    if path.startswith(unc_prefix):
        return r"\\" + path[len(unc_prefix) :]
    if path.startswith(extended_prefix):
        return path[len(extended_prefix) :]
    return path

CODEX_WINDOWS_INSTALLER_URL = "https://get.microsoft.com/installer/download/9PLM9XGG6VKS?cid=website_cta_psi"

CODEX_MICROSOFT_STORE_WEB_URL = "https://apps.microsoft.com/detail/9PLM9XGG6VKS"

def run_windows_app_open_or_install(
    *,
    workspace: Path,
    download_url: str | None,
    stderr: TextIO,
) -> int:
    workspace_text = display_workspace_path(workspace)
    print("Checking for installed Codex Desktop on Windows...", file=stderr)
    powershell_cmd = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        "Get-StartApps -Name 'Codex' | Select-Object -First 1 -ExpandProperty AppID",
    ]
    app_id: str = ""
    try:
        result = subprocess.run(
            powershell_cmd,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        print(f"Failed to detect installed Codex app: {exc}", file=stderr)
        result = None

    if result is not None and result.returncode == 0:
        app_id = result.stdout.strip()

    if app_id:
        print("Opening Codex Desktop...", file=stderr)
        try:
            subprocess.run(
                ("explorer.exe", f"shell:AppsFolder\\{app_id}"),
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            print(f"Failed to open Codex Desktop: {exc}", file=stderr)
            return 2
        print(f"In Codex Desktop, open workspace {workspace_text}.", file=stderr)
        return 0

    print("Codex Desktop not found; opening Windows installer...", file=stderr)
    installer = download_url if download_url is not None else CODEX_WINDOWS_INSTALLER_URL
    print(f"Opening installer: {installer}", file=stderr)
    if not open_url(installer, stderr=stderr) and download_url is None:
        print("Opening Microsoft Store URL fallback...", file=stderr)
        open_url(CODEX_MICROSOFT_STORE_WEB_URL, stderr=stderr)
    print(f"After installing Codex Desktop, open workspace {workspace_text}.", file=stderr)
    return 0

def open_url(url: str, *, stderr: TextIO) -> bool:
    try:
        if webbrowser.open(url):
            return True
    except Exception as exc:
        print(f"Failed to open URL: {exc}", file=stderr)
        return False
    print("Could not open URL in a browser.", file=stderr)
    return False
