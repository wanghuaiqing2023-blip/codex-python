import importlib


def test_cloud_tasks_items_are_owned_by_rust_aligned_modules() -> None:
    """Rust source: cloud-tasks/src/{app,env_detect,util}.rs."""
    app = importlib.import_module("pycodex.cloud_tasks.app")
    env_detect = importlib.import_module("pycodex.cloud_tasks.env_detect")
    util = importlib.import_module("pycodex.cloud_tasks.util")

    assert app.ApplyResultLevel.__module__ == "pycodex.cloud_tasks.app"
    assert env_detect.CodeEnvironment.__module__ == "pycodex.cloud_tasks.env_detect"
    assert (
        env_detect.autodetect_environment_id.__module__
        == "pycodex.cloud_tasks.env_detect"
    )
    assert util.normalize_base_url.__module__ == "pycodex.cloud_tasks.util"
    assert util.build_chatgpt_headers.__module__ == "pycodex.cloud_tasks.util"


def test_cloud_tasks_root_reexports_existing_public_surface() -> None:
    cloud_tasks = importlib.import_module("pycodex.cloud_tasks")
    app = importlib.import_module("pycodex.cloud_tasks.app")
    env_detect = importlib.import_module("pycodex.cloud_tasks.env_detect")
    util = importlib.import_module("pycodex.cloud_tasks.util")

    assert cloud_tasks.ApplyResultLevel is app.ApplyResultLevel
    assert cloud_tasks.CodeEnvironment is env_detect.CodeEnvironment
    assert (
        cloud_tasks.autodetect_environment_id
        is env_detect.autodetect_environment_id
    )
    assert cloud_tasks.normalize_base_url is util.normalize_base_url
