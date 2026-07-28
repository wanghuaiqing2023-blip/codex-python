import importlib


def test_http_inline_api_items_have_the_rust_aligned_owner() -> None:
    """Rust source: cloud-tasks-client/src/http.rs::api."""
    http = importlib.import_module("pycodex.cloud_tasks_client.http")
    http_api = importlib.import_module("pycodex.cloud_tasks_client.http.api")

    for name in (
        "attempt_status_from_str",
        "details_path",
        "extract_assistant_messages_from_body",
        "map_task_list_item_to_summary",
        "summarize_patch_for_logging",
    ):
        item = getattr(http_api, name)
        assert item.__module__ == "pycodex.cloud_tasks_client.http.api"
        assert getattr(http, name) is item


def test_http_rs_is_represented_by_one_continuous_python_package() -> None:
    """A Rust module-file may map to one continuous Python package."""
    http = importlib.import_module("pycodex.cloud_tasks_client.http")

    assert http.__file__ is not None
    assert http.__file__.replace("\\", "/").endswith(
        "pycodex/cloud_tasks_client/http/__init__.py"
    )
