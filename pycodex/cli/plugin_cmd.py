"""Rust-aligned implementation of codex-cli::plugin_cmd."""

from __future__ import annotations

from functools import cmp_to_key
import json
import shutil
from datetime import datetime, timezone
import re
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping, TextIO
from urllib.parse import urlencode, urlparse
from pycodex.core.config.edit import CONFIG_TOML_FILE, read_toml_mapping, write_toml_mapping
from pycodex.utils.home_dir import find_codex_home
from .main.spec import CliParseError
from .marketplace_cmd import _load_marketplace_config

def _find_codex_home() -> Path:
    try:
        return find_codex_home()
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise RuntimeError(f"failed to resolve CODEX_HOME: {exc}") from exc

def parse_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args
    if not args:
        raise CliParseError("plugin requires a subcommand.")

    subcommand = args[0]
    if subcommand not in _PLUGIN_SUBCOMMANDS:
        raise CliParseError(f"Unknown plugin subcommand: {subcommand}")

    remainder = list(args[1:])
    if subcommand == "marketplace":
        if not remainder:
            raise CliParseError("plugin marketplace requires a subcommand.")
        market_subcommand = remainder[0]
        if market_subcommand not in _PLUGIN_MARKETPLACE_SUBCOMMANDS:
            raise CliParseError(f"Unknown plugin marketplace subcommand: {market_subcommand}")
        market_args = remainder[1:]
        if market_subcommand == "list":
            if market_args:
                raise CliParseError("Too many arguments for `plugin marketplace list`.")
            return args
        if market_subcommand == "add":
            if not market_args:
                raise CliParseError("plugin marketplace add requires source.")
            index = 2
            while index < len(remainder):
                arg = remainder[index]
                if arg == "--ref":
                    if index + 1 >= len(remainder):
                        raise CliParseError("Missing value for --ref.")
                    index += 2
                    continue
                if arg == "--sparse":
                    if index + 1 >= len(remainder) or remainder[index + 1].startswith("-"):
                        raise CliParseError("Missing value for --sparse.")
                    index += 2
                    while index < len(remainder) and not remainder[index].startswith("-"):
                        index += 1
                    continue
                if arg.startswith("-"):
                    raise CliParseError(f"Unknown argument for plugin marketplace add: {arg}")
                raise CliParseError(f"Unknown argument for plugin marketplace add: {arg}")
            return args
        if market_subcommand == "upgrade":
            if len(market_args) > 1:
                raise CliParseError("plugin marketplace upgrade accepts at most one marketplace name.")
            return args
        if market_subcommand == "remove":
            if len(market_args) != 1:
                raise CliParseError("plugin marketplace remove requires marketplace name.")
            return args
        return args

    if subcommand in {"add", "remove"}:
        if not remainder:
            raise CliParseError(f"plugin {subcommand} requires <plugin>[@<marketplace>].")
        plugin_selector = remainder[0]
        if plugin_selector.startswith("-"):
            raise CliParseError(f"plugin {subcommand} requires <plugin>[@<marketplace>].")
        if len(remainder) > 3:
            raise CliParseError(f"Too many arguments for `plugin {subcommand}`.")
        if len(remainder) >= 2 and remainder[1] in {"--marketplace", "-m"}:
            if len(remainder) != 3 or remainder[2].startswith("-"):
                raise CliParseError(f"plugin {subcommand} --marketplace requires MARKETPLACE.")
            return args
        if len(remainder) > 1:
            raise CliParseError(f"Unknown argument for plugin {subcommand}: {remainder[1]}")
        return args

    # plugin list
    if subcommand == "list":
        if not remainder:
            return args
        if len(remainder) > 2:
            raise CliParseError("Too many arguments for `plugin list`.")
        if remainder[0] in {"--marketplace", "-m"}:
            if len(remainder) != 2 or remainder[1].startswith("-"):
                raise CliParseError("plugin list --marketplace requires MARKETPLACE.")
            return args
        raise CliParseError(f"Unknown argument for plugin list: {remainder[0]}")

    raise CliParseError(f"Unknown plugin subcommand: {subcommand}")

_PLUGIN_SUBCOMMANDS = {"add", "list", "marketplace", "remove"}

_PLUGIN_MARKETPLACE_SUBCOMMANDS = {"add", "list", "upgrade", "remove"}

_DEFAULT_PLUGIN_VERSION = "local"

def _plugin_key(name: str, marketplace: str) -> str:
    return f"{name}@{marketplace}"

def _validate_plugin_segment(segment: str, kind: str) -> None:
    if not segment:
        raise ValueError(f"invalid {kind}: must not be empty")
    if not all(ch.isascii() and (ch.isalnum() or ch in {"-", "_"}) for ch in segment):
        raise ValueError(f"invalid {kind}: only ASCII letters, digits, `_`, and `-` are allowed")

def _validate_plugin_version_segment(version: str) -> None:
    if not version:
        raise ValueError("invalid plugin version: must not be empty")
    if version in {".", ".."}:
        raise ValueError("invalid plugin version: path traversal is not allowed")
    if not all(ch.isascii() and (ch.isalnum() or ch in {".", "+", "_", "-"}) for ch in version):
        raise ValueError("invalid plugin version: only ASCII letters, digits, `.`, `+`, `_`, and `-` are allowed")

def _version_segment_invalid(version: str) -> bool:
    try:
        _validate_plugin_version_segment(version)
    except ValueError:
        return True
    return False

def _semver_core(version: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", version)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))

def _compare_plugin_versions(left: str, right: str) -> int:
    left_semver = _semver_core(left)
    right_semver = _semver_core(right)
    if left_semver is not None and right_semver is not None:
        return (left_semver > right_semver) - (left_semver < right_semver)
    return (left > right) - (left < right)

def _old_plugin_version_would_stay_active(old_version: str, new_version: str) -> bool:
    return old_version == _DEFAULT_PLUGIN_VERSION or _compare_plugin_versions(old_version, new_version) > 0

def parse_plugin_selection(value: str, explicit_marketplace: str | None) -> tuple[str, str]:
    plugin_name = value
    marketplace = explicit_marketplace
    tail = ""
    if "@" in value:
        head, tail = value.rsplit("@", 1)
        plugin_name = head
        if explicit_marketplace is None and head and tail:
            marketplace = tail
        elif explicit_marketplace is not None and head and tail and tail != explicit_marketplace:
            raise ValueError(
                f"plugin id `{value}` belongs to marketplace `{tail}`, "
                f"but --marketplace specified `{explicit_marketplace}`"
            )
    if explicit_marketplace is None and "@" in value and not tail:
        raise ValueError(f"Invalid plugin selector: {value}")
    if not plugin_name:
        raise ValueError(f"Invalid plugin selector: {value}")
    if marketplace is None:
        raise ValueError("plugin requires --marketplace unless passed as <plugin>@<marketplace>")
    try:
        _validate_plugin_segment(plugin_name, "plugin name")
        _validate_plugin_segment(marketplace, "marketplace name")
    except ValueError as exc:
        if "@" in value and explicit_marketplace is None:
            raise ValueError(f"{exc} in `{value}`") from exc
        raise
    return plugin_name, marketplace





def _load_plugin_config(codex_home: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = read_toml_mapping(codex_home / CONFIG_TOML_FILE)
    plugins_value = config.get("plugins")
    plugins: dict[str, Any] = {}
    if isinstance(plugins_value, MutableMapping):
        for name, entry in plugins_value.items():
            if isinstance(name, str) and isinstance(entry, MutableMapping):
                plugins[name] = dict(entry)
    return plugins, config

def _write_plugin_config(codex_home: Path, plugins: Mapping[str, Any], config: MutableMapping[str, Any]) -> None:
    if plugins:
        config["plugins"] = {
            str(name): dict(entry)
            for name, entry in sorted(plugins.items(), key=lambda item: str(item[0]))
            if isinstance(entry, MutableMapping)
        }
    else:
        config.pop("plugins", None)
    write_toml_mapping(codex_home / CONFIG_TOML_FILE, config)

def _read_marketplace_manifest(marketplace_root: Path) -> Mapping[str, Any]:
    manifest_path = marketplace_root / ".agents" / "plugins" / "marketplace.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise RuntimeError("marketplace root does not contain a supported manifest") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"failed to read marketplace manifest {manifest_path}: {exc}") from exc
    if not isinstance(manifest, MutableMapping):
        raise RuntimeError("marketplace manifest must be an object")
    return manifest

def _find_marketplace_plugin(manifest: Mapping[str, Any], plugin_name: str) -> Mapping[str, Any]:
    try:
        _validate_plugin_segment(plugin_name, "plugin name")
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    plugins = manifest.get("plugins")
    if not isinstance(plugins, list):
        raise RuntimeError("marketplace manifest must contain a plugins array")
    matches = [
        plugin
        for plugin in plugins
        if isinstance(plugin, MutableMapping) and plugin.get("name") == plugin_name
    ]
    if not matches:
        raise RuntimeError("plugin not found in marketplace")
    if len(matches) > 1:
        raise RuntimeError("plugin matched multiple marketplace entries")
    return matches[0]

def _copy_local_marketplace_plugin(
    codex_home: Path,
    marketplace: str,
    plugin_name: str,
    marketplace_entry: Mapping[str, Any],
) -> tuple[str, Path]:
    if marketplace_entry.get("source_type") != "local":
        raise RuntimeError("only local marketplace plugin installation is implemented")
    source_value = marketplace_entry.get("source")
    if not isinstance(source_value, str) or not source_value:
        raise RuntimeError("configured local marketplace source is missing or empty")
    marketplace_root = Path(source_value)
    manifest = _read_marketplace_manifest(marketplace_root)
    plugin = _find_marketplace_plugin(manifest, plugin_name)
    source = plugin.get("source")
    if not isinstance(source, MutableMapping) or source.get("source") != "local":
        raise RuntimeError("only local marketplace plugin sources are implemented")
    plugin_path_value = source.get("path")
    if not isinstance(plugin_path_value, str) or not plugin_path_value:
        raise RuntimeError("local marketplace plugin source path is missing")
    plugin_source = (marketplace_root / plugin_path_value).resolve()
    plugin_manifest_path = plugin_source / ".codex-plugin" / "plugin.json"
    try:
        plugin_manifest = json.loads(plugin_manifest_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise RuntimeError("plugin root does not contain .codex-plugin/plugin.json") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"failed to read plugin manifest {plugin_manifest_path}: {exc}") from exc
    if not isinstance(plugin_manifest, MutableMapping):
        raise RuntimeError("plugin manifest must be an object")
    manifest_name = plugin_manifest.get("name")
    if not isinstance(manifest_name, str) or not manifest_name:
        raise RuntimeError("invalid plugin name: must not be empty")
    try:
        _validate_plugin_segment(manifest_name, "plugin name")
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    if manifest_name != plugin_name:
        raise RuntimeError(f"plugin.json name `{manifest_name}` does not match marketplace plugin name `{plugin_name}`")
    raw_version = plugin_manifest.get("version")
    if raw_version is None:
        version = _DEFAULT_PLUGIN_VERSION
    elif not isinstance(raw_version, str):
        raise RuntimeError("invalid plugin version in plugin.json: expected string")
    else:
        version = raw_version.strip()
        if not version:
            raise RuntimeError("invalid plugin version in plugin.json: must not be blank")
    try:
        _validate_plugin_version_segment(version)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    installed_root = codex_home / "plugins" / "cache" / marketplace / plugin_name / version
    if installed_root.exists():
        shutil.rmtree(installed_root)
    installed_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(plugin_source, installed_root)
    _remove_old_plugin_versions(installed_root.parent, version)
    return version, installed_root

def _remove_old_plugin_versions(target_root: Path, plugin_version: str) -> None:
    if not target_root.is_dir():
        return
    for entry in target_root.iterdir():
        if not entry.is_dir():
            continue
        old_version = entry.name
        if old_version == plugin_version:
            continue
        try:
            _validate_plugin_version_segment(old_version)
        except ValueError:
            continue
        try:
            shutil.rmtree(entry)
        except OSError as exc:
            if _old_plugin_version_would_stay_active(old_version, plugin_version):
                raise RuntimeError(
                    f"failed to activate updated plugin cache version `{plugin_version}` while `{old_version}` remains active"
                ) from exc

def _remove_installed_plugin_cache(codex_home: Path, marketplace: str, plugin_name: str) -> None:
    plugin_cache_root = codex_home / "plugins" / "cache" / marketplace / plugin_name
    if plugin_cache_root.exists():
        shutil.rmtree(plugin_cache_root)


def _plugin_manifest_version(plugin_root: Path) -> str:
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(manifest, MutableMapping):
        return ""
    version = manifest.get("version")
    return version if isinstance(version, str) else ""

def _installed_plugin_version(codex_home: Path, marketplace: str, plugin_name: str) -> str:
    plugin_cache_root = codex_home / "plugins" / "cache" / marketplace / plugin_name
    if not plugin_cache_root.is_dir():
        return ""
    versions = [
        path.name
        for path in plugin_cache_root.iterdir()
        if path.is_dir()
    ]
    versions = [
        version
        for version in versions
        if not _version_segment_invalid(version)
    ]
    if not versions:
        return ""
    if _DEFAULT_PLUGIN_VERSION in versions:
        active_version = _DEFAULT_PLUGIN_VERSION
    else:
        active_version = sorted(versions, key=cmp_to_key(_compare_plugin_versions))[-1]
    active_root = plugin_cache_root / active_version
    return _plugin_manifest_version(active_root) or active_version

def _local_marketplace_plugin_path(marketplace_root: Path, plugin: Mapping[str, Any]) -> Path | None:
    source = plugin.get("source")
    if not isinstance(source, MutableMapping) or source.get("source") != "local":
        return None
    plugin_path_value = source.get("path")
    if not isinstance(plugin_path_value, str) or not plugin_path_value:
        return None
    return (marketplace_root / plugin_path_value).resolve()

def _render_plugin_table_for_marketplace(
    codex_home: Path,
    marketplace: str,
    marketplace_entry: Mapping[str, Any],
    plugin_config: Mapping[str, Any],
    *,
    stdout: TextIO,
) -> bool:
    if marketplace_entry.get("source_type") != "local":
        return False
    source_value = marketplace_entry.get("source")
    if not isinstance(source_value, str) or not source_value:
        raise RuntimeError("configured local marketplace source is missing or empty")
    marketplace_root = Path(source_value)
    manifest = _read_marketplace_manifest(marketplace_root)
    plugins = manifest.get("plugins")
    if not isinstance(plugins, list):
        raise RuntimeError("marketplace manifest must contain a plugins array")

    rows: list[tuple[str, str, str, str]] = []
    for plugin in plugins:
        if not isinstance(plugin, MutableMapping):
            continue
        name = plugin.get("name")
        if not isinstance(name, str) or not name:
            continue
        try:
            _validate_plugin_segment(name, "plugin name")
        except ValueError:
            continue
        plugin_key = _plugin_key(name, marketplace)
        configured = plugin_config.get(plugin_key)
        installed = isinstance(configured, MutableMapping)
        enabled = not isinstance(configured, MutableMapping) or configured.get("enabled", True) is not False
        if installed and enabled:
            status = "installed, enabled"
        elif installed:
            status = "installed, disabled"
        else:
            status = "not installed"
        version = _installed_plugin_version(codex_home, marketplace, name) if installed else ""
        plugin_path = _local_marketplace_plugin_path(marketplace_root, plugin)
        rows.append((plugin_key, status, version, str(plugin_path) if plugin_path is not None else ""))

    plugin_width = max(["PLUGIN".__len__(), *(len(row[0]) for row in rows)] or [len("PLUGIN")])
    status_width = max(["STATUS".__len__(), *(len(row[1]) for row in rows)] or [len("STATUS")])
    version_width = max(["VERSION".__len__(), *(len(row[2]) for row in rows)] or [len("VERSION")])
    path_width = max(["PATH".__len__(), *(len(row[3]) for row in rows)] or [len("PATH")])

    print(f"Marketplace `{marketplace}`", file=stdout)
    print(marketplace_root / ".agents" / "plugins" / "marketplace.json", file=stdout)
    print("", file=stdout)
    print(
        f"{'PLUGIN':<{plugin_width}}  {'STATUS':<{status_width}}  {'VERSION':<{version_width}}  {'PATH':<{path_width}}",
        file=stdout,
    )
    for plugin_key, status, version, path in rows:
        print(
            f"{plugin_key:<{plugin_width}}  {status:<{status_width}}  {version:<{version_width}}  {path:<{path_width}}",
            file=stdout,
        )
    return True

def _run_plugin_action(command_args: tuple[str, ...], *, stdout: TextIO, stderr: TextIO) -> int:
    if not command_args:
        print("Usage: codex plugin [OPTIONS] <SUBCOMMAND>", file=stdout)
        return 0

    if any(arg in {"-h", "--help"} for arg in command_args):
        print(help_text(command_args), file=stdout)
        return 0

    try:
        codex_home = _find_codex_home()
    except RuntimeError as exc:
        print(f"pycodex: {exc}", file=stderr)
        return 2

    subcommand = command_args[0]

    if subcommand in {"add", "remove"}:
        if len(command_args) < 2:
            print(f"plugin {subcommand} requires <plugin>[@<marketplace>].", file=stderr)
            return 2
        selector = command_args[1]
        explicit_marketplace = None
        if len(command_args) == 4 and command_args[2] in {"--marketplace", "-m"}:
            explicit_marketplace = command_args[3]
        try:
            plugin_name, marketplace = parse_plugin_selection(selector, explicit_marketplace)
        except ValueError as exc:
            print(f"pycodex: {exc}", file=stderr)
            return 2
        plugin_key = _plugin_key(plugin_name, marketplace)
        if subcommand == "add":
            try:
                marketplaces, _market_config = _load_marketplace_config(codex_home)
                if marketplace not in marketplaces:
                    print(f"pycodex: plugin `{plugin_name}` was not found in marketplace `{marketplace}`", file=stderr)
                    return 2
                marketplace_entry = marketplaces[marketplace]
                if not isinstance(marketplace_entry, MutableMapping):
                    print(f"pycodex: plugin `{plugin_name}` was not found in marketplace `{marketplace}`", file=stderr)
                    return 2
                try:
                    installed_version, installed_path = _copy_local_marketplace_plugin(
                        codex_home,
                        marketplace,
                        plugin_name,
                        marketplace_entry,
                    )
                except RuntimeError as exc:
                    print(f"pycodex: {exc}", file=stderr)
                    return 2
                plugin_list, config = _load_plugin_config(codex_home)
                plugin_entry = dict(plugin_list.get(plugin_key, {})) if isinstance(plugin_list.get(plugin_key), MutableMapping) else {}
                plugin_entry["enabled"] = True
                plugin_list[plugin_key] = plugin_entry
                _write_plugin_config(codex_home, plugin_list, config)
            except OSError as exc:
                print(f"pycodex: failed to write {CONFIG_TOML_FILE}: {exc}", file=stderr)
                return 2
            print(f"Added plugin `{plugin_name}` from marketplace `{marketplace}`.", file=stdout)
            print(f"Installed plugin root: {installed_path}", file=stdout)
            return 0

        try:
            plugin_list, config = _load_plugin_config(codex_home)
        except OSError as exc:
            print(f"pycodex: failed to read {CONFIG_TOML_FILE}: {exc}", file=stderr)
            return 2
        if plugin_key not in plugin_list:
            print(f"pycodex: plugin '{plugin_name}' not found.", file=stderr)
            return 2
        del plugin_list[plugin_key]
        try:
            _remove_installed_plugin_cache(codex_home, marketplace, plugin_name)
            _write_plugin_config(codex_home, plugin_list, config)
        except OSError as exc:
            print(f"pycodex: failed to write {CONFIG_TOML_FILE}: {exc}", file=stderr)
            return 2
        print(f"Removed plugin `{plugin_name}` from marketplace `{marketplace}`.", file=stdout)
        return 0

    if subcommand == "list":
        try:
            plugin_list, _config = _load_plugin_config(codex_home)
            marketplaces, _market_config = _load_marketplace_config(codex_home)
        except OSError as exc:
            print(f"pycodex: failed to read {CONFIG_TOML_FILE}: {exc}", file=stderr)
            return 2
        selected_marketplace = None
        if len(command_args) == 3 and command_args[1] in {"--marketplace", "-m"}:
            selected_marketplace = command_args[2]
        rendered = False
        matched_marketplaces = [
            (name, entry)
            for name, entry in sorted(marketplaces.items(), key=lambda item: item[0])
            if selected_marketplace is None or name == selected_marketplace
        ]
        try:
            for index, (marketplace, marketplace_entry) in enumerate(matched_marketplaces):
                if index > 0:
                    print("", file=stdout)
                rendered = _render_plugin_table_for_marketplace(
                    codex_home,
                    marketplace,
                    marketplace_entry,
                    plugin_list,
                    stdout=stdout,
                ) or rendered
        except RuntimeError as exc:
            print(f"pycodex: {exc}", file=stderr)
            return 2
        if not rendered:
            if selected_marketplace is not None:
                print(f"No plugins found in marketplace `{selected_marketplace}`.", file=stdout)
            else:
                print("No marketplace plugins found.", file=stdout)
            return 0
        return 0

    print(f"Unrecognized plugin subcommand: {subcommand}", file=stderr)
    return 64


def run_plugin_add(
    command_args: tuple[str, ...],
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    return _run_plugin_action(command_args, stdout=stdout, stderr=stderr)


def run_plugin_list(
    command_args: tuple[str, ...],
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    return _run_plugin_action(command_args, stdout=stdout, stderr=stderr)


def run_plugin_remove(
    command_args: tuple[str, ...],
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    return _run_plugin_action(command_args, stdout=stdout, stderr=stderr)

def help_text(command_args: tuple[str, ...]) -> str:
    positional = [arg for arg in command_args if not arg.startswith("-")]
    if not positional:
        return "\n".join(
            [
                "Manage Codex plugins.",
                "",
                "Usage: codex plugin <COMMAND>",
                "",
                "Commands:",
                "  list                         List configured plugins.",
                "  add <PLUGIN>[@<MARKETPLACE>] Add a plugin.",
                "  remove <PLUGIN>[@<MARKETPLACE>]",
                "                               Remove a plugin.",
                "  marketplace <COMMAND>        Manage plugin marketplaces.",
                "",
                "Options:",
                "  -h, --help                   Show this help message.",
            ]
        )

    subcommand = positional[0]
    if subcommand == "marketplace":
        if len(positional) == 1:
            return "\n".join(
                [
                    "Manage Codex plugin marketplaces.",
                    "",
                    "Usage: codex plugin marketplace <COMMAND>",
                    "",
                    "Commands:",
                    "  list                         List configured marketplaces.",
                    "  add <SOURCE> [--ref REF] [--sparse PATH...]",
                    "                               Add a marketplace from a source.",
                    "  upgrade [MARKETPLACE]        Upgrade one or all marketplaces.",
                    "  remove <MARKETPLACE>         Remove a marketplace.",
                    "",
                    "Options:",
                    "  -h, --help                   Show this help message.",
                ]
            )
        market_subcommand = positional[1]
        if market_subcommand == "add":
            return "\n".join(
                [
                    "Add a Codex plugin marketplace.",
                    "",
                    "Usage: codex plugin marketplace add <SOURCE> [--ref REF] [--sparse PATH...]",
                    "",
                    "Arguments:",
                    "  SOURCE        Local path, repository, or URL for the marketplace source.",
                    "",
                    "Options:",
                    "      --ref REF          Git ref to use for a git marketplace source.",
                    "      --sparse PATH...   Sparse checkout path(s) for git marketplace sources.",
                    "  -h, --help             Show this help message.",
                ]
            )
        if market_subcommand == "list":
            return "Usage: codex plugin marketplace list [--help]"
        if market_subcommand == "upgrade":
            return "Usage: codex plugin marketplace upgrade [MARKETPLACE] [--help]"
        if market_subcommand == "remove":
            return "Usage: codex plugin marketplace remove <MARKETPLACE> [--help]"
        return "Usage: codex plugin marketplace <COMMAND>"

    if subcommand in {"add", "remove"}:
        return "\n".join(
            [
                f"{'Add' if subcommand == 'add' else 'Remove'} a Codex plugin.",
                "",
                f"Usage: codex plugin {subcommand} <PLUGIN>[@<MARKETPLACE>] [--marketplace MARKETPLACE]",
                "",
                "Arguments:",
                "  PLUGIN        Plugin id or name, optionally suffixed with @marketplace.",
                "",
                "Options:",
                "  -m, --marketplace MARKETPLACE",
                "                Select the marketplace explicitly.",
                "  -h, --help    Show this help message.",
            ]
        )
    if subcommand == "list":
        return "\n".join(
            [
                "List configured Codex plugins.",
                "",
                "Usage: codex plugin list [--marketplace MARKETPLACE]",
                "",
                "Options:",
                "  -m, --marketplace MARKETPLACE",
                "                Filter plugins by marketplace.",
                "  -h, --help    Show this help message.",
            ]
        )

    return "Usage: codex plugin"

