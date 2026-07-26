"""Rust-aligned implementation of codex-cli::marketplace_cmd."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, MutableMapping, TextIO
from urllib.parse import urlparse

from pycodex.core.config.edit import CONFIG_TOML_FILE, read_toml_mapping, write_toml_mapping


def _validate_marketplace_segment(segment: str, kind: str) -> None:
    if not segment:
        raise ValueError(f"invalid {kind}: must not be empty")
    if not all(ch.isascii() and (ch.isalnum() or ch in {"-", "_"}) for ch in segment):
        raise ValueError(
            f"invalid {kind}: only ASCII letters, digits, `_`, and `-` are allowed"
        )


def _plugin_marketplace_name_from_source(source: str) -> str:
    source_path = Path(source).expanduser()
    if source_path.exists():
        if source_path.is_file():
            raise RuntimeError("local marketplace source must be a directory, not a file")
        manifest_path = source_path / ".agents" / "plugins" / "marketplace.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"failed to read marketplace manifest {manifest_path}: {exc}") from exc
            if isinstance(manifest, MutableMapping):
                manifest_name = manifest.get("name")
                if isinstance(manifest_name, str) and manifest_name:
                    try:
                        _validate_marketplace_segment(manifest_name, "marketplace name")
                    except ValueError as exc:
                        raise RuntimeError(str(exc)) from exc
                    return manifest_name
        if source_path.name:
            candidate = source_path.name
            try:
                _validate_marketplace_segment(candidate, "marketplace name")
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
            return candidate

    parsed = urlparse(source)
    if parsed.scheme and parsed.path:
        candidate = Path(parsed.path).name
    elif "/" in source or "\\" in source:
        candidate = Path(source).name
    else:
        candidate = source

    candidate = candidate.rsplit("@", 1)[0]
    if candidate.endswith(".git"):
        candidate = candidate[:-4]
    try:
        _validate_marketplace_segment(candidate or source, "marketplace name")
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    return candidate or source

def _load_marketplace_config(codex_home: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = read_toml_mapping(codex_home / CONFIG_TOML_FILE)
    marketplaces_value = config.get("marketplaces")
    marketplaces: dict[str, Any] = {}
    if isinstance(marketplaces_value, MutableMapping):
        for name, entry in marketplaces_value.items():
            if isinstance(name, str) and isinstance(entry, MutableMapping):
                marketplaces[name] = dict(entry)
    return marketplaces, config

def _write_marketplace_config(codex_home: Path, marketplaces: Mapping[str, Any], config: MutableMapping[str, Any]) -> None:
    if marketplaces:
        config["marketplaces"] = {
            str(name): dict(entry)
            for name, entry in sorted(marketplaces.items(), key=lambda item: str(item[0]))
            if isinstance(entry, MutableMapping)
        }
    else:
        config.pop("marketplaces", None)
    write_toml_mapping(codex_home / CONFIG_TOML_FILE, config)

def _marketplace_config_update(source: str, ref: str | None, sparse: list[str]) -> dict[str, Any]:
    source_path = Path(source).expanduser()
    if source_path.exists():
        if sparse:
            raise RuntimeError("--sparse is only supported for git marketplace sources")
        source_type = "local"
        source_value = str(source_path.resolve())
    else:
        source_type = "git"
        source_value = source

    entry: dict[str, Any] = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source_type": source_type,
        "source": source_value,
    }
    if ref is not None:
        entry["ref"] = ref
    if sparse:
        entry["sparse_paths"] = sparse
    return entry

def _marketplace_root_display(marketplace: str, marketplace_entry: Mapping[str, Any]) -> str:
    try:
        _validate_marketplace_segment(marketplace, "marketplace name")
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    source_value = marketplace_entry.get("source")
    if not isinstance(source_value, str) or not source_value:
        raise RuntimeError(f"`{marketplace}` <invalid source>: configured local marketplace source is missing or empty")
    if marketplace_entry.get("source_type") == "local":
        marketplace_root = Path(source_value)
        _read_marketplace_manifest(marketplace_root)
        return str(marketplace_root)
    return source_value


def run(
    command_args: tuple[str, ...],
    *,
    codex_home: Path,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
            if len(command_args) < 2:
                print("plugin marketplace requires a subcommand.", file=stderr)
                return 2

            market_action = command_args[1]

            if market_action == "list":
                try:
                    marketplaces, _config = _load_marketplace_config(codex_home)
                except OSError as exc:
                    print(f"pycodex: failed to read {CONFIG_TOML_FILE}: {exc}", file=stderr)
                    return 2
                rows: list[tuple[str, str]] = []
                for market, market_entry in sorted(marketplaces.items(), key=lambda item: item[0]):
                    try:
                        root_display = _marketplace_root_display(market, market_entry)
                    except RuntimeError as exc:
                        print(f"pycodex: failed to load marketplace(s): {exc}", file=stderr)
                        return 2
                    rows.append((market, root_display))
                print("MARKETPLACE  ROOT", file=stdout)
                for market, root_display in rows:
                    print(f"{market:<{len('MARKETPLACE')}}  {root_display}", file=stdout)
                return 0

            if market_action == "add":
                if len(command_args) < 3:
                    print("plugin marketplace add requires source.", file=stderr)
                    return 2
                source = command_args[2]
                index = 3
                sparse: list[str] = []
                ref: str | None = None
                while index < len(command_args):
                    arg = command_args[index]
                    if arg == "--ref":
                        ref = command_args[index + 1]
                        index += 2
                        continue
                    if arg == "--sparse":
                        index += 1
                        while index < len(command_args) and not command_args[index].startswith("-"):
                            sparse.append(command_args[index])
                            index += 1
                        continue
                    index += 1
                try:
                    market_name = _plugin_marketplace_name_from_source(source)
                    market_info = _marketplace_config_update(source, ref, sparse)
                except RuntimeError as exc:
                    print(f"pycodex: {exc}", file=stderr)
                    return 2
                try:
                    markets, config = _load_marketplace_config(codex_home)
                    already_added = market_name in markets
                    markets[market_name] = market_info
                    _write_marketplace_config(codex_home, markets, config)
                except OSError as exc:
                    print(f"pycodex: failed to write {CONFIG_TOML_FILE}: {exc}", file=stderr)
                    return 2
                if already_added:
                    print(f"Marketplace '{market_name}' is already added from {source}.", file=stdout)
                else:
                    print(f"Added marketplace '{market_name}' from {source}.", file=stdout)
                return 0

            if market_action == "upgrade":
                if len(command_args) > 3:
                    print("plugin marketplace upgrade accepts at most one marketplace name.", file=stderr)
                    return 2
                try:
                    marketplaces, config = _load_marketplace_config(codex_home)
                except OSError as exc:
                    print(f"pycodex: failed to read {CONFIG_TOML_FILE}: {exc}", file=stderr)
                    return 2
                if len(command_args) == 2:
                    updated = False
                    for market_name, market_entry in marketplaces.items():
                        if isinstance(market_entry, MutableMapping) and market_entry.get("source_type") == "git":
                            market_entry["last_updated"] = datetime.now(timezone.utc).isoformat()
                            updated = True
                    if not updated:
                        print("No configured Git marketplaces to upgrade.", file=stdout)
                        return 0
                    try:
                        _write_marketplace_config(codex_home, marketplaces, config)
                    except OSError as exc:
                        print(f"pycodex: failed to write {CONFIG_TOML_FILE}: {exc}", file=stderr)
                        return 2
                    print("Upgraded all marketplaces.", file=stdout)
                    return 0
                market_name = command_args[2]
                market_entry = marketplaces.get(market_name)
                if not isinstance(market_entry, MutableMapping):
                    print(f"pycodex: marketplace '{market_name}' not found.", file=stderr)
                    return 2
                market_entry["last_updated"] = datetime.now(timezone.utc).isoformat()
                marketplaces[market_name] = market_entry
                try:
                    _write_marketplace_config(codex_home, marketplaces, config)
                except OSError as exc:
                    print(f"pycodex: failed to write {CONFIG_TOML_FILE}: {exc}", file=stderr)
                    return 2
                print(f"Upgraded marketplace '{market_name}'.", file=stdout)
                return 0

            if market_action == "remove":
                if len(command_args) < 3:
                    print("plugin marketplace remove requires marketplace name.", file=stderr)
                    return 2
                if len(command_args) > 3:
                    print("plugin marketplace remove requires marketplace name.", file=stderr)
                    return 2
                market_name = command_args[2]
                try:
                    marketplaces, config = _load_marketplace_config(codex_home)
                except OSError as exc:
                    print(f"pycodex: failed to read {CONFIG_TOML_FILE}: {exc}", file=stderr)
                    return 2
                if not marketplaces.pop(market_name, None):
                    print(f"pycodex: marketplace '{market_name}' not found.", file=stderr)
                    return 2
                try:
                    _write_marketplace_config(codex_home, marketplaces, config)
                except OSError as exc:
                    print(f"pycodex: failed to write {CONFIG_TOML_FILE}: {exc}", file=stderr)
                    return 2
                print(f"Removed marketplace '{market_name}'.", file=stdout)
                return 0

            print(f"plugin marketplace {market_action} is not implemented.", file=stderr)

            return 64
