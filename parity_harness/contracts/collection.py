"""Accepted contract collection loading and cross-contract integrity gates."""

from __future__ import annotations

from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Iterable

from parity_harness.model import MappingStatus

from .schema import (
    ContractError,
    ModuleContract,
    StructureScopePolicy,
    load_contract,
)


def load_contract_directory(
    root: Path,
    *,
    allow_empty: bool = False,
) -> tuple[ModuleContract, ...]:
    if not root.is_dir():
        raise ContractError(f"accepted contract directory does not exist: {root}")
    paths = tuple(sorted(root.rglob("*.json")))
    if not paths and not allow_empty:
        raise ContractError(f"accepted contract directory is empty: {root}")
    if not paths:
        return ()
    return validate_contract_set(load_contract(path) for path in paths)


def validate_contract_set(
    contracts: Iterable[ModuleContract],
) -> tuple[ModuleContract, ...]:
    """Reject contradictions before contracts can become structural standards."""
    contracts = tuple(contracts)
    if not contracts:
        raise ContractError("accepted contract set must not be empty")

    errors: list[str] = []
    indexes = (
        (
            "contract_id",
            Counter(contract.contract_id for contract in contracts),
        ),
        (
            "Rust module",
            Counter(contract.rust_coordinate for contract in contracts),
        ),
        (
            "Python owner",
            Counter(contract.python_owner for contract in contracts),
        ),
        (
            "implementation file",
            Counter(
                path
                for contract in contracts
                for path in contract.python["implementation_files"]
            ),
        ),
    )
    for label, counts in indexes:
        for value, count in sorted(counts.items()):
            if count > 1:
                errors.append(f"duplicate {label}: {value} ({count} claims)")

    baselines = {contract.rust["baseline_commit"] for contract in contracts}
    if len(baselines) > 1:
        errors.append("accepted contract set mixes Rust baseline commits")

    for contract in contracts:
        coordinate = contract.contract_id
        if contract.evidence_status in {
            MappingStatus.CANDIDATE,
            MappingStatus.INCONCLUSIVE,
        }:
            errors.append(
                f"{coordinate}: unresolved evidence status cannot enter accepted contracts"
            )
        owner = PurePosixPath(contract.python_owner)
        if contract.rust["anchors"] != contract.python["anchors"]:
            errors.append(
                f"{coordinate}: Rust and Python anchors must be the same mapped symbols"
            )
        implementations = tuple(
            PurePosixPath(path) for path in contract.python["implementation_files"]
        )
        if owner not in implementations:
            errors.append(f"{coordinate}: Python owner is not an implementation file")
        if contract.python["layout"] == "module-file":
            if implementations != (owner,):
                errors.append(
                    f"{coordinate}: module-file contract must own exactly its owner file"
                )
        else:
            if owner.name != "__init__.py":
                errors.append(
                    f"{coordinate}: module-package owner must be an __init__.py file"
                )
            scattered = tuple(
                path
                for path in implementations
                if path != owner and owner.parent not in path.parents
            )
            if scattered:
                errors.append(
                    f"{coordinate}: module-package files escape owner directory: "
                    + ", ".join(map(str, scattered))
                )

    if errors:
        raise ContractError("accepted contract set is inconsistent:\n- " + "\n- ".join(errors))
    return contracts


def validate_contract_scope(
    contracts: Iterable[ModuleContract],
    *,
    scope: str,
    rust_crate: str,
    rust_root: str,
    python_root: str,
    baseline_commit: str,
    policy: StructureScopePolicy,
) -> tuple[ModuleContract, ...]:
    """Ensure accepted documents cannot be filed under an unrelated crate scope."""
    contracts = tuple(contracts)
    errors: list[str] = []
    expected_rust_root = PurePosixPath(rust_root)
    expected_python_root = PurePosixPath(python_root)

    if policy.scope != scope:
        errors.append(f"policy scope mismatch: expected {scope}, got {policy.scope}")
    if PurePosixPath(policy.rust_root) != expected_rust_root:
        errors.append(
            f"policy Rust root mismatch: expected {rust_root}, got {policy.rust_root}"
        )
    if PurePosixPath(policy.python_root) != expected_python_root:
        errors.append(
            f"policy Python root mismatch: expected {python_root}, got {policy.python_root}"
        )

    for contract in contracts:
        coordinate = contract.contract_id
        if contract.rust["crate"] != rust_crate:
            errors.append(
                f"{coordinate}: Rust crate {contract.rust['crate']} does not belong "
                f"to scope {scope} ({rust_crate})"
            )
        if contract.rust["baseline_commit"] != baseline_commit:
            errors.append(
                f"{coordinate}: Rust baseline does not match workspace baseline"
            )
        rust_source = PurePosixPath(contract.rust["source"])
        if not rust_source.is_relative_to(expected_rust_root):
            errors.append(
                f"{coordinate}: Rust source escapes scope root {rust_root}: {rust_source}"
            )
        owner = PurePosixPath(contract.python_owner)
        if not owner.is_relative_to(expected_python_root):
            errors.append(
                f"{coordinate}: Python owner escapes scope root {python_root}: {owner}"
            )
        for implementation in contract.python["implementation_files"]:
            implementation_path = PurePosixPath(implementation)
            if not implementation_path.is_relative_to(expected_python_root):
                errors.append(
                    f"{coordinate}: Python implementation escapes scope root "
                    f"{python_root}: {implementation_path}"
                )

    if errors:
        raise ContractError(
            "accepted contracts do not match their workspace scope:\n- "
            + "\n- ".join(errors)
        )
    return contracts


__all__ = [
    "load_contract_directory",
    "validate_contract_scope",
    "validate_contract_set",
]
