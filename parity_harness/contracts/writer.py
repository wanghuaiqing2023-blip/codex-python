"""Transactional writer for accepted structural contract collections."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import shutil
from typing import Any, Iterable

from parity_harness.paths import REPO_ROOT


def write_structural_contract_set(
    output: Path,
    contracts: Iterable[dict[str, Any]],
    *,
    root: Path = REPO_ROOT,
) -> tuple[dict[str, Any], ...]:
    contracts = tuple(contracts)
    output = output.resolve()
    accepted_root = (root / "parity_harness" / "contracts" / "accepted").resolve()
    if output.parent != accepted_root:
        raise ValueError(
            "generated structural contracts must be one scope directory directly "
            "below parity_harness/contracts/accepted"
        )
    staging = output.parent / f".{output.name}.next"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        for contract in contracts:
            module = str(contract["rust"]["module"])
            parts = module.split("::") if module != "crate" else ["crate"]
            path = staging.joinpath(*parts).with_suffix(".json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(contract, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

        from parity_harness.contracts.collection import load_contract_directory
        from parity_harness.structure.scanner import StructureAuditor

        loaded = load_contract_directory(staging)
        results = StructureAuditor(root=root).check(loaded)
        failed = tuple(result for result in results if result.verdict.value != "verified")
        if failed:
            counts = Counter(item.code for result in failed for item in result.findings)
            raise ValueError(
                "generated structural contracts failed module validation: "
                + json.dumps(dict(sorted(counts.items())))
            )

        backup = output.parent / f".{output.name}.previous"
        if backup.exists():
            shutil.rmtree(backup)
        if output.exists():
            try:
                output.replace(backup)
            except PermissionError:
                # Windows can reject a directory rename while an editor or virus
                # scanner briefly holds a contract file open. Preserve the same
                # rollback guarantee with a copy-and-remove fallback.
                shutil.copytree(output, backup)
                shutil.rmtree(output)
        try:
            staging.replace(output)
        except Exception:
            if backup.exists() and not output.exists():
                backup.replace(output)
            raise
        shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return contracts


__all__ = ["write_structural_contract_set"]
