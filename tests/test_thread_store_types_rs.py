from __future__ import annotations

from pycodex.protocol import ThreadSource
from pycodex.thread_store import GitInfoPatch, ThreadMetadataPatch, clear_field, is_clear_field


def test_thread_metadata_patch_round_trips_optional_clears() -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/types.rs::thread_metadata_patch_round_trips_optional_clears
    # Contract: clearable ThreadMetadataPatch fields serialize as explicit JSON null and deserialize as present clear requests.
    patch = ThreadMetadataPatch(
        name=clear_field(),
        thread_source=clear_field(),
        agent_nickname=clear_field(),
        agent_role=clear_field(),
        agent_path=clear_field(),
    )

    value = patch.to_mapping()

    assert value["name"] is None
    assert value["thread_source"] is None
    assert value["agent_nickname"] is None
    assert value["agent_role"] is None
    assert value["agent_path"] is None

    decoded = ThreadMetadataPatch.from_mapping(value)
    assert is_clear_field(decoded.name)
    assert is_clear_field(decoded.thread_source)
    assert is_clear_field(decoded.agent_nickname)
    assert is_clear_field(decoded.agent_role)
    assert is_clear_field(decoded.agent_path)


def test_git_info_patch_round_trips_optional_clears() -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/types.rs::git_info_patch_round_trips_optional_clears
    # Contract: nested GitInfoPatch omits absent fields, serializes present values, and preserves explicit clear requests.
    patch = ThreadMetadataPatch(
        git_info=GitInfoPatch(
            sha=None,
            branch="main",
            origin_url=clear_field(),
        )
    )

    value = patch.to_mapping()

    assert value["git_info"] == {"branch": "main", "origin_url": None}

    decoded = ThreadMetadataPatch.from_mapping(value)
    assert decoded.git_info == GitInfoPatch(
        sha=None,
        branch="main",
        origin_url=clear_field(),
    )


def test_thread_metadata_patch_accepts_missing_fields() -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/types.rs::thread_metadata_patch_accepts_missing_fields
    # Contract: missing fields deserialize as omitted no-op patch values and leave the patch empty.
    decoded = ThreadMetadataPatch.from_mapping({})

    assert decoded.is_empty()
    assert decoded.to_mapping() == {}


def test_thread_metadata_patch_merge_uses_presence_semantics() -> None:
    # Rust crate: codex-thread-store
    # Rust module/test: src/types.rs::thread_metadata_patch_merge_uses_presence_semantics
    # Contract: omitted fields leave current values unchanged, present clear requests clear values, and nested git patch fields merge independently.
    current = ThreadMetadataPatch(
        name="old name",
        preview="old preview",
        thread_source=ThreadSource.USER,
        git_info=GitInfoPatch(
            sha="abc123",
            branch="main",
            origin_url=None,
        ),
    )

    merged = current.merge(
        ThreadMetadataPatch(
            name=clear_field(),
            preview=None,
            title="new title",
            thread_source=clear_field(),
            git_info=GitInfoPatch(
                sha=None,
                branch="feature",
                origin_url=clear_field(),
            ),
        )
    )

    assert is_clear_field(merged.name)
    assert merged.preview == "old preview"
    assert merged.title == "new title"
    assert is_clear_field(merged.thread_source)
    assert merged.git_info == GitInfoPatch(
        sha="abc123",
        branch="feature",
        origin_url=clear_field(),
    )
    assert merged.to_mapping()["git_info"] == {
        "sha": "abc123",
        "branch": "feature",
        "origin_url": None,
    }
