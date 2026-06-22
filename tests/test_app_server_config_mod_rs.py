from pycodex.app_server import config


def test_config_mod_declares_external_agent_config_child_module():
    # Rust contract: app-server/src/config/mod.rs contains only
    # `pub(crate) mod external_agent_config;`.
    assert config.RUST_MODULE == "codex-app-server/src/config/mod.rs"
    assert config.child_module_names() == ("external_agent_config",)

    child = config.CHILD_MODULES[0]
    assert child.rust_name == "external_agent_config"
    assert child.python_name == "pycodex.app_server.config.external_agent_config"
    assert child.visibility == "pub(crate)"
