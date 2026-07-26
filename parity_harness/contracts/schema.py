"""Strict JSON contract schema without third-party dependencies."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from parity_harness.model import MappingStatus


class ContractError(ValueError):
    pass


_REQUIRED_RUST = {
    "workspace",
    "crate",
    "module",
    "source",
    "anchors",
    "baseline_commit",
}
_REQUIRED_PYTHON = {"owner", "layout", "implementation_files", "anchors"}
_REQUIRED_CHECKS = {"structure"}


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{name} must be an object")
    return dict(value)


def _require_keys(value: dict[str, Any], required: set[str], name: str) -> None:
    missing = sorted(required - set(value))
    if missing:
        raise ContractError(f"{name} is missing required fields: {', '.join(missing)}")


def _string_list(value: Any, name: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ContractError(f"{name} must be a list of strings")
    if nonempty and not value:
        raise ContractError(f"{name} must not be empty")
    return tuple(value)


def _safe_relative(value: str, name: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise ContractError(f"{name} must be a repository-relative path")
    return path.as_posix()


@dataclass(frozen=True)
class ModuleContract:
    contract_id: str
    evidence_status: MappingStatus
    rust: dict[str, Any]
    python: dict[str, Any]
    checks: dict[str, Any]
    fixture_refs: tuple[str, ...]
    source_path: Path

    @property
    def rust_coordinate(self) -> str:
        return f"{self.rust['crate']}::{self.rust['module']}"

    @property
    def python_owner(self) -> str:
        return str(self.python["owner"])


@dataclass(frozen=True)
class StructureScopePolicy:
    scope: str
    rust_root: str
    python_root: str
    allowed_unowned: tuple[dict[str, str], ...]
    check_item_ownership: bool
    include_inline_modules: bool
    check_orphans: bool
    coverage_expectation: str
    uncovered_rust_modules: tuple[str, ...]
    uncovered_python_files: tuple[str, ...]
    source_path: Path


def contract_from_dict(value: dict[str, Any], *, source_path: Path) -> ModuleContract:
    if "behavior" in value:
        raise ContractError(
            "behavior was removed because prose is not executable evidence; "
            "the current contract schema accepts structure checks only"
        )
    for field in ("contract_id", "evidence_status", "rust", "python", "checks"):
        if field not in value:
            raise ContractError(f"contract is missing required field: {field}")
    contract_id = value["contract_id"]
    if not isinstance(contract_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]+", contract_id):
        raise ContractError("contract_id must be a stable lowercase identifier")
    try:
        status = MappingStatus(value["evidence_status"])
    except (TypeError, ValueError) as exc:
        raise ContractError(f"unknown evidence_status: {value['evidence_status']!r}") from exc

    rust = _mapping(value["rust"], "rust")
    python = _mapping(value["python"], "python")
    checks = _mapping(value["checks"], "checks")
    _require_keys(rust, _REQUIRED_RUST, "rust")
    _require_keys(python, _REQUIRED_PYTHON, "python")
    _require_keys(checks, _REQUIRED_CHECKS, "checks")

    rust["source"] = _safe_relative(str(rust["source"]), "rust.source")
    rust["workspace"] = _safe_relative(str(rust["workspace"]), "rust.workspace")
    rust["anchors"] = _string_list(rust["anchors"], "rust.anchors", nonempty=True)
    baseline = rust["baseline_commit"]
    if not isinstance(baseline, str) or not re.fullmatch(r"[0-9a-f]{40}", baseline):
        raise ContractError("rust.baseline_commit must be a full 40-character commit SHA")

    python["owner"] = _safe_relative(str(python["owner"]), "python.owner")
    if python["layout"] not in {"module-file", "module-package"}:
        raise ContractError("python.layout must be module-file or module-package")
    python["implementation_files"] = tuple(
        _safe_relative(item, "python.implementation_files")
        for item in _string_list(
            python["implementation_files"],
            "python.implementation_files",
            nonempty=True,
        )
    )
    python["anchors"] = _string_list(python["anchors"], "python.anchors", nonempty=True)
    unexpected_checks = sorted(set(checks) - _REQUIRED_CHECKS)
    if unexpected_checks:
        raise ContractError(
            "only structure checks are currently accepted; unsupported checks: "
            + ", ".join(unexpected_checks)
        )
    for field in _REQUIRED_CHECKS:
        if not isinstance(checks[field], dict):
            raise ContractError(f"checks.{field} must be an object")
    structure = checks["structure"]
    for field in ("owned_symbols", "restricted_decisions", "allowed_decision_files"):
        if field in structure:
            structure[field] = _string_list(
                structure[field],
                f"checks.structure.{field}",
            )
    if "allowed_dependencies" in structure:
        dependencies = structure["allowed_dependencies"]
        if dependencies is not None:
            structure["allowed_dependencies"] = _string_list(
                dependencies,
                "checks.structure.allowed_dependencies",
            )
    if structure.get("allowed_decision_files") and not structure.get(
        "restricted_decisions"
    ):
        raise ContractError(
            "checks.structure.allowed_decision_files requires restricted_decisions"
        )
    fixture_refs = tuple(
        _safe_relative(item, "fixture_refs")
        for item in _string_list(value.get("fixture_refs", []), "fixture_refs")
    )
    return ModuleContract(
        contract_id=contract_id,
        evidence_status=status,
        rust=rust,
        python=python,
        checks=checks,
        fixture_refs=fixture_refs,
        source_path=source_path,
    )


def load_contract(path: Path) -> ModuleContract:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load contract {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError("contract document must be a JSON object")
    return contract_from_dict(value, source_path=path)


def load_structure_policy(path: Path) -> StructureScopePolicy:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load structure policy {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError("structure policy must be a JSON object")
    _require_keys(
        value,
        {"scope", "rust_root", "python_root", "allowed_unowned"},
        "policy",
    )
    scope = value["scope"]
    if not isinstance(scope, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]+", scope):
        raise ContractError("policy.scope must be a stable lowercase identifier")
    rust_root = _safe_relative(str(value["rust_root"]), "policy.rust_root")
    python_root = _safe_relative(str(value["python_root"]), "policy.python_root")
    raw_allowed = value["allowed_unowned"]
    if not isinstance(raw_allowed, list):
        raise ContractError("policy.allowed_unowned must be a list")
    allowed: list[dict[str, str]] = []
    for index, item in enumerate(raw_allowed):
        if not isinstance(item, dict):
            raise ContractError(f"policy.allowed_unowned[{index}] must be an object")
        _require_keys(item, {"path", "reason"}, f"policy.allowed_unowned[{index}]")
        reason = item["reason"]
        if not isinstance(reason, str) or not reason.strip():
            raise ContractError(
                f"policy.allowed_unowned[{index}].reason must not be empty"
            )
        allowed.append(
            {
                "path": _safe_relative(
                    str(item["path"]),
                    f"policy.allowed_unowned[{index}].path",
                ),
                "reason": reason.strip(),
            }
        )
    paths = [item["path"] for item in allowed]
    if len(paths) != len(set(paths)):
        raise ContractError("policy.allowed_unowned contains duplicate paths")
    check_item_ownership = value.get("check_item_ownership", False)
    if not isinstance(check_item_ownership, bool):
        raise ContractError("policy.check_item_ownership must be a boolean")
    include_inline_modules = value.get("include_inline_modules", False)
    if not isinstance(include_inline_modules, bool):
        raise ContractError("policy.include_inline_modules must be a boolean")
    check_orphans = value.get("check_orphans", False)
    if not isinstance(check_orphans, bool):
        raise ContractError("policy.check_orphans must be a boolean")
    coverage_expectation = value.get("coverage_expectation", "verified")
    if coverage_expectation not in {"verified", "partial"}:
        raise ContractError("policy.coverage_expectation must be verified or partial")
    uncovered_rust_modules = _string_list(
        value.get("uncovered_rust_modules", []),
        "policy.uncovered_rust_modules",
    )
    uncovered_python_files = tuple(
        _safe_relative(item, "policy.uncovered_python_files")
        for item in _string_list(
            value.get("uncovered_python_files", []),
            "policy.uncovered_python_files",
        )
    )
    if coverage_expectation == "verified" and uncovered_rust_modules:
        raise ContractError("verified policy cannot declare Rust coverage debt")
    return StructureScopePolicy(
        scope=scope,
        rust_root=rust_root,
        python_root=python_root,
        allowed_unowned=tuple(allowed),
        check_item_ownership=check_item_ownership,
        include_inline_modules=include_inline_modules,
        check_orphans=check_orphans,
        coverage_expectation=coverage_expectation,
        uncovered_rust_modules=uncovered_rust_modules,
        uncovered_python_files=uncovered_python_files,
        source_path=path,
    )
