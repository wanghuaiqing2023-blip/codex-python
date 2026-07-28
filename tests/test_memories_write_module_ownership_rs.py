import importlib

import pytest


@pytest.mark.parametrize(
    ("module_name", "symbol"),
    [
        ("artifacts", "RAW_MEMORIES_FILENAME"),
        ("control", "clear_memory_roots_contents"),
        ("extension_resources", "RETENTION_DAYS"),
        ("extensions", "seed_extension_instructions"),
        ("extensions.ad_hoc", "seed_instructions"),
        ("extensions.prune", "prune_old_extension_resources"),
        ("guard", "rate_limits_ok"),
        ("guard_limits", "CODEX_LIMIT_ID"),
        ("metrics", "MEMORY_PHASE_ONE_JOBS"),
        ("phase1", "StageOneOutput"),
        ("phase1.job", "run"),
        ("phase1.job.result", "failed"),
        ("phase2", "run"),
        ("phase2.agent", "get_config"),
        ("phase2.job", "claim"),
        ("prompt_blocks", "EXTENSIONS_FOLDER_STRUCTURE"),
        ("prompts", "build_consolidation_prompt"),
        ("runtime", "MemoryStartupContext"),
        ("stage_one", "MODEL"),
        ("stage_two", "MODEL"),
        ("start", "start_memories_startup_task"),
        ("storage", "rebuild_raw_memories_file_from_memories"),
        ("workspace", "prepare_memory_workspace"),
        ("workspace_diff", "FILENAME"),
    ],
)
def test_memories_write_item_has_rust_aligned_owner(
    module_name: str, symbol: str
) -> None:
    """Rust source: codex-memories-write module graph rooted at src/lib.rs."""
    module = importlib.import_module(f"pycodex.memories.write.{module_name}")
    item = getattr(module, symbol)
    if callable(item):
        assert item.__module__ == module.__name__


def test_crate_root_owns_paths_and_reexports_public_surface() -> None:
    root = importlib.import_module("pycodex.memories.write")
    control = importlib.import_module("pycodex.memories.write.control")
    prompts = importlib.import_module("pycodex.memories.write.prompts")

    assert root.memory_root.__module__ == root.__name__
    assert root.clear_memory_roots_contents is control.clear_memory_roots_contents
    assert root.build_consolidation_prompt is prompts.build_consolidation_prompt
