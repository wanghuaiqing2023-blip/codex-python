from pycodex.tui.app.loaded_threads import (
    LoadedSubagentThread,
    find_loaded_subagent_threads_for_primary,
    finds_loaded_subagent_tree_for_primary_thread,
    test_thread,
    thread_spawn_parent_thread_id,
    thread_spawn_source,
)


PRIMARY = "00000000-0000-0000-0000-000000000001"
CHILD = "00000000-0000-0000-0000-000000000002"
GRANDCHILD = "00000000-0000-0000-0000-000000000003"
UNRELATED_PARENT = "00000000-0000-0000-0000-000000000004"
UNRELATED_CHILD = "00000000-0000-0000-0000-000000000005"


def test_finds_loaded_subagent_tree_for_primary_thread_matches_rust() -> None:
    # Rust: codex-tui app/loaded_threads.rs
    # Test: finds_loaded_subagent_tree_for_primary_thread
    assert finds_loaded_subagent_tree_for_primary_thread()


def test_invalid_thread_ids_and_non_spawn_sources_are_ignored() -> None:
    # Rust skips invalid ThreadId parsing and non-subagent SessionSource values.
    threads = [
        {"id": "not-a-uuid", "source": thread_spawn_source(PRIMARY)},
        test_thread(CHILD, {"cli": {}}, "Not", "spawned"),
        test_thread(GRANDCHILD, thread_spawn_source(CHILD), "Nested", "worker"),
    ]

    assert find_loaded_subagent_threads_for_primary(threads, PRIMARY) == []


def test_output_is_sorted_by_thread_id_not_input_order() -> None:
    # Rust sorts LoadedSubagentThread values by thread_id.to_string().
    first = "00000000-0000-0000-0000-000000000010"
    second = "00000000-0000-0000-0000-000000000011"
    threads = [
        test_thread(second, thread_spawn_source(PRIMARY), "Second", "worker"),
        test_thread(first, thread_spawn_source(PRIMARY), "First", "worker"),
    ]

    assert find_loaded_subagent_threads_for_primary(threads, PRIMARY) == [
        LoadedSubagentThread(first, "First", "worker"),
        LoadedSubagentThread(second, "Second", "worker"),
    ]


def test_thread_spawn_parent_thread_id_accepts_json_shape_and_rejects_invalid() -> None:
    # Rust reads subAgent.thread_spawn.parent_thread_id from serialized SessionSource.
    assert thread_spawn_parent_thread_id(thread_spawn_source(PRIMARY)) == PRIMARY
    assert (
        thread_spawn_parent_thread_id(
            {"subAgent": {"thread_spawn": {"parent_thread_id": "bad"}}}
        )
        is None
    )
    assert thread_spawn_parent_thread_id({"cli": {}}) is None


def test_dict_and_object_threads_are_supported() -> None:
    # Python semantic model accepts dict/object thread facades for neighboring modules.
    class ObjectThread:
        id = CHILD
        source = thread_spawn_source(PRIMARY)
        agent_nickname = "Obj"
        agent_role = "role"

    threads = [
        {
            "id": GRANDCHILD,
            "source": thread_spawn_source(CHILD),
            "agent_nickname": "Dict",
            "agent_role": "role",
        },
        ObjectThread(),
    ]

    assert find_loaded_subagent_threads_for_primary(threads, PRIMARY) == [
        LoadedSubagentThread(CHILD, "Obj", "role"),
        LoadedSubagentThread(GRANDCHILD, "Dict", "role"),
    ]
