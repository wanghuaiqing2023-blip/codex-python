"""Workspace-level Rust/Python structure contract and Cargo inventory gate."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import tomllib
from typing import Any

from parity_harness.paths import HARNESS_ROOT, REPO_ROOT
WORKSPACE_CONTRACT_PATH = HARNESS_ROOT / "contracts" / "workspace.json"
WORKSPACE_SCHEMA = "parity-harness/workspace-contract/v1"
BASELINE_COMMIT = "1c7832ffa37a3ab56f601497c00bfce120370bf9"


class WorkspaceContractError(ValueError):
    pass


@dataclass(frozen=True)
class WorkspaceCrate:
    scope: str
    rust_crate: str
    rust_root: str
    cargo_toml: str
    python_root: str
    disposition: str
    reason: str = ""


@dataclass(frozen=True)
class WorkspaceContract:
    workspace: str
    baseline_commit: str
    crates: tuple[WorkspaceCrate, ...]
    source_path: Path

    def crate(self, scope: str) -> WorkspaceCrate:
        matches = tuple(item for item in self.crates if item.scope == scope)
        if len(matches) != 1:
            raise WorkspaceContractError(f"unknown or duplicate workspace scope: {scope}")
        return matches[0]

    @property
    def active(self) -> tuple[WorkspaceCrate, ...]:
        return tuple(item for item in self.crates if item.disposition != "deferred")


def _relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise WorkspaceContractError(f"{field} must be a non-empty string")
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise WorkspaceContractError(f"{field} must be repository-relative")
    return path.as_posix()


def load_workspace_contract(path: Path = WORKSPACE_CONTRACT_PATH) -> WorkspaceContract:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceContractError(f"cannot load workspace contract {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != WORKSPACE_SCHEMA:
        raise WorkspaceContractError(f"workspace contract schema must be {WORKSPACE_SCHEMA}")
    baseline = value.get("baseline_commit")
    if baseline != BASELINE_COMMIT:
        raise WorkspaceContractError("workspace contract is not pinned to the fixed Rust baseline")
    workspace = _relative_path(value.get("workspace"), "workspace")
    raw_crates = value.get("crates")
    if not isinstance(raw_crates, list):
        raise WorkspaceContractError("crates must be a list")
    crates: list[WorkspaceCrate] = []
    for index, raw in enumerate(raw_crates):
        if not isinstance(raw, dict):
            raise WorkspaceContractError(f"crates[{index}] must be an object")
        scope = raw.get("scope")
        if not isinstance(scope, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", scope):
            raise WorkspaceContractError(f"crates[{index}].scope is invalid")
        disposition = raw.get("disposition")
        if disposition not in {"accepted", "partial", "deferred"}:
            raise WorkspaceContractError(f"crates[{index}].disposition is invalid")
        reason = raw.get("reason", "")
        if not isinstance(reason, str):
            raise WorkspaceContractError(f"crates[{index}].reason must be a string")
        if disposition == "deferred" and not reason.strip():
            raise WorkspaceContractError(f"deferred scope {scope} requires a reason")
        crates.append(
            WorkspaceCrate(
                scope=scope,
                rust_crate=str(raw.get("rust_crate", "")),
                rust_root=_relative_path(raw.get("rust_root"), f"crates[{index}].rust_root"),
                cargo_toml=_relative_path(raw.get("cargo_toml"), f"crates[{index}].cargo_toml"),
                python_root=_relative_path(raw.get("python_root"), f"crates[{index}].python_root"),
                disposition=disposition,
                reason=reason.strip(),
            )
        )
    return WorkspaceContract(
        workspace=workspace,
        baseline_commit=baseline,
        crates=tuple(crates),
        source_path=path,
    )


def _cargo_inventory(contract: WorkspaceContract, root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    workspace = root / contract.workspace
    workspace_toml = tomllib.loads(
        (workspace / "Cargo.toml").read_text(encoding="utf-8-sig")
    )
    paths = set(workspace_toml.get("workspace", {}).get("members", ()))
    paths.update(
        value["path"]
        for value in workspace_toml.get("workspace", {}).get("dependencies", {}).values()
        if isinstance(value, dict) and isinstance(value.get("path"), str)
    )
    for relative in sorted(paths):
        crate_root = (workspace / relative).resolve()
        cargo_path = crate_root / "Cargo.toml"
        if not cargo_path.is_file():
            continue
        cargo = tomllib.loads(cargo_path.read_text(encoding="utf-8-sig"))
        name = cargo.get("package", {}).get("name")
        if not isinstance(name, str) or not name:
            continue
        result[name] = crate_root.relative_to(root).as_posix()
    return result


def validate_workspace_contract(
    contract: WorkspaceContract,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    errors: list[str] = []
    scopes = [item.scope for item in contract.crates]
    crates = [item.rust_crate for item in contract.crates]
    roots = [item.rust_root for item in contract.crates]
    for label, values in (("scope", scopes), ("Rust crate", crates), ("Rust root", roots)):
        duplicates = sorted({value for value in values if values.count(value) > 1})
        errors.extend(f"duplicate {label}: {value}" for value in duplicates)

    cargo = _cargo_inventory(contract, root)
    declared = {item.rust_crate: item.rust_root for item in contract.crates}
    for name in sorted(cargo.keys() - declared.keys()):
        errors.append(f"Cargo crate is not classified: {name} ({cargo[name]})")
    for name in sorted(declared.keys() - cargo.keys()):
        errors.append(f"workspace contract crate is not in Cargo workspace: {name}")
    for name in sorted(cargo.keys() & declared.keys()):
        if cargo[name] != declared[name]:
            errors.append(
                f"Cargo root mismatch for {name}: contract={declared[name]} cargo={cargo[name]}"
            )

    accepted_root = HARNESS_ROOT / "contracts" / "accepted"
    for item in contract.crates:
        if not (root / item.cargo_toml).is_file():
            errors.append(f"missing Cargo.toml for {item.scope}: {item.cargo_toml}")
        if item.disposition == "deferred":
            python_root = root / item.python_root
            if python_root.is_dir():
                production_files = tuple(
                    path
                    for path in python_root.rglob("*.py")
                    if "tests" not in path.relative_to(python_root).parts
                    and "__pycache__" not in path.parts
                )
                if production_files:
                    errors.append(
                        f"deferred scope {item.scope} contains Python product files: "
                        + ", ".join(
                            path.relative_to(root).as_posix()
                            for path in production_files[:5]
                        )
                    )
            continue
        if not (root / item.python_root).is_dir():
            errors.append(f"missing Python root for {item.scope}: {item.python_root}")
        if not (accepted_root / f"{item.scope}.policy.json").is_file():
            errors.append(f"missing structure policy for active scope: {item.scope}")
        if not (accepted_root / item.scope).is_dir():
            errors.append(f"missing accepted contract directory for active scope: {item.scope}")

    return {
        "verdict": "verified" if not errors else "failed",
        "crates": len(contract.crates),
        "active": len(contract.active),
        "deferred": sum(item.disposition == "deferred" for item in contract.crates),
        "errors": errors,
    }


__all__ = [
    "BASELINE_COMMIT",
    "WORKSPACE_CONTRACT_PATH",
    "WorkspaceContract",
    "WorkspaceContractError",
    "WorkspaceCrate",
    "load_workspace_contract",
    "validate_workspace_contract",
]
