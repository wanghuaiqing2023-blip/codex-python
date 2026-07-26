from __future__ import annotations

import json
import unittest

from parity_harness.contracts.generator import generate_candidate_catalog
from parity_harness.paths import HARNESS_ROOT
from parity_harness.workspace import load_workspace_contract


class CandidateGenerationTests(unittest.TestCase):
    def test_every_active_scope_has_a_nonaccepted_candidate_artifact(self) -> None:
        workspace = load_workspace_contract()
        generated = HARNESS_ROOT / "contracts" / "generated"
        missing: list[str] = []
        invalid: list[str] = []

        for crate in workspace.active:
            path = generated / f"{crate.scope}.candidates.json"
            if not path.is_file():
                missing.append(crate.scope)
                continue
            value = json.loads(path.read_text(encoding="utf-8"))
            if (
                value.get("scope") != crate.scope
                or value.get("evidence_status") != "candidate"
                or value.get("baseline_commit") != workspace.baseline_commit
            ):
                invalid.append(crate.scope)

        self.assertEqual(missing, [])
        self.assertEqual(invalid, [])

    def test_core_candidates_come_only_from_source_inventories(self) -> None:
        catalog = generate_candidate_catalog("core")

        self.assertEqual(catalog["evidence_status"], "candidate")
        self.assertTrue(catalog["generation_policy"]["cargo_graph_is_source"])
        self.assertTrue(catalog["generation_policy"]["python_tree_is_source"])
        self.assertTrue(catalog["generation_policy"]["accepted_contracts_are_not_read"])
        self.assertNotIn("source" + "_manifest", catalog)

    def test_app_server_candidates_cover_the_cargo_production_graph(self) -> None:
        catalog = generate_candidate_catalog("app-server")
        by_module = {item["rust"]["module"]: item for item in catalog["contracts"]}

        self.assertEqual(catalog["summary"]["rust_modules"], 60)
        self.assertEqual(catalog["summary"]["python_files"], 61)
        self.assertIn("crate", by_module)
        self.assertIn("request_processors::turn_processor", by_module)
        self.assertNotIn("config_manager_service_tests", by_module)
        self.assertNotIn("transport_tests", by_module)
        self.assertEqual(
            by_module["analytics_utils"]["python_candidates"][0][
                "anchor_candidates"
            ],
            ["analytics_events_client_from_config"],
        )
        self.assertEqual(
            set(
                by_module["extensions"]["python_candidates"][0][
                    "anchor_candidates"
                ]
            ),
            {
                "app_server_extension_event_sink",
                "emit",
                "guardian_agent_spawner",
                "thread_extensions",
            },
        )

    def test_candidate_coordinates_round_trip_through_accepted_scanner_rules(self) -> None:
        catalog = generate_candidate_catalog("agent-graph-store")
        modules = {item["rust"]["module"] for item in catalog["contracts"]}

        self.assertIn("crate", modules)
        self.assertIn("error", modules)
        self.assertNotIn("crate::error", modules)

    def test_cargo_binary_main_maps_to_python_package_main(self) -> None:
        catalog = generate_candidate_catalog("windows-sandbox")
        by_module = {item["rust"]["module"]: item for item in catalog["contracts"]}

        self.assertEqual(
            by_module["bin::codex-command-runner"]["python_candidates"][0]["owner"],
            "pycodex/windows_sandbox/bin/command_runner/__main__.py",
        )
        self.assertEqual(
            by_module["bin::codex-command-runner::win"]["python_candidates"][0]["owner"],
            "pycodex/windows_sandbox/bin/command_runner/win/__init__.py",
        )
        self.assertEqual(
            by_module["bin::codex-command-runner::win::cwd_junction"][
                "python_candidates"
            ][0]["owner"],
            "pycodex/windows_sandbox/bin/command_runner/win/cwd_junction.py",
        )

    def test_deferred_scope_cannot_fabricate_candidates(self) -> None:
        with self.assertRaisesRegex(ValueError, "deferred scope"):
            generate_candidate_catalog("chatgpt")


if __name__ == "__main__":
    unittest.main()
