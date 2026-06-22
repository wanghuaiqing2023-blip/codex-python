import importlib

import pycodex.state.model as model


PUBLIC_REEXPORTS = {
    "AgentJob": "pycodex.state.model.agent_job",
    "AgentJobCreateParams": "pycodex.state.model.agent_job",
    "AgentJobItem": "pycodex.state.model.agent_job",
    "AgentJobItemCreateParams": "pycodex.state.model.agent_job",
    "AgentJobItemStatus": "pycodex.state.model.agent_job",
    "AgentJobProgress": "pycodex.state.model.agent_job",
    "AgentJobStatus": "pycodex.state.model.agent_job",
    "BackfillState": "pycodex.state.model.backfill_state",
    "BackfillStatus": "pycodex.state.model.backfill_state",
    "DirectionalThreadSpawnEdgeStatus": "pycodex.state.model.graph",
    "LogEntry": "pycodex.state.model.log",
    "LogQuery": "pycodex.state.model.log",
    "LogRow": "pycodex.state.model.log",
    "Phase2JobClaimOutcome": "pycodex.state.model.memories",
    "Stage1JobClaim": "pycodex.state.model.memories",
    "Stage1JobClaimOutcome": "pycodex.state.model.memories",
    "Stage1Output": "pycodex.state.model.memories",
    "Stage1StartupClaimParams": "pycodex.state.model.memories",
    "ThreadGoal": "pycodex.state.model.thread_goal",
    "ThreadGoalStatus": "pycodex.state.model.thread_goal",
    "Anchor": "pycodex.state.model.thread_metadata",
    "BackfillStats": "pycodex.state.model.thread_metadata",
    "ExtractionOutcome": "pycodex.state.model.thread_metadata",
    "SortDirection": "pycodex.state.model.thread_metadata",
    "SortKey": "pycodex.state.model.thread_metadata",
    "ThreadMetadata": "pycodex.state.model.thread_metadata",
    "ThreadMetadataBuilder": "pycodex.state.model.thread_metadata",
    "ThreadsPage": "pycodex.state.model.thread_metadata",
}


CRATE_PRIVATE_REEXPORTS = {
    "AgentJobItemRow": "pycodex.state.model.agent_job",
    "AgentJobRow": "pycodex.state.model.agent_job",
    "ThreadGoalRow": "pycodex.state.model.thread_goal",
    "ThreadRow": "pycodex.state.model.thread_metadata",
    "anchor_from_item": "pycodex.state.model.thread_metadata",
    "datetime_to_epoch_millis": "pycodex.state.model.thread_metadata",
    "datetime_to_epoch_seconds": "pycodex.state.model.thread_metadata",
    "epoch_millis_to_datetime": "pycodex.state.model.thread_metadata",
}


def test_model_mod_public_reexports_match_rust_surface() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/mod.rs public `pub use` list
    # Behavior contract: the model aggregation module exposes the Rust public
    # model surface from all seven child modules.
    for name, module_name in PUBLIC_REEXPORTS.items():
        child_module = importlib.import_module(module_name)
        assert getattr(model, name) is getattr(child_module, name)
        assert name in model.__all__


def test_model_mod_crate_private_helpers_are_available_for_python_neighbors() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/mod.rs `pub(crate) use` list
    # Behavior contract: row/helper anchors are available to neighboring Python
    # state modules even though Rust keeps them crate-private.
    for name, module_name in CRATE_PRIVATE_REEXPORTS.items():
        child_module = importlib.import_module(module_name)
        assert getattr(model, name) is getattr(child_module, name)
        assert name in model.__all__


def test_model_mod_no_required_rust_reexport_is_missing() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/mod.rs
    # Behavior contract: every Rust public and crate-private aggregation anchor
    # selected for Python parity appears in the package export list.
    required = set(PUBLIC_REEXPORTS) | set(CRATE_PRIVATE_REEXPORTS)

    assert required <= set(model.__all__)
