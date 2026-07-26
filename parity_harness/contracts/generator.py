"""Generic, source-derived review candidate generation for any workspace crate."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from parity_harness.contracts.anchors import anchor_candidates, fallback_module_anchors
from parity_harness.paths import HARNESS_ROOT, REPO_ROOT
from parity_harness.structure.scanner import discover_python_modules, discover_rust_modules
from parity_harness.workspace import load_workspace_contract


CANDIDATE_SCHEMA = "parity-harness/structure-candidates/v1"


def _contract_coordinate(graph_coordinate: str) -> str:
    """Convert scanner graph coordinates to the accepted-contract convention."""
    if graph_coordinate.startswith("crate::"):
        return graph_coordinate.removeprefix("crate::")
    return graph_coordinate


def _python_candidates(
    module: str,
    python_root: str,
    files: set[str],
    rust_source: str | None = None,
) -> tuple[str, ...]:
    root = PurePosixPath(python_root)
    if module == "crate":
        expected = (root / "__init__.py",)
    elif module == "main":
        expected = (root / "__main__.py", root / "main.py")
    elif module.startswith("bin::"):
        source = PurePosixPath(rust_source) if rust_source is not None else None
        if source is not None and "bin" in source.parts:
            bin_index = len(source.parts) - 1 - source.parts[::-1].index("bin")
            relative = source.parts[bin_index + 1 :]
            directories = relative[:-1]
            source_name = relative[-1]
            if source_name == "main.rs":
                base = root.joinpath("bin", *directories)
                expected = (base / "__main__.py", base / "main.py")
            else:
                base = root.joinpath("bin", *directories, Path(source_name).stem)
                expected = (base.with_suffix(".py"), base / "__init__.py")
        else:
            leaf = module.split("::", 1)[1].replace("-", "_")
            expected = (root / "bin" / f"{leaf}.py", root / f"{leaf}.py")
    else:
        parts = module.removeprefix("crate::").split("::")
        base = root.joinpath(*parts)
        expected = (base.with_suffix(".py"), base / "__init__.py")
    direct = tuple(path.as_posix() for path in expected if path.as_posix() in files)
    if direct:
        return direct
    leaf = module.split("::")[-1]
    return tuple(
        sorted(
            path
            for path in files
            if PurePosixPath(path).stem == leaf
            or (
                PurePosixPath(path).name == "__init__.py"
                and PurePosixPath(path).parent.name == leaf
            )
        )
    )


def generate_candidate_catalog(
    scope: str,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    workspace = load_workspace_contract()
    crate = workspace.crate(scope)
    if crate.disposition == "deferred":
        raise ValueError(f"deferred scope has no Python structure candidates: {scope}")
    python_files = set(discover_python_modules(root / crate.python_root))
    modules = discover_rust_modules(root / crate.rust_root, include_inline_modules=True)
    contracts: list[dict[str, Any]] = []
    for module in modules:
        candidates = _python_candidates(
            module.name,
            crate.python_root,
            python_files,
            module.source,
        )
        contract_coordinate = _contract_coordinate(module.name)
        candidate_rows: list[dict[str, Any]] = []
        for owner in candidates:
            anchors = anchor_candidates(
                root / module.source,
                (root / owner,),
                rust_module=module.name,
            ) or fallback_module_anchors(
                module.source,
                owner,
                root=root,
                rust_module=module.name,
            )
            candidate_rows.append({"owner": owner, "anchor_candidates": list(anchors)})
        contracts.append(
            {
                "rust": {
                    "crate": crate.rust_crate,
                    "module": contract_coordinate,
                    "source": module.source,
                    "baseline_commit": workspace.baseline_commit,
                },
                "python_candidates": candidate_rows,
                "review": {
                    "status": "candidate",
                    "unresolved": ["owner-review", "anchor-review"],
                },
            }
        )
    return {
        "schema": CANDIDATE_SCHEMA,
        "scope": scope,
        "evidence_status": "candidate",
        "baseline_commit": workspace.baseline_commit,
        "generation_policy": {
            "cargo_graph_is_source": True,
            "python_tree_is_source": True,
            "accepted_contracts_are_not_read": True,
            "generated_candidates_cannot_claim_parity": True,
        },
        "summary": {
            "rust_modules": len(modules),
            "python_files": len(python_files),
            "modules_with_candidates": sum(bool(item["python_candidates"]) for item in contracts),
            "modules_with_anchors": sum(
                any(row["anchor_candidates"] for row in item["python_candidates"])
                for item in contracts
            ),
        },
        "contracts": contracts,
    }


def write_candidate_catalog(scope: str, output: Path | None = None) -> dict[str, Any]:
    catalog = generate_candidate_catalog(scope)
    target = output or HARNESS_ROOT / "contracts" / "generated" / f"{scope}.candidates.json"
    target = target.resolve()
    generated_root = (HARNESS_ROOT / "contracts" / "generated").resolve()
    if generated_root not in target.parents:
        raise ValueError("candidate catalog must stay below parity_harness/contracts/generated")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    return catalog


__all__ = ["CANDIDATE_SCHEMA", "generate_candidate_catalog", "write_candidate_catalog"]
