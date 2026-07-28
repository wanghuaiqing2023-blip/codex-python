from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from parity_harness.model import MappingStatus, Verdict
from parity_harness.paths import ArtifactWorkspace
from parity_harness.structure import (
    StructureAuditor,
    discover_rust_modules,
    discover_workspace_crates,
)
from parity_harness.structure.scanner import COVERAGE_FINDING_CODES
from parity_harness.contracts.schema import contract_from_dict
from parity_harness.contracts.anchors import anchor_candidates, fallback_module_anchors
from parity_harness.workflow import example_contract


class StructureTests(unittest.TestCase):
    def test_named_and_wildcard_reexports_are_executable_anchors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rust = root / "rust/lib.rs"
            python = root / "python/path_utils.py"
            rust.parent.mkdir(parents=True)
            python.parent.mkdir(parents=True)
            rust.write_text(
                "pub use codex_tools::FunctionCallError;\n"
                "pub use codex_utils_path::*;\n",
                encoding="utf-8",
            )
            python.write_text(
                "from tools import FunctionCallError\n"
                "from pycodex.utils.path_utils import normalize_for_native_workdir\n",
                encoding="utf-8",
            )
            self.assertIn("FunctionCallError", anchor_candidates(rust, (python,)))
            self.assertEqual(
                fallback_module_anchors(
                    "rust/lib.rs",
                    "python/path_utils.py",
                    root=root,
                ),
                ("reexport:path_utils",),
            )

    def test_named_module_reexport_anchor_is_executable(self) -> None:
        contract = replace(
            example_contract(),
            rust={
                **example_contract().rust,
                "anchors": ["reexport:config"],
            },
            python={
                **example_contract().python,
                "anchors": ["reexport:config"],
            },
            fixture_refs=(),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rust_path = root / contract.rust["source"]
            rust_path.parent.mkdir(parents=True, exist_ok=True)
            rust_path.write_text(
                "pub use config::NetworkProxyConfig;\n",
                encoding="utf-8",
            )
            for relative in contract.python["implementation_files"]:
                python_path = root / relative
                python_path.parent.mkdir(parents=True, exist_ok=True)
                python_path.write_text(
                    "from .config import NetworkProxyConfig\n",
                    encoding="utf-8",
                )

            result = StructureAuditor(root=root).check((contract,))[0]

        self.assertEqual(result.verdict, Verdict.VERIFIED)
        self.assertFalse(result.findings)

    def test_cargo_bin_target_name_is_not_treated_as_an_inline_module(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rust = root / "rust/main.rs"
            python = root / "python/main.py"
            rust.parent.mkdir(parents=True)
            python.parent.mkdir(parents=True)
            rust.write_text("pub fn run() {}\n", encoding="utf-8")
            python.write_text("def run(): pass\n", encoding="utf-8")

            anchors = anchor_candidates(
                rust,
                (python,),
                rust_module="bin::custom-target",
            )

        self.assertEqual(anchors, ("run",))

    def test_inline_module_include_uses_symbols_from_relative_binding_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rust = root / "rust/macos.rs"
            bindings = root / "rust/iokit_bindings.rs"
            python = root / "python/iokit.py"
            rust.parent.mkdir(parents=True)
            python.parent.mkdir(parents=True)
            rust.write_text(
                'mod iokit {\n    include!("iokit_bindings.rs");\n}\n',
                encoding="utf-8",
            )
            bindings.write_text(
                "pub const kIOReturnSuccess: u32 = 0;\n",
                encoding="utf-8",
            )
            python.write_text("kIOReturnSuccess = 0\n", encoding="utf-8")

            anchors = anchor_candidates(
                rust,
                (python,),
                rust_module="macos::iokit",
            )

        self.assertEqual(anchors, ("kIOReturnSuccess",))

    def test_inline_wildcard_reexport_uses_its_imported_source_module(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rust = root / "rust/rollout.rs"
            python = root / "python/rollout/truncation.py"
            rust.parent.mkdir(parents=True)
            python.parent.mkdir(parents=True)
            rust.write_text(
                "pub(crate) mod truncation {\n"
                "    pub(crate) use crate::thread_rollout_truncation::*;\n"
                "}\n",
                encoding="utf-8",
            )
            python.write_text(
                "from python.thread_rollout_truncation import truncate_rollout\n",
                encoding="utf-8",
            )

            self.assertEqual(
                fallback_module_anchors(
                    "rust/rollout.rs",
                    "python/rollout/truncation.py",
                    root=root,
                    rust_module="crate::rollout::truncation",
                ),
                ("reexport:thread_rollout_truncation",),
            )

    def test_python_anchor_detection_accepts_utf8_bom(self) -> None:
        contract = replace(example_contract(), fixture_refs=())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, relative in enumerate(contract.python["implementation_files"]):
                python_path = root / relative
                python_path.parent.mkdir(parents=True, exist_ok=True)
                source = "class render_status:\n    pass\n" if index == 0 else ""
                python_path.write_text(source, encoding="utf-8-sig")
            rust_path = root / contract.rust["source"]
            rust_path.parent.mkdir(parents=True, exist_ok=True)
            rust_path.write_text("fn render_status() {}\n", encoding="utf-8")
            result = StructureAuditor(root=root).check((contract,))[0]

        self.assertEqual(result.verdict, Verdict.VERIFIED)

    def test_file_to_bounded_package_mapping_is_legal(self) -> None:
        result = StructureAuditor().check((example_contract(),))[0]
        self.assertEqual(result.verdict, Verdict.VERIFIED)
        self.assertFalse(result.findings)

    def test_package_module_anchor_requires_matching_children_on_both_sides(self) -> None:
        contract = replace(example_contract(), fixture_refs=())
        rust = dict(contract.rust)
        rust["anchors"] = ("module:child",)
        python = dict(contract.python)
        python["owner"] = "python/pkg/__init__.py"
        python["layout"] = "module-package"
        python["implementation_files"] = (
            "python/pkg/__init__.py",
            "python/pkg/child.py",
        )
        python["anchors"] = ("module:child",)
        contract = replace(contract, rust=rust, python=python)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rust_path = root / contract.rust["source"]
            rust_path.parent.mkdir(parents=True, exist_ok=True)
            rust_path.write_text("pub mod child;\n", encoding="utf-8")
            for relative in contract.python["implementation_files"]:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
            result = StructureAuditor(root=root).check((contract,))[0]

        self.assertEqual(result.verdict, Verdict.VERIFIED)

    def test_module_file_anchor_accepts_imported_sibling_module(self) -> None:
        contract = replace(example_contract(), fixture_refs=())
        rust = dict(contract.rust)
        rust["anchors"] = ("module:child",)
        python = dict(contract.python)
        python["owner"] = "python/parent.py"
        python["layout"] = "module-file"
        python["implementation_files"] = ("python/parent.py",)
        python["anchors"] = ("module:child",)
        contract = replace(contract, rust=rust, python=python)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rust_path = root / contract.rust["source"]
            rust_path.parent.mkdir(parents=True, exist_ok=True)
            rust_path.write_text("pub mod child;\n", encoding="utf-8")
            python_path = root / contract.python["owner"]
            python_path.parent.mkdir(parents=True, exist_ok=True)
            python_path.write_text("from . import child\n", encoding="utf-8")
            (python_path.parent / "child.py").write_text("", encoding="utf-8")
            result = StructureAuditor(root=root).check((contract,))[0]

        self.assertEqual(result.verdict, Verdict.VERIFIED)

    def test_missing_fixture_reference_is_rejected(self) -> None:
        contract = replace(example_contract(), fixture_refs=("tests/missing_fixture.py",))
        result = StructureAuditor().check((contract,))[0]
        self.assertEqual(result.verdict, Verdict.FAILED)
        self.assertIn("STR001", {item.code for item in result.findings})

    def test_main_child_coordinate_is_not_rewritten_as_crate_module(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rust/src").mkdir(parents=True)
            (root / "python/sample").mkdir(parents=True)
            (root / "rust/Cargo.toml").write_text(
                "[package]\nname='sample'\nversion='0.0.0'\n",
                encoding="utf-8",
            )
            (root / "rust/src/main.rs").write_text("mod child;\n", encoding="utf-8")
            (root / "rust/src/child.rs").write_text("fn child_api() {}\n", encoding="utf-8")
            (root / "python/sample/child.py").write_text(
                "def child_api(): pass\n", encoding="utf-8"
            )
            contract = contract_from_dict(
                {
                    "contract_id": "sample.main-child",
                    "evidence_status": "mapped",
                    "rust": {
                        "workspace": "rust",
                        "crate": "sample",
                        "module": "main::child",
                        "source": "rust/src/child.rs",
                        "anchors": ["child_api"],
                        "baseline_commit": "1" * 40,
                    },
                    "python": {
                        "owner": "python/sample/child.py",
                        "layout": "module-file",
                        "implementation_files": ["python/sample/child.py"],
                        "anchors": ["child_api"],
                    },
                    "checks": {"structure": {}},
                },
                source_path=root / "contract.json",
            )
            result = StructureAuditor(root=root).audit_inventory(
                (contract,),
                rust_root="rust",
                python_root="python/sample",
            )
        self.assertNotIn("STR016", {item.code for item in result.findings})
        self.assertFalse(any(
            item.code == "STR018" and item.coordinate.startswith("main::child ")
            for item in result.findings
        ))

    def test_same_named_modules_cannot_be_matched_by_filename_alone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rust_root = root / "rust" / "sample"
            python_root = root / "python" / "sample"
            (rust_root / "src" / "left").mkdir(parents=True)
            (rust_root / "src" / "right").mkdir(parents=True)
            python_root.mkdir(parents=True)
            (rust_root / "Cargo.toml").write_text(
                "[package]\nname='sample'\nversion='0.0.0'\n",
                encoding="utf-8",
            )
            (rust_root / "src" / "lib.rs").write_text(
                "pub mod left;\npub mod right;\n",
                encoding="utf-8",
            )
            (rust_root / "src" / "left.rs").write_text(
                "pub mod shell;\n", encoding="utf-8"
            )
            (rust_root / "src" / "right.rs").write_text(
                "pub mod shell;\n", encoding="utf-8"
            )
            (rust_root / "src" / "left" / "shell.rs").write_text(
                "pub fn run_shell() {}\n", encoding="utf-8"
            )
            (rust_root / "src" / "right" / "shell.rs").write_text(
                "pub fn run_shell() {}\n", encoding="utf-8"
            )
            (python_root / "shell.py").write_text(
                "def run_shell(): pass\n", encoding="utf-8"
            )
            contract = contract_from_dict(
                {
                    "contract_id": "sample.left-shell",
                    "evidence_status": "mapped",
                    "rust": {
                        "workspace": "rust",
                        "crate": "sample",
                        "module": "left::shell",
                        # Deliberately point the left coordinate at right/shell.rs.
                        "source": "rust/sample/src/right/shell.rs",
                        "anchors": ["run_shell"],
                        "baseline_commit": "1" * 40,
                    },
                    "python": {
                        "owner": "python/sample/shell.py",
                        "layout": "module-file",
                        "implementation_files": ["python/sample/shell.py"],
                        "anchors": ["run_shell"],
                    },
                    "checks": {"structure": {}},
                },
                source_path=root / "contract.json",
            )
            result = StructureAuditor(root=root).audit_inventory(
                (contract,),
                rust_root="rust/sample",
                python_root="python/sample",
                uncovered_rust_modules=("crate", "crate::left", "crate::right", "crate::right::shell"),
            )

        self.assertIn("STR025", {item.code for item in result.findings})

    def test_executable_contract_capabilities_detect_architecture_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rust/src").mkdir(parents=True)
            (root / "python/sample").mkdir(parents=True)
            (root / "rust/src/lib.rs").write_text("fn owner_api() {}\n", encoding="utf-8")
            (root / "python/sample/owner.py").write_text(
                "from python.sample.forbidden import helper\n"
                "def owner_api(): pass\n"
                "def unique_owner(): pass\n",
                encoding="utf-8",
            )
            (root / "python/sample/rogue.py").write_text(
                "def unique_owner(): pass\n"
                "def choose(value): return value == 'raw-decision'\n",
                encoding="utf-8",
            )
            contract = contract_from_dict(
                {
                    "contract_id": "sample.capabilities",
                    "evidence_status": "mapped",
                    "rust": {
                        "workspace": "rust",
                        "crate": "sample",
                        "module": "crate",
                        "source": "rust/src/lib.rs",
                        "anchors": ["owner_api"],
                        "baseline_commit": "1" * 40,
                    },
                    "python": {
                        "owner": "python/sample/owner.py",
                        "layout": "module-file",
                        "implementation_files": ["python/sample/owner.py"],
                        "anchors": ["owner_api"],
                    },
                    "checks": {
                        "structure": {
                            "owned_symbols": ["unique_owner"],
                            "allowed_dependencies": ["python.sample.allowed"],
                            "restricted_decisions": ["raw-decision"],
                        }
                    },
                },
                source_path=root / "contract.json",
            )
            result = StructureAuditor(
                root=root,
                python_root="python/sample",
            ).check((contract,))[0]
        self.assertEqual(result.verdict, Verdict.FAILED)
        self.assertTrue({"STR021", "STR022", "STR023"}.issubset(
            {item.code for item in result.findings}
        ))

    def test_orphan_check_is_opt_in_and_detects_unconsumed_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rust/src").mkdir(parents=True)
            (root / "python/sample").mkdir(parents=True)
            (root / "rust/src/lib.rs").write_text("fn owner_api() {}\n", encoding="utf-8")
            (root / "python/sample/owner.py").write_text(
                "def owner_api(): pass\n", encoding="utf-8"
            )
            contract = contract_from_dict(
                {
                    "contract_id": "sample.orphan",
                    "evidence_status": "mapped",
                    "rust": {
                        "workspace": "rust",
                        "crate": "sample",
                        "module": "crate",
                        "source": "rust/src/lib.rs",
                        "anchors": ["owner_api"],
                        "baseline_commit": "1" * 40,
                    },
                    "python": {
                        "owner": "python/sample/owner.py",
                        "layout": "module-file",
                        "implementation_files": ["python/sample/owner.py"],
                        "anchors": ["owner_api"],
                    },
                    "checks": {"structure": {}},
                },
                source_path=root / "contract.json",
            )
            result = StructureAuditor(root=root, check_orphans=True).audit_inventory(
                (contract,),
                python_root="python/sample",
            )
        self.assertIn("STR024", {item.code for item in result.findings})

    def test_scattered_package_implementation_is_rejected(self) -> None:
        contract = example_contract()
        python = dict(contract.python)
        python["implementation_files"] = (*python["implementation_files"], "parity_harness/model.py")
        result = StructureAuditor().check((replace(contract, python=python),))[0]
        self.assertEqual(result.verdict, Verdict.FAILED)
        self.assertIn("STR005", {item.code for item in result.findings})

    def test_duplicate_owner_is_rejected(self) -> None:
        contract = example_contract()
        duplicate = replace(contract, contract_id="harness-fixture.duplicate")
        results = StructureAuditor().check((contract, duplicate))
        self.assertTrue(all(result.verdict == Verdict.FAILED for result in results))
        self.assertTrue(all("STR002" in {item.code for item in result.findings} for result in results))

    def test_distinct_rust_modules_cannot_be_aggregated_into_one_owner(self) -> None:
        child = example_contract()
        rust = dict(child.rust)
        rust.update(
            module="crate",
            source="parity_harness/fixtures/example_repo/rust/src/lib.rs",
        )
        parent = replace(
            child,
            contract_id="harness-fixture.crate",
            rust=rust,
        )

        results = StructureAuditor().check((parent, child))

        self.assertTrue(all(result.verdict == Verdict.FAILED for result in results))
        self.assertTrue(
            all("STR002" in {item.code for item in result.findings} for result in results)
        )

    def test_candidate_cannot_become_verified_from_structure(self) -> None:
        contract = replace(example_contract(), evidence_status=MappingStatus.CANDIDATE)
        result = StructureAuditor().check((contract,))[0]
        self.assertEqual(result.verdict, Verdict.INCONCLUSIVE)
        self.assertIn("STR009", {item.code for item in result.findings})

    def test_unregistered_python_file_is_detected(self) -> None:
        contract = example_contract()
        auditor = StructureAuditor()
        result = auditor.audit_inventory(
            (contract,),
            python_root="parity_harness/fixtures/example_repo/python",
            contract_id=contract.contract_id,
        )
        codes = {item.code for item in result.findings}
        self.assertIn("STR012", codes)

    def test_declared_python_debt_remains_an_ownership_failure(self) -> None:
        contract = example_contract()
        unowned = "parity_harness/fixtures/example_repo/python/demo/__init__.py"
        result = StructureAuditor().audit_inventory(
            (contract,),
            python_root="parity_harness/fixtures/example_repo/python",
            uncovered_python_files=(unowned,),
            contract_id=contract.contract_id,
        )

        self.assertIn("STR019", {item.code for item in result.findings})
        self.assertNotIn("STR019", COVERAGE_FINDING_CODES)

    def test_unowned_python_file_reports_symbol_based_rust_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rust/src").mkdir(parents=True)
            (root / "python/sample").mkdir(parents=True)
            (root / "rust/Cargo.toml").write_text(
                "[package]\nname='sample'\nversion='0.0.0'\n",
                encoding="utf-8",
            )
            (root / "rust/src/lib.rs").write_text(
                "pub mod child;\n", encoding="utf-8"
            )
            (root / "rust/src/child.rs").write_text(
                "pub fn child_api() {}\n", encoding="utf-8"
            )
            (root / "python/sample/rogue.py").write_text(
                "def child_api(): pass\n", encoding="utf-8"
            )

            result = StructureAuditor(root=root).audit_inventory(
                (),
                rust_root="rust",
                python_root="python/sample",
                uncovered_rust_modules=("crate", "crate::child"),
                uncovered_python_files=("python/sample/rogue.py",),
            )

        finding = next(item for item in result.findings if item.code == "STR019")
        self.assertEqual(finding.metadata["python_symbols"], ["child_api"])
        self.assertEqual(
            finding.metadata["rust_symbol_matches"],
            [
                {
                    "module": "crate::child",
                    "source": "rust/src/child.rs",
                    "symbols": ["child_api"],
                }
            ],
        )

    def test_rust_module_and_use_relationships_are_discovered(self) -> None:
        crate = Path("parity_harness/fixtures/example_repo/rust").resolve()
        modules = {item.name: item for item in discover_rust_modules(crate)}
        self.assertIn("crate", modules)
        self.assertIn("crate::status", modules)
        self.assertIn("status", modules["crate"].declarations)
        self.assertIn("status::render_status", modules["crate"].public_uses)

    def test_workspace_members_are_discovered(self) -> None:
        with ArtifactWorkspace("workspace-") as workspace:
            (workspace / "crate-a").mkdir()
            (workspace / "crate-a" / "Cargo.toml").write_text("[package]\nname='a'\nversion='0.0.0'\n", encoding="utf-8")
            (workspace / "Cargo.toml").write_text("[workspace]\nmembers=['crate-*']\n", encoding="utf-8")
            crates = discover_workspace_crates(workspace)
            self.assertEqual(crates, ((workspace / "crate-a").resolve(),))

    def test_inline_modules_mod_rs_and_cargo_bins_are_discovered_by_coordinate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src" / "nested").mkdir(parents=True)
            (root / "src" / "bin").mkdir(parents=True)
            (root / "Cargo.toml").write_text(
                "[package]\nname='sample'\nversion='0.0.0'\n"
                "[[bin]]\nname='worker'\npath='src/bin/worker.rs'\n",
                encoding="utf-8",
            )
            (root / "src" / "lib.rs").write_text(
                "pub mod nested;\n"
                "pub(crate) mod mentions {\n"
                "    pub(crate) use crate::nested::Item;\n"
                "}\n",
                encoding="utf-8",
            )
            (root / "src" / "nested" / "mod.rs").write_text(
                "pub struct Item;\n",
                encoding="utf-8",
            )
            (root / "src" / "bin" / "worker.rs").write_text(
                "fn main() {}\n",
                encoding="utf-8",
            )

            modules = {item.name: item for item in discover_rust_modules(root)}

        self.assertIn("crate", modules)
        self.assertIn("crate::nested", modules)
        self.assertIn("crate::mentions", modules)
        self.assertIn("bin::worker", modules)
        self.assertIn("crate::nested::Item", modules["crate::mentions"].public_uses)

    def test_explicit_cargo_bin_names_distinguish_custom_main_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src" / "bin" / "setup").mkdir(parents=True)
            (root / "src" / "bin" / "runner").mkdir(parents=True)
            (root / "Cargo.toml").write_text(
                "[package]\nname='sample'\nversion='0.0.0'\n"
                "[[bin]]\nname='setup-tool'\npath='src/bin/setup/main.rs'\n"
                "[[bin]]\nname='command-runner'\npath='src/bin/runner/main.rs'\n",
                encoding="utf-8",
            )
            (root / "src" / "bin" / "setup" / "main.rs").write_text(
                "mod win;\nfn main() {}\n",
                encoding="utf-8",
            )
            (root / "src" / "bin" / "setup" / "win.rs").write_text(
                "pub fn setup() {}\n",
                encoding="utf-8",
            )
            (root / "src" / "bin" / "runner" / "main.rs").write_text(
                "mod win;\nfn main() {}\n",
                encoding="utf-8",
            )
            (root / "src" / "bin" / "runner" / "win.rs").write_text(
                "pub fn run() {}\n",
                encoding="utf-8",
            )

            modules = discover_rust_modules(root)
            coordinates = [item.name for item in modules]

        self.assertEqual(
            coordinates,
            [
                "bin::command-runner",
                "bin::command-runner::win",
                "bin::setup-tool",
                "bin::setup-tool::win",
            ],
        )

    def test_path_module_uses_declared_coordinate_and_custom_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src" / "client").mkdir(parents=True)
            (root / "Cargo.toml").write_text(
                "[package]\nname='sample'\nversion='0.0.0'\n",
                encoding="utf-8",
            )
            (root / "src" / "lib.rs").write_text(
                "mod client;\n",
                encoding="utf-8",
            )
            (root / "src" / "client.rs").write_text(
                '#[path = "client/http_response_body_stream.rs"]\n'
                "pub(crate) mod response_body_stream;\n",
                encoding="utf-8",
            )
            custom_source = root / "src" / "client" / "http_response_body_stream.rs"
            custom_source.write_text(
                "pub struct HttpResponseBodyStream;\n",
                encoding="utf-8",
            )

            modules = {item.name: item for item in discover_rust_modules(root)}

        child = modules["crate::client::response_body_stream"]
        self.assertEqual(
            Path(child.source).resolve(),
            custom_source.resolve(),
        )
        self.assertIn("HttpResponseBodyStream", child.items)

    def test_test_only_module_container_is_not_a_production_coordinate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src" / "apps").mkdir(parents=True)
            (root / "Cargo.toml").write_text(
                "[package]\nname='sample'\nversion='0.0.0'\n",
                encoding="utf-8",
            )
            (root / "src" / "lib.rs").write_text(
                "mod apps;\n"
                "#[cfg(all(test, target_os = \"windows\"))]\n"
                "mod windows_tests { fn helper() {} }\n"
                "#[cfg(any(not(debug_assertions), test))]\n"
                "mod release_or_test { fn helper() {} }\n",
                encoding="utf-8",
            )
            (root / "src" / "apps" / "mod.rs").write_text(
                "#[cfg(test)]\nmod render;\n",
                encoding="utf-8",
            )
            (root / "src" / "apps" / "render.rs").write_text(
                "pub fn test_helper() {}\n",
                encoding="utf-8",
            )

            modules = {item.name for item in discover_rust_modules(root)}

        self.assertIn("crate", modules)
        self.assertNotIn("crate::apps", modules)
        self.assertNotIn("crate::apps::render", modules)
        self.assertNotIn("crate::windows_tests", modules)
        self.assertIn("crate::release_or_test", modules)

    def test_cfg_test_inline_module_with_attributes_and_docs_is_not_production(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir(parents=True)
            (root / "Cargo.toml").write_text(
                "[package]\nname='sample'\nversion='0.0.0'\n",
                encoding="utf-8",
            )
            (root / "src/lib.rs").write_text(
                "pub fn production_api() {}\n"
                "#[cfg(test)]\n"
                "#[allow(clippy::items_after_test_module)]\n"
                "/// Test-only helpers.\n"
                "mod tests { fn helper() {} }\n",
                encoding="utf-8",
            )

            modules = {item.name for item in discover_rust_modules(root)}

        self.assertEqual(modules, {"crate"})

    def test_cfg_test_symbol_cannot_be_used_as_a_production_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rust/src").mkdir(parents=True)
            (root / "python/sample").mkdir(parents=True)
            (root / "rust/Cargo.toml").write_text(
                "[package]\nname='sample'\nversion='0.0.0'\n",
                encoding="utf-8",
            )
            (root / "rust/src/lib.rs").write_text(
                "pub fn production_api() {}\n"
                "#[cfg(test)]\nfn test_helper() {}\n",
                encoding="utf-8",
            )
            (root / "python/sample/__init__.py").write_text(
                "def test_helper(): pass\n", encoding="utf-8"
            )
            contract = contract_from_dict(
                {
                    "contract_id": "sample.test-only-anchor",
                    "evidence_status": "mapped",
                    "rust": {
                        "workspace": "rust",
                        "crate": "sample",
                        "module": "crate",
                        "source": "rust/src/lib.rs",
                        "anchors": ["test_helper"],
                        "baseline_commit": "1" * 40,
                    },
                    "python": {
                        "owner": "python/sample/__init__.py",
                        "layout": "module-package",
                        "implementation_files": ["python/sample/__init__.py"],
                        "anchors": ["test_helper"],
                    },
                    "checks": {"structure": {}},
                },
                source_path=root / "contract.json",
            )
            result = StructureAuditor(root=root).check((contract,))[0]

        self.assertIn("STR007", {item.code for item in result.findings})

    def test_unported_rust_module_cannot_be_reported_as_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rust/src").mkdir(parents=True)
            (root / "python/sample").mkdir(parents=True)
            (root / "rust/Cargo.toml").write_text(
                "[package]\nname='sample'\nversion='0.0.0'\n",
                encoding="utf-8",
            )
            (root / "rust/src/lib.rs").write_text(
                "pub mod missing;\npub fn root_api() {}\n", encoding="utf-8"
            )
            (root / "rust/src/missing.rs").write_text(
                "pub fn missing_api() {}\n", encoding="utf-8"
            )
            (root / "python/sample/__init__.py").write_text(
                "def root_api(): pass\n", encoding="utf-8"
            )
            contract = contract_from_dict(
                {
                    "contract_id": "sample.crate",
                    "evidence_status": "mapped",
                    "rust": {
                        "workspace": "rust",
                        "crate": "sample",
                        "module": "crate",
                        "source": "rust/src/lib.rs",
                        "anchors": ["root_api"],
                        "baseline_commit": "1" * 40,
                    },
                    "python": {
                        "owner": "python/sample/__init__.py",
                        "layout": "module-package",
                        "implementation_files": ["python/sample/__init__.py"],
                        "anchors": ["root_api"],
                    },
                    "checks": {"structure": {}},
                },
                source_path=root / "contract.json",
            )
            result = StructureAuditor(root=root).audit_inventory(
                (contract,), rust_root="rust", python_root="python/sample"
            )

        self.assertEqual(result.verdict, Verdict.FAILED)
        self.assertIn("STR018", {item.code for item in result.findings})

    def test_parent_owner_defining_child_module_item_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rust_root = root / "rust" / "sample"
            python_root = root / "python" / "sample"
            (rust_root / "src" / "parent").mkdir(parents=True)
            python_root.mkdir(parents=True)
            (rust_root / "Cargo.toml").write_text(
                "[package]\nname='sample'\nversion='0.0.0'\n",
                encoding="utf-8",
            )
            (rust_root / "src" / "lib.rs").write_text(
                "pub mod parent;\n",
                encoding="utf-8",
            )
            (rust_root / "src" / "parent.rs").write_text(
                "mod child;\npub fn parent_api() {}\n",
                encoding="utf-8",
            )
            (rust_root / "src" / "parent" / "child.rs").write_text(
                "pub fn child_api() {}\n",
                encoding="utf-8",
            )
            (python_root / "parent.py").write_text(
                "def parent_api(): pass\n\ndef child_api(): pass\n",
                encoding="utf-8",
            )
            contract = contract_from_dict(
                {
                    "contract_id": "sample.parent",
                    "evidence_status": "mapped",
                    "rust": {
                        "workspace": "rust",
                        "crate": "sample",
                        "module": "parent",
                        "source": "rust/sample/src/parent.rs",
                        "anchors": ["parent_api"],
                        "baseline_commit": "1" * 40,
                    },
                    "python": {
                        "owner": "python/sample/parent.py",
                        "layout": "module-file",
                        "implementation_files": ["python/sample/parent.py"],
                        "anchors": ["parent_api"],
                    },
                    "checks": {"structure": {"checker": "structure.owner-and-coordinate"}},
                    "fixture_refs": [],
                },
                source_path=root / "contract.json",
            )

            result = StructureAuditor(root=root).check((contract,))[0]

        self.assertEqual(result.verdict, Verdict.FAILED)
        self.assertIn("STR017", {item.code for item in result.findings})
        finding = next(item for item in result.findings if item.code == "STR017")
        self.assertIn("crate::parent::child", finding.message)
        self.assertIn("rust/sample/src/parent/child.rs", finding.message)
        self.assertEqual(finding.metadata["python_owner"], "python/sample/parent.py")
        self.assertEqual(finding.metadata["symbol"], "child_api")
        self.assertEqual(
            finding.metadata["rust_owners"],
            [
                {
                    "module": "crate::parent::child",
                    "source": "rust/sample/src/parent/child.rs",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
