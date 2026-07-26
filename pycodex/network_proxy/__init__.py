"""Public API owned by ``codex-network-proxy::lib``."""

from .config import (
    NetworkDomainPermission,
    NetworkMode,
    NetworkProxyConfig,
    host_and_port_from_network_addr,
)
from .mitm_hook import (
    InjectedHeaderConfig,
    MitmHookActionsConfig,
    MitmHookConfig,
    MitmHookMatchConfig,
)
from .network_policy import (
    NetworkDecision,
    NetworkDecisionSource,
    NetworkPolicyDecision,
    NetworkPolicyRequest,
    NetworkPolicyRequestArgs,
    NetworkProtocol,
)
from .policy import normalize_host
from .proxy import (
    ALL_PROXY_ENV_KEYS,
    ALLOW_LOCAL_BINDING_ENV_KEY,
    CODEX_PROXY_GIT_SSH_COMMAND_MARKER,
    DEFAULT_NO_PROXY_VALUE,
    NO_PROXY_ENV_KEYS,
    PROXY_ACTIVE_ENV_KEY,
    PROXY_ENV_KEYS,
    PROXY_GIT_SSH_COMMAND_ENV_KEY,
    PROXY_URL_ENV_KEYS,
    NetworkProxy,
    NetworkProxyBuilder,
    NetworkProxyHandle,
    has_proxy_url_env_vars,
    proxy_url_env_value,
)
from .runtime import (
    BlockedRequest,
    BlockedRequestArgs,
    ConfigState,
    NetworkProxyAuditMetadata,
    NetworkProxyState,
)
from .state import (
    NetworkProxyConstraintError,
    NetworkProxyConstraints,
    build_config_state,
    validate_policy_against_constraints,
)

__all__ = [
    "ALL_PROXY_ENV_KEYS",
    "ALLOW_LOCAL_BINDING_ENV_KEY",
    "BlockedRequest",
    "BlockedRequestArgs",
    "CODEX_PROXY_GIT_SSH_COMMAND_MARKER",
    "ConfigState",
    "DEFAULT_NO_PROXY_VALUE",
    "InjectedHeaderConfig",
    "MitmHookActionsConfig",
    "MitmHookConfig",
    "MitmHookMatchConfig",
    "NO_PROXY_ENV_KEYS",
    "NetworkDecision",
    "NetworkDecisionSource",
    "NetworkDomainPermission",
    "NetworkMode",
    "NetworkPolicyDecision",
    "NetworkPolicyRequest",
    "NetworkPolicyRequestArgs",
    "NetworkProtocol",
    "NetworkProxy",
    "NetworkProxyAuditMetadata",
    "NetworkProxyBuilder",
    "NetworkProxyConfig",
    "NetworkProxyConstraintError",
    "NetworkProxyConstraints",
    "NetworkProxyHandle",
    "NetworkProxyState",
    "PROXY_ACTIVE_ENV_KEY",
    "PROXY_ENV_KEYS",
    "PROXY_GIT_SSH_COMMAND_ENV_KEY",
    "PROXY_URL_ENV_KEYS",
    "build_config_state",
    "has_proxy_url_env_vars",
    "host_and_port_from_network_addr",
    "normalize_host",
    "proxy_url_env_value",
    "validate_policy_against_constraints",
]
