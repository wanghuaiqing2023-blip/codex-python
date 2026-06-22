"""App-server config manager helpers ported from ``config_manager.rs``."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from pycodex.config import (
    CloudRequirementsLoader,
    ConfigLayerStack,
    ConfigLoadOptions,
    LoaderOverrides,
    NoopThreadConfigLoader,
    ThreadConfigLoader,
)
from pycodex.features import feature_for_key

JsonValue = Any
ConfigBuilder = Callable[["ConfigBuildRequest"], Awaitable[Any] | Any]
DefaultConfigLoader = Callable[["ConfigManager"], Awaitable[Any] | Any]
ConfigLayersLoader = Callable[["ConfigLayersLoadRequest"], Awaitable[Any] | Any]
CloudRequirementsFactory = Callable[[Any, str, Path], CloudRequirementsLoader]
ResidencyRequirementSetter = Callable[[Any], None]


class ConfigManagerRuntimeBoundaryError(NotImplementedError):
    """Raised when a concrete Rust runtime dependency has not been injected."""


@dataclass(frozen=True)
class Arg0DispatchPaths:
    codex_self_exe: Path | None = None
    codex_linux_sandbox_exe: Path | None = None
    main_execve_wrapper_exe: Path | None = None


@dataclass(frozen=True)
class ConfigOverrides:
    bypass_hook_trust: bool | None = None
    extras: Mapping[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfigBuildRequest:
    codex_home: Path
    cli_overrides: tuple[tuple[str, JsonValue], ...]
    loader_overrides: LoaderOverrides
    strict_config: bool
    harness_overrides: Any
    fallback_cwd: Path | None
    cloud_requirements: CloudRequirementsLoader
    thread_config_loader: ThreadConfigLoader


@dataclass(frozen=True)
class ConfigLayersLoadRequest:
    codex_home: Path
    cwd: Path | None
    cli_overrides: tuple[tuple[str, JsonValue], ...]
    options: ConfigLoadOptions
    cloud_requirements: CloudRequirementsLoader
    thread_config_loader: ThreadConfigLoader


class ConfigManager:
    """Shared app-server entry point for loading effective Codex config.

    The Rust module coordinates several neighboring crates. Python keeps this
    module's local merge/dispatch behavior concrete and accepts injected
    builders for the heavy config-loading runtime boundaries.
    """

    def __init__(
        self,
        codex_home: Path | str,
        cli_overrides: Sequence[tuple[str, JsonValue]] = (),
        loader_overrides: LoaderOverrides | None = None,
        strict_config: bool = False,
        cloud_requirements: CloudRequirementsLoader | None = None,
        arg0_paths: Arg0DispatchPaths | None = None,
        thread_config_loader: ThreadConfigLoader | None = None,
        *,
        config_builder: ConfigBuilder | None = None,
        default_config_loader: DefaultConfigLoader | None = None,
        config_layers_loader: ConfigLayersLoader | None = None,
        cloud_requirements_factory: CloudRequirementsFactory | None = None,
        residency_requirement_setter: ResidencyRequirementSetter | None = None,
    ) -> None:
        self._codex_home = Path(codex_home)
        self._cli_overrides = _clone_overrides(cli_overrides)
        self._runtime_feature_enablement: dict[str, bool] = {}
        self._loader_overrides = loader_overrides or LoaderOverrides()
        self._strict_config = bool(strict_config)
        self._cloud_requirements = cloud_requirements or CloudRequirementsLoader()
        self._arg0_paths = arg0_paths or Arg0DispatchPaths()
        self._thread_config_loader = thread_config_loader or NoopThreadConfigLoader()
        self._config_builder = config_builder or _missing_config_builder
        self._default_config_loader = default_config_loader or _missing_default_config_loader
        self._config_layers_loader = config_layers_loader or _missing_config_layers_loader
        self._cloud_requirements_factory = cloud_requirements_factory or _default_cloud_requirements_factory
        self._residency_requirement_setter = residency_requirement_setter

    def codex_home(self) -> Path:
        return self._codex_home

    def user_config_path(self) -> Path:
        return self._loader_overrides.user_config_file(self._codex_home)

    def current_cli_overrides(self) -> list[tuple[str, JsonValue]]:
        return _clone_overrides(self._cli_overrides)

    def current_cloud_requirements(self) -> CloudRequirementsLoader:
        return self._cloud_requirements

    def extend_runtime_feature_enablement(self, enablement: Mapping[str, bool] | Sequence[tuple[str, bool]]) -> None:
        items = enablement.items() if isinstance(enablement, Mapping) else enablement
        for key, enabled in items:
            self._runtime_feature_enablement[str(key)] = bool(enabled)

    def replace_cloud_requirements_loader(self, auth_manager: Any, chatgpt_base_url: str) -> None:
        self._cloud_requirements = self._cloud_requirements_factory(
            auth_manager,
            str(chatgpt_base_url),
            self._codex_home,
        )

    def replace_thread_config_loader(self, thread_config_loader: ThreadConfigLoader) -> None:
        self._thread_config_loader = thread_config_loader

    def current_thread_config_loader(self) -> ThreadConfigLoader:
        return self._thread_config_loader or NoopThreadConfigLoader()

    async def sync_default_client_residency_requirement(self) -> None:
        if self._residency_requirement_setter is None:
            return
        try:
            config = await self.load_latest_config(None)
        except Exception:
            return
        self._residency_requirement_setter(_residency_requirement_value(config))

    async def load_latest_config(self, fallback_cwd: Path | str | None = None) -> Any:
        return await self.load_with_cli_overrides(
            self.current_cli_overrides(),
            None,
            ConfigOverrides(),
            Path(fallback_cwd) if fallback_cwd is not None else None,
        )

    async def load_latest_config_for_thread(self, thread_config: Any) -> Any:
        refreshed_config = await self.load_latest_config(Path(_get_attr(thread_config, "cwd")))
        rebuild = getattr(thread_config, "rebuild_preserving_session_layers")
        config = await _maybe_await(rebuild(refreshed_config))
        self.apply_runtime_feature_enablement(config)
        self.apply_arg0_paths(config)
        return config

    async def load_default_config(self) -> Any:
        config = await _maybe_await(self._default_config_loader(self))
        if self._loader_overrides.user_config_path is not None or self._loader_overrides.user_config_profile is not None:
            stack = getattr(config, "config_layer_stack", None)
            with_profile = getattr(stack, "with_user_config_profile", None)
            if callable(with_profile):
                config.config_layer_stack = with_profile(
                    self.user_config_path(),
                    self._loader_overrides.user_config_profile,
                    {},
                )
        self.apply_runtime_feature_enablement(config)
        self.apply_arg0_paths(config)
        return config

    async def load_with_overrides(
        self,
        request_overrides: Mapping[str, JsonValue] | None,
        typesafe_overrides: Any,
    ) -> Any:
        return await self.load_with_cli_overrides(
            self.current_cli_overrides(),
            request_overrides,
            typesafe_overrides,
            None,
        )

    async def load_for_cwd(
        self,
        request_overrides: Mapping[str, JsonValue] | None,
        typesafe_overrides: Any,
        cwd: Path | str | None,
    ) -> Any:
        return await self.load_with_cli_overrides(
            self.current_cli_overrides(),
            request_overrides,
            typesafe_overrides,
            Path(cwd) if cwd is not None else None,
        )

    async def load_with_cli_overrides(
        self,
        cli_overrides: Sequence[tuple[str, JsonValue]],
        request_overrides: Mapping[str, JsonValue] | None,
        typesafe_overrides: Any,
        fallback_cwd: Path | str | None,
    ) -> Any:
        request = dict(request_overrides or {})
        if "bypass_hook_trust" in request:
            bypass_hook_trust = request.pop("bypass_hook_trust")
            if not isinstance(bypass_hook_trust, bool):
                raise ValueError("`bypass_hook_trust` override must be a boolean")
            typesafe_overrides = _with_bypass_hook_trust(typesafe_overrides, bypass_hook_trust)

        merged_cli_overrides = _clone_overrides(cli_overrides)
        merged_cli_overrides.extend((str(key), _json_to_toml(value)) for key, value in request.items())
        build_request = ConfigBuildRequest(
            codex_home=self._codex_home,
            cli_overrides=tuple(merged_cli_overrides),
            loader_overrides=self._loader_overrides,
            strict_config=self._strict_config,
            harness_overrides=typesafe_overrides,
            fallback_cwd=Path(fallback_cwd) if fallback_cwd is not None else None,
            cloud_requirements=self.current_cloud_requirements(),
            thread_config_loader=self.current_thread_config_loader(),
        )
        config = await _maybe_await(self._config_builder(build_request))
        self.apply_runtime_feature_enablement(config)
        self.apply_arg0_paths(config)
        return config

    async def load_config_layers_for_cwd(self, cwd: Path | str) -> Any:
        return await self.load_config_layers(Path(cwd))

    async def load_config_layers(self, cwd: Path | str | None = None) -> Any:
        request = ConfigLayersLoadRequest(
            codex_home=self._codex_home,
            cwd=Path(cwd) if cwd is not None else None,
            cli_overrides=tuple(self.current_cli_overrides()),
            options=ConfigLoadOptions(
                loader_overrides=self._loader_overrides,
                strict_config=self._strict_config,
            ),
            cloud_requirements=self.current_cloud_requirements(),
            thread_config_loader=self.current_thread_config_loader(),
        )
        return await _maybe_await(self._config_layers_loader(request))

    def apply_runtime_feature_enablement(self, config: Any) -> None:
        apply_runtime_feature_enablement(config, self.current_runtime_feature_enablement())

    def current_runtime_feature_enablement(self) -> dict[str, bool]:
        return dict(self._runtime_feature_enablement)

    def apply_arg0_paths(self, config: Any) -> None:
        config.codex_self_exe = self._arg0_paths.codex_self_exe
        config.codex_linux_sandbox_exe = self._arg0_paths.codex_linux_sandbox_exe
        config.main_execve_wrapper_exe = self._arg0_paths.main_execve_wrapper_exe

    @classmethod
    def new_for_tests(
        cls,
        codex_home: Path | str,
        cli_overrides: Sequence[tuple[str, JsonValue]] = (),
        loader_overrides: LoaderOverrides | None = None,
        cloud_requirements: CloudRequirementsLoader | None = None,
        **kwargs: Any,
    ) -> "ConfigManager":
        return cls(
            codex_home,
            cli_overrides,
            loader_overrides or LoaderOverrides(),
            False,
            cloud_requirements or CloudRequirementsLoader(),
            Arg0DispatchPaths(),
            NoopThreadConfigLoader(),
            **kwargs,
        )

    @classmethod
    def without_managed_config_for_tests(cls, codex_home: Path | str, **kwargs: Any) -> "ConfigManager":
        return cls.new_for_tests(
            codex_home,
            (),
            LoaderOverrides.without_managed_config_for_tests(),
            CloudRequirementsLoader(),
            **kwargs,
        )


def protected_feature_keys(config_layer_stack: Any) -> set[str]:
    effective_config = _effective_config(config_layer_stack)
    features = effective_config.get("features") if isinstance(effective_config, Mapping) else None
    protected = {str(key) for key in features} if isinstance(features, Mapping) else set()

    requirements_toml = _requirements_toml(config_layer_stack)
    feature_requirements = _get_optional(requirements_toml, "feature_requirements")
    entries = _get_optional(feature_requirements, "entries")
    if isinstance(entries, Mapping):
        protected.update(str(key) for key in entries)
    return protected


def apply_runtime_feature_enablement(config: Any, runtime_feature_enablement: Mapping[str, bool]) -> None:
    protected_features = protected_feature_keys(_get_attr(config, "config_layer_stack"))
    features = _get_attr(config, "features")
    set_enabled = getattr(features, "set_enabled", None)
    if not callable(set_enabled):
        return
    for name in sorted(runtime_feature_enablement):
        if name in protected_features:
            continue
        feature = feature_for_key(name)
        if feature is None:
            continue
        try:
            set_enabled(feature, bool(runtime_feature_enablement[name]))
        except Exception:
            continue


async def _maybe_await(value: Awaitable[Any] | Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _clone_overrides(overrides: Sequence[tuple[str, JsonValue]]) -> list[tuple[str, JsonValue]]:
    return [(str(key), deepcopy(value)) for key, value in overrides]


def _json_to_toml(value: JsonValue) -> JsonValue:
    return deepcopy(value)


def _with_bypass_hook_trust(typesafe_overrides: Any, bypass_hook_trust: bool) -> Any:
    if isinstance(typesafe_overrides, ConfigOverrides):
        return replace(typesafe_overrides, bypass_hook_trust=bypass_hook_trust)
    if isinstance(typesafe_overrides, Mapping):
        merged = dict(typesafe_overrides)
        merged["bypass_hook_trust"] = bypass_hook_trust
        return merged
    try:
        setattr(typesafe_overrides, "bypass_hook_trust", bypass_hook_trust)
        return typesafe_overrides
    except Exception:
        return ConfigOverrides(bypass_hook_trust=bypass_hook_trust, extras={"source": typesafe_overrides})


def _effective_config(config_layer_stack: Any) -> Mapping[str, JsonValue]:
    effective_config = getattr(config_layer_stack, "effective_config", None)
    if callable(effective_config):
        value = effective_config()
    elif isinstance(config_layer_stack, Mapping):
        value = config_layer_stack.get("effective_config", config_layer_stack)
    else:
        value = getattr(config_layer_stack, "effective_config", {})
    return value if isinstance(value, Mapping) else {}


def _requirements_toml(config_layer_stack: Any) -> Any:
    requirements_toml = getattr(config_layer_stack, "requirements_toml", None)
    if callable(requirements_toml):
        return requirements_toml()
    if isinstance(config_layer_stack, Mapping):
        return config_layer_stack.get("requirements_toml")
    return requirements_toml


def _get_optional(value: Any, key: str) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _get_attr(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value[key]
    return getattr(value, key)


def _residency_requirement_value(config: Any) -> Any:
    enforce_residency = _get_attr(config, "enforce_residency")
    value = getattr(enforce_residency, "value", None)
    return value() if callable(value) else value


def _default_cloud_requirements_factory(_auth_manager: Any, _chatgpt_base_url: str, _codex_home: Path) -> CloudRequirementsLoader:
    return CloudRequirementsLoader()


def _missing_config_builder(_request: ConfigBuildRequest) -> Any:
    raise ConfigManagerRuntimeBoundaryError("ConfigBuilder::build runtime is not ported in pycodex.app_server")


def _missing_default_config_loader(_manager: ConfigManager) -> Any:
    raise ConfigManagerRuntimeBoundaryError(
        "Config::load_default_with_cli_overrides_for_codex_home runtime is not ported in pycodex.app_server"
    )


def _missing_config_layers_loader(_request: ConfigLayersLoadRequest) -> Any:
    raise ConfigManagerRuntimeBoundaryError("load_config_layers_state runtime is not ported in pycodex.app_server")


__all__ = [
    "Arg0DispatchPaths",
    "ConfigBuildRequest",
    "ConfigLayersLoadRequest",
    "ConfigManager",
    "ConfigManagerRuntimeBoundaryError",
    "ConfigOverrides",
    "apply_runtime_feature_enablement",
    "protected_feature_keys",
]
