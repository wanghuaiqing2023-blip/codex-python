from __future__ import annotations

"""Shell snapshot helpers ported from ``core/src/shell_snapshot.rs``."""
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .shell import Shell, ShellType, get_shell


SNAPSHOT_TIMEOUT_SECONDS = 10
SNAPSHOT_RETENTION_SECONDS = 60 * 60 * 24 * 3
SNAPSHOT_DIR = "shell_snapshots"
EXCLUDED_EXPORT_VARS = ("PWD", "OLDPWD")


def _ensure_path(value: object, field: str) -> Path:
    if not isinstance(value, Path):
        raise TypeError(f"{field} must be a Path")
    return value


def _ensure_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _ensure_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field} must be a bool")
    return value


def _ensure_number(value: object, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{field} must be numeric")
    return float(value)


def _ensure_shell_type(value: object) -> ShellType:
    if not isinstance(value, ShellType):
        raise TypeError("shell_type must be a ShellType")
    return value


class ShellSnapshotError(Exception):
    """Raised when snapshot capture or validation fails."""


@dataclass(frozen=True)
class ShellSnapshot:
    path: Path
    cwd: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _ensure_path(self.path, "path"))
        object.__setattr__(self, "cwd", _ensure_path(self.cwd, "cwd"))

    def close(self) -> None:
        remove_snapshot_file(self.path)

    def __enter__(self) -> "ShellSnapshot":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def shell_snapshot_extension(shell_type: ShellType) -> str:
    shell_type = _ensure_shell_type(shell_type)
    return "ps1" if shell_type is ShellType.POWERSHELL else "sh"


def shell_snapshot_paths(
    codex_home: Path,
    session_id: str,
    shell_type: ShellType,
    nonce: int | None = None,
) -> tuple[Path, Path]:
    home = _ensure_path(codex_home, "codex_home")
    session_id = _ensure_str(session_id, "session_id")
    generation = time.time_ns() if nonce is None else nonce
    if not isinstance(generation, int) or isinstance(generation, bool):
        raise TypeError("nonce must be an integer")
    snapshot_dir = home / SNAPSHOT_DIR
    extension = shell_snapshot_extension(shell_type)
    return (
        snapshot_dir / f"{session_id}.{generation}.{extension}",
        snapshot_dir / f"{session_id}.tmp-{generation}",
    )


def strip_snapshot_preamble(snapshot: str) -> str:
    snapshot = _ensure_str(snapshot, "snapshot")
    marker = "# Snapshot file"
    start = snapshot.find(marker)
    if start == -1:
        raise ShellSnapshotError(f"Snapshot output missing marker {marker}")
    return snapshot[start:]


def excluded_exports_regex() -> str:
    return "|".join(EXCLUDED_EXPORT_VARS)


def zsh_snapshot_script() -> str:
    excluded = excluded_exports_regex()
    script = r"""if [[ -n "$ZDOTDIR" ]]; then
  rc="$ZDOTDIR/.zshrc"
else
  rc="$HOME/.zshrc"
fi
[[ -r "$rc" ]] && . "$rc"
print '# Snapshot file'
print '# Unset all aliases to avoid conflicts with functions'
print 'unalias -a 2>/dev/null || true'
print '# Functions'
functions
print ''
setopt_count=$(setopt | wc -l | tr -d ' ')
print "# setopts $setopt_count"
setopt | sed 's/^/setopt /'
print ''
alias_count=$(alias -L | wc -l | tr -d ' ')
print "# aliases $alias_count"
alias -L
print ''
export_lines=$(export -p | awk '
/^(export|declare -x|typeset -x) / {
  line=$0
  name=line
  sub(/^(export|declare -x|typeset -x) /, "", name)
  sub(/=.*/, "", name)
  if (name ~ /^(EXCLUDED_EXPORTS)$/) {
    next
  }
  if (name ~ /^[A-Za-z_][A-Za-z0-9_]*$/) {
    print line
  }
}')
export_count=$(printf '%s\n' "$export_lines" | sed '/^$/d' | wc -l | tr -d ' ')
print "# exports $export_count"
if [[ -n "$export_lines" ]]; then
  print -r -- "$export_lines"
fi
"""
    return script.replace("EXCLUDED_EXPORTS", excluded)


def bash_snapshot_script() -> str:
    excluded = excluded_exports_regex()
    script = r"""if [ -z "$BASH_ENV" ] && [ -r "$HOME/.bashrc" ]; then
  . "$HOME/.bashrc"
fi
echo '# Snapshot file'
echo '# Unset all aliases to avoid conflicts with functions'
unalias -a 2>/dev/null || true
echo '# Functions'
declare -f
echo ''
bash_opts=$(set -o | awk '$2=="on"{print $1}')
bash_opt_count=$(printf '%s\n' "$bash_opts" | sed '/^$/d' | wc -l | tr -d ' ')
echo "# setopts $bash_opt_count"
if [ -n "$bash_opts" ]; then
  printf 'set -o %s\n' $bash_opts
fi
echo ''
alias_count=$(alias -p | wc -l | tr -d ' ')
echo "# aliases $alias_count"
alias -p
echo ''
export_lines=$(
  while IFS= read -r name; do
    if [[ "$name" =~ ^(EXCLUDED_EXPORTS)$ ]]; then
      continue
    fi
    if [[ ! "$name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      continue
    fi
    declare -xp "$name" 2>/dev/null || true
  done < <(compgen -e)
)
export_count=$(printf '%s\n' "$export_lines" | sed '/^$/d' | wc -l | tr -d ' ')
echo "# exports $export_count"
if [ -n "$export_lines" ]; then
  printf '%s\n' "$export_lines"
fi
"""
    return script.replace("EXCLUDED_EXPORTS", excluded)


def sh_snapshot_script() -> str:
    excluded = excluded_exports_regex()
    script = r"""if [ -n "$ENV" ] && [ -r "$ENV" ]; then
  . "$ENV"
fi
echo '# Snapshot file'
echo '# Unset all aliases to avoid conflicts with functions'
unalias -a 2>/dev/null || true
echo '# Functions'
if command -v typeset >/dev/null 2>&1; then
  typeset -f
elif command -v declare >/dev/null 2>&1; then
  declare -f
fi
echo ''
if set -o >/dev/null 2>&1; then
  sh_opts=$(set -o | awk '$2=="on"{print $1}')
  sh_opt_count=$(printf '%s\n' "$sh_opts" | sed '/^$/d' | wc -l | tr -d ' ')
  echo "# setopts $sh_opt_count"
  if [ -n "$sh_opts" ]; then
    printf 'set -o %s\n' $sh_opts
  fi
else
  echo '# setopts 0'
fi
echo ''
if alias >/dev/null 2>&1; then
  alias_count=$(alias | wc -l | tr -d ' ')
  echo "# aliases $alias_count"
  alias
  echo ''
else
  echo '# aliases 0'
fi
if export -p >/dev/null 2>&1; then
  export_lines=$(export -p | awk '
/^(export|declare -x|typeset -x) / {
  line=$0
  name=line
  sub(/^(export|declare -x|typeset -x) /, "", name)
  sub(/=.*/, "", name)
  if (name ~ /^(EXCLUDED_EXPORTS)$/) {
    next
  }
  if (name ~ /^[A-Za-z_][A-Za-z0-9_]*$/) {
    print line
  }
}')
  export_count=$(printf '%s\n' "$export_lines" | sed '/^$/d' | wc -l | tr -d ' ')
  echo "# exports $export_count"
  if [ -n "$export_lines" ]; then
    printf '%s\n' "$export_lines"
  fi
else
  export_count=$(env | sort | awk -F= '$1 ~ /^[A-Za-z_][A-Za-z0-9_]*$/ { count++ } END { print count }')
  echo "# exports $export_count"
  env | sort | while IFS='=' read -r key value; do
    case "$key" in
      ""|[0-9]*|*[!A-Za-z0-9_]*|EXCLUDED_EXPORTS) continue ;;
    esac
    escaped=$(printf "%s" "$value" | sed "s/'/'\"'\"'/g")
    printf "export %s='%s'\n" "$key" "$escaped"
  done
fi
"""
    return script.replace("EXCLUDED_EXPORTS", excluded)


def powershell_snapshot_script() -> str:
    return r"""$ErrorActionPreference = 'Stop'
Write-Output '# Snapshot file'
Write-Output '# Unset all aliases to avoid conflicts with functions'
Write-Output 'Remove-Item Alias:* -ErrorAction SilentlyContinue'
Write-Output '# Functions'
Get-ChildItem Function: | ForEach-Object {
    "function {0} {{`n{1}`n}}" -f $_.Name, $_.Definition
}
Write-Output ''
$aliases = Get-Alias
Write-Output ("# aliases " + $aliases.Count)
$aliases | ForEach-Object {
    "Set-Alias -Name {0} -Value {1}" -f $_.Name, $_.Definition
}
Write-Output ''
$envVars = Get-ChildItem Env:
Write-Output ("# exports " + $envVars.Count)
$envVars | ForEach-Object {
    $escaped = $_.Value -replace "'", "''"
    "`$env:{0}='{1}'" -f $_.Name, $escaped
}
"""


def capture_snapshot(shell: Shell, cwd: Path) -> str:
    if not isinstance(shell, Shell):
        raise TypeError("shell must be a Shell")
    cwd = _ensure_path(cwd, "cwd")
    shell_type = _ensure_shell_type(shell.shell_type)
    if shell_type is ShellType.ZSH:
        script = zsh_snapshot_script()
    elif shell_type is ShellType.BASH:
        script = bash_snapshot_script()
    elif shell_type is ShellType.SH:
        script = sh_snapshot_script()
    elif shell_type is ShellType.POWERSHELL:
        script = powershell_snapshot_script()
    else:
        raise ShellSnapshotError(f"Shell snapshotting is not yet supported for {shell_type.name}")
    return run_script_with_timeout(shell, script, SNAPSHOT_TIMEOUT_SECONDS, True, cwd)


def write_shell_snapshot(shell_type: ShellType, output_path: Path, cwd: Path) -> None:
    shell_type = _ensure_shell_type(shell_type)
    output_path = _ensure_path(output_path, "output_path")
    cwd = _ensure_path(cwd, "cwd")
    if shell_type in {ShellType.POWERSHELL, ShellType.CMD}:
        raise ShellSnapshotError(f"Shell snapshot not supported yet for {shell_type.name}")
    shell = get_shell(shell_type)
    if shell is None:
        raise ShellSnapshotError(f"No available shell for {shell_type.name}")

    raw_snapshot = capture_snapshot(shell, cwd)
    snapshot = strip_snapshot_preamble(raw_snapshot)
    path = output_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snapshot, encoding="utf-8", newline="\n")


def run_script_with_timeout(
    shell: Shell,
    script: str,
    snapshot_timeout_seconds: float,
    use_login_shell: bool,
    cwd: Path,
) -> str:
    if not isinstance(shell, Shell):
        raise TypeError("shell must be a Shell")
    script = _ensure_str(script, "script")
    snapshot_timeout_seconds = _ensure_number(snapshot_timeout_seconds, "snapshot_timeout_seconds")
    use_login_shell = _ensure_bool(use_login_shell, "use_login_shell")
    cwd = _ensure_path(cwd, "cwd")
    args = shell.derive_exec_args(script, use_login_shell)
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=snapshot_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ShellSnapshotError(f"Snapshot command timed out for {shell.name()}") from exc
    except OSError as exc:
        raise ShellSnapshotError(f"Failed to execute {shell.name()}") from exc

    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        raise ShellSnapshotError(
            f"Snapshot command exited with status {completed.returncode}: {stderr}"
        )
    return stdout


def snapshot_session_id_from_file_name(file_name: str) -> str | None:
    name = _ensure_str(file_name, "file_name")
    if "." not in name:
        return None
    stem, extension = name.rsplit(".", 1)
    if extension in {"sh", "ps1"}:
        return stem.split(".", 1)[0]
    if extension.startswith("tmp-"):
        return stem
    return None


RolloutFinder = Callable[[Path, str], str | Path | None]


def cleanup_stale_snapshots(
    codex_home: Path,
    active_session_id: str,
    *,
    rollout_finder: RolloutFinder | None = None,
    now: float | None = None,
    retention_seconds: float = SNAPSHOT_RETENTION_SECONDS,
) -> list[Path]:
    """Remove stale snapshots and return the files that were deleted."""

    home = _ensure_path(codex_home, "codex_home")
    snapshot_dir = home / SNAPSHOT_DIR
    if not snapshot_dir.exists():
        return []

    if rollout_finder is None:
        from pycodex.rollout import find_thread_path_by_id_str

        rollout_finder = find_thread_path_by_id_str

    removed: list[Path] = []
    current_time = time.time() if now is None else _ensure_number(now, "now")
    retention_seconds = _ensure_number(retention_seconds, "retention_seconds")
    active = _ensure_str(active_session_id, "active_session_id")

    for path in snapshot_dir.iterdir():
        if not path.is_file():
            continue
        session_id = snapshot_session_id_from_file_name(path.name)
        if session_id is None:
            if remove_snapshot_file(path):
                removed.append(path)
            continue
        if session_id == active:
            continue

        rollout_path = rollout_finder(home, session_id)
        if rollout_path is None:
            if remove_snapshot_file(path):
                removed.append(path)
            continue

        try:
            modified = Path(rollout_path).stat().st_mtime
        except OSError:
            continue
        if current_time - modified >= retention_seconds:
            if remove_snapshot_file(path):
                removed.append(path)

    return removed


def remove_snapshot_file(path: Path) -> bool:
    path = _ensure_path(path, "path")
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except OSError:
        return False
    return True


def _coerce_shell_type(shell_type: ShellType) -> ShellType:
    return _ensure_shell_type(shell_type)


__all__ = [
    "EXCLUDED_EXPORT_VARS",
    "SNAPSHOT_DIR",
    "SNAPSHOT_RETENTION_SECONDS",
    "SNAPSHOT_TIMEOUT_SECONDS",
    "ShellSnapshot",
    "ShellSnapshotError",
    "bash_snapshot_script",
    "capture_snapshot",
    "cleanup_stale_snapshots",
    "excluded_exports_regex",
    "powershell_snapshot_script",
    "remove_snapshot_file",
    "run_script_with_timeout",
    "sh_snapshot_script",
    "shell_snapshot_extension",
    "shell_snapshot_paths",
    "snapshot_session_id_from_file_name",
    "strip_snapshot_preamble",
    "write_shell_snapshot",
    "zsh_snapshot_script",
]
