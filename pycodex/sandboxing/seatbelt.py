"""macOS Seatbelt policy argv generation for ``codex-sandboxing``.

Rust counterpart: ``codex-rs/sandboxing/src/seatbelt.rs``.

The module mirrors the Rust command-argument and policy-generation helpers
without invoking ``sandbox-exec``.  Path handling intentionally treats inputs as
macOS/POSIX paths even when this Python port is developed on Windows.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from os import PathLike, fspath
from pathlib import Path
import re
from urllib.parse import urlparse

from pycodex.protocol import (
    FileSystemSandboxPolicy,
    NetworkSandboxPolicy,
    PROTECTED_METADATA_PATH_NAMES,
    SandboxPolicy,
)

MACOS_PATH_TO_SEATBELT_EXECUTABLE = "/usr/bin/sandbox-exec"

PROXY_URL_ENV_KEYS: tuple[str, ...] = (
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
    "YARN_HTTP_PROXY",
    "yarn_http_proxy",
    "YARN_HTTPS_PROXY",
    "yarn_https_proxy",
    "NPM_CONFIG_HTTP_PROXY",
    "npm_config_http_proxy",
    "NPM_CONFIG_HTTPS_PROXY",
    "npm_config_https_proxy",
    "BUNDLE_HTTP_PROXY",
    "bundle_http_proxy",
    "BUNDLE_HTTPS_PROXY",
    "bundle_https_proxy",
    "DOCKER_HTTP_PROXY",
    "docker_http_proxy",
    "DOCKER_HTTPS_PROXY",
    "docker_https_proxy",
)

MACOS_SEATBELT_BASE_POLICY = """(version 1)

; start with closed-by-default
(deny default)

; child processes inherit the policy of their parent
(allow process-exec)
(allow process-fork)
(allow signal (target same-sandbox))

; process-info
(allow process-info* (target same-sandbox))

(allow file-write-data
  (require-all
    (path "/dev/null")
    (vnode-type CHARACTER-DEVICE)))

; sysctls permitted.
(allow sysctl-read
  (sysctl-name "hw.activecpu")
  (sysctl-name "hw.machine")
  (sysctl-name "hw.model")
  (sysctl-name "hw.ncpu")
  (sysctl-name "kern.hostname")
  (sysctl-name "kern.osrelease")
  (sysctl-name "kern.ostype")
  (sysctl-name "kern.osversion")
  (sysctl-name-prefix "net.routetable."))

; Needed for python multiprocessing and common OpenMP runtimes.
(allow ipc-posix-sem)
(allow ipc-posix-shm-read-data
  ipc-posix-shm-write-create
  ipc-posix-shm-write-unlink
  (ipc-posix-name-regex #"^/__KMP_REGISTERED_LIB_[0-9]+$"))

; allow openpty()
(allow pseudo-tty)
(allow file-read* file-write* file-ioctl (literal "/dev/ptmx"))
(allow file-read* file-write*
  (require-all
    (regex #"^/dev/ttys[0-9]+")
    (extension "com.apple.sandbox.pty")))
(allow file-ioctl (regex #"^/dev/ttys[0-9]+"))

; allow readonly user preferences
(allow ipc-posix-shm-read* (ipc-posix-name-prefix "apple.cfprefs."))
(allow mach-lookup
  (global-name "com.apple.cfprefsd.daemon")
  (global-name "com.apple.cfprefsd.agent")
  (local-name "com.apple.cfprefsd.agent"))
(allow user-preference-read)
"""

MACOS_SEATBELT_NETWORK_POLICY = """; when network access is enabled, these policies are added after those in seatbelt_base_policy.sbpl
; proxy-specific allow rules are injected by codex-core based on environment.

; allow only safe AF_SYSTEM sockets used for local platform services.
(allow system-socket
  (require-all
    (socket-domain AF_SYSTEM)
    (socket-protocol 2)
  )
)

(allow mach-lookup
    (global-name "com.apple.bsd.dirhelper")
    (global-name "com.apple.system.opendirectoryd.membership")
    (global-name "com.apple.SecurityServer")
    (global-name "com.apple.networkd")
    (global-name "com.apple.ocspd")
    (global-name "com.apple.trustd.agent")
    (global-name "com.apple.SystemConfiguration.DNSConfiguration")
    (global-name "com.apple.SystemConfiguration.configd")
)

(allow sysctl-read
  (sysctl-name-regex #"^net.routetable")
)
"""

MACOS_RESTRICTED_READ_ONLY_PLATFORM_DEFAULTS = """; macOS platform defaults included when a split filesystem policy requests `:minimal`.
(allow file-read* file-test-existence
  (subpath "/Library/Apple")
  (subpath "/usr/lib")
  (subpath "/usr/share")
  (subpath "/Library/Preferences")
  (subpath "/var/db")
  (subpath "/private/var/db"))

(allow file-map-executable
  (subpath "/System/Library/Frameworks")
  (subpath "/System/Library/PrivateFrameworks")
  (subpath "/usr/lib"))

(allow file-read* file-test-existence
  (literal "/")
  (literal "/etc")
  (literal "/tmp")
  (literal "/var")
  (literal "/dev/null")
  (literal "/dev/urandom")
  (subpath "/etc")
  (subpath "/private/etc"))

(allow file-read* file-test-existence file-write* (subpath "/tmp"))
(allow file-read* file-write* (subpath "/private/tmp"))
(allow file-read* file-write* (subpath "/var/tmp"))
(allow file-read* file-write* (subpath "/private/var/tmp"))

(allow mach-lookup
  (global-name "com.apple.cfprefsd.agent")
  (global-name "com.apple.cfprefsd.daemon")
  (global-name "com.apple.logd")
  (global-name "com.apple.trustd")
  (local-name "com.apple.cfprefsd.agent"))

(allow file-read-data (subpath "/bin"))
(allow file-read-metadata (subpath "/bin"))
(allow file-read-data (subpath "/usr/bin"))
(allow file-read-metadata (subpath "/usr/bin"))
(allow file-read-data (subpath "/usr/libexec"))
(allow file-read-metadata (subpath "/usr/libexec"))

; App sandbox extensions
(allow file-read* (extension "com.apple.app-sandbox.read"))
(allow file-read* file-write* (extension "com.apple.app-sandbox.read-write"))
"""


@dataclass(frozen=True)
class UnixDomainSocketPolicy:
    allow_all: bool = False
    allowed: tuple[str, ...] = ()

    @classmethod
    def allow_all_policy(cls) -> "UnixDomainSocketPolicy":
        return cls(allow_all=True)

    @classmethod
    def restricted(cls, allowed: Sequence[str | PathLike[str]] = ()) -> "UnixDomainSocketPolicy":
        return cls(allowed=tuple(path for path in (_normalize_path_for_sandbox(p) for p in allowed) if path))


@dataclass(frozen=True)
class ProxyPolicyInputs:
    ports: tuple[int, ...] = ()
    has_proxy_config: bool = False
    allow_local_binding: bool = False
    unix_domain_socket_policy: UnixDomainSocketPolicy = field(default_factory=UnixDomainSocketPolicy)


@dataclass(frozen=True)
class UnixSocketPathParam:
    index: int
    path: str


@dataclass(frozen=True)
class SeatbeltAccessRoot:
    root: str | PathLike[str]
    excluded_subpaths: tuple[str | PathLike[str], ...] = ()
    protected_metadata_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class CreateSeatbeltCommandArgsParams:
    command: tuple[str, ...] | list[str]
    file_system_sandbox_policy: FileSystemSandboxPolicy
    network_sandbox_policy: NetworkSandboxPolicy = NetworkSandboxPolicy.RESTRICTED
    sandbox_policy_cwd: str | PathLike[str] = "."
    enforce_managed_network: bool = False
    network: object | None = None
    extra_allow_unix_sockets: tuple[str | PathLike[str], ...] | list[str | PathLike[str]] = ()


def is_loopback_host(host: str) -> bool:
    return host.lower() == "localhost" or host in {"127.0.0.1", "::1"}


def proxy_scheme_default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 1080 if scheme in {"socks5", "socks5h", "socks4", "socks4a"} else 80


def proxy_url_env_value(env: Mapping[str, str], key: str) -> str | None:
    if key in env:
        return env[key]
    if key.upper() in env:
        return env[key.upper()]
    if key.lower() in env:
        return env[key.lower()]
    return None


def has_proxy_url_env_vars(env: Mapping[str, str]) -> bool:
    return any((proxy_url_env_value(env, key) or "").strip() for key in PROXY_URL_ENV_KEYS)


def proxy_loopback_ports_from_env(env: Mapping[str, str]) -> tuple[int, ...]:
    ports: set[int] = set()
    for key in PROXY_URL_ENV_KEYS:
        proxy_url = proxy_url_env_value(env, key)
        if proxy_url is None:
            continue
        trimmed = proxy_url.strip()
        if not trimmed:
            continue
        candidate = trimmed if "://" in trimmed else f"http://{trimmed}"
        parsed = urlparse(candidate)
        host = parsed.hostname
        if not host or not is_loopback_host(host):
            continue
        port = parsed.port or proxy_scheme_default_port(parsed.scheme.lower())
        ports.add(port)
    return tuple(sorted(ports))


def proxy_policy_inputs(
    network: object | None,
    extra_allow_unix_sockets: Sequence[str | PathLike[str]] = (),
) -> ProxyPolicyInputs:
    extra_allowed = tuple(path for path in (_normalize_path_for_sandbox(p) for p in extra_allow_unix_sockets) if path)
    if network is None:
        return ProxyPolicyInputs(unix_domain_socket_policy=UnixDomainSocketPolicy.restricted(extra_allowed))

    env: dict[str, str] = {}
    apply_to_env = getattr(network, "apply_to_env", None)
    if callable(apply_to_env):
        apply_to_env(env)
    else:
        for key in ("proxy_url", "http_proxy", "HTTP_PROXY"):
            value = getattr(network, key, None)
            if value:
                env["HTTP_PROXY"] = str(value)
                break

    if _network_bool(network, "dangerously_allow_all_unix_sockets"):
        unix_policy = UnixDomainSocketPolicy.allow_all_policy()
    else:
        allowed_raw = _network_sequence(network, "allow_unix_sockets")
        allowed = tuple(path for path in (_normalize_path_for_sandbox(p) for p in allowed_raw) if path)
        unix_policy = UnixDomainSocketPolicy.restricted((*allowed, *extra_allowed))

    return ProxyPolicyInputs(
        ports=proxy_loopback_ports_from_env(env),
        has_proxy_config=has_proxy_url_env_vars(env),
        allow_local_binding=_network_bool(network, "allow_local_binding"),
        unix_domain_socket_policy=unix_policy,
    )


def unix_socket_path_params(proxy: ProxyPolicyInputs) -> tuple[UnixSocketPathParam, ...]:
    if proxy.unix_domain_socket_policy.allow_all:
        return ()
    paths = tuple(sorted(dict.fromkeys(proxy.unix_domain_socket_policy.allowed)))
    return tuple(UnixSocketPathParam(index, path) for index, path in enumerate(paths))


def unix_socket_path_param_key(index: int) -> str:
    return f"UNIX_SOCKET_PATH_{index}"


def unix_socket_dir_params(proxy: ProxyPolicyInputs) -> tuple[tuple[str, str], ...]:
    return tuple((unix_socket_path_param_key(param.index), param.path) for param in unix_socket_path_params(proxy))


def unix_socket_policy(proxy: ProxyPolicyInputs) -> str:
    socket_params = unix_socket_path_params(proxy)
    if not proxy.unix_domain_socket_policy.allow_all and not socket_params:
        return ""
    lines = ["(allow system-socket (socket-domain AF_UNIX))"]
    if proxy.unix_domain_socket_policy.allow_all:
        lines.append("(allow network-bind (local unix-socket))")
        lines.append("(allow network-outbound (remote unix-socket))")
    else:
        for param in socket_params:
            key = unix_socket_path_param_key(param.index)
            lines.append(f'(allow network-bind (local unix-socket (subpath (param "{key}"))))')
            lines.append(f'(allow network-outbound (remote unix-socket (subpath (param "{key}"))))')
    return "\n".join(lines) + "\n"


def dynamic_network_policy_for_network(
    network_policy: NetworkSandboxPolicy,
    enforce_managed_network: bool,
    proxy: ProxyPolicyInputs,
) -> str:
    has_some_unix_socket_access = proxy.unix_domain_socket_policy.allow_all or bool(proxy.unix_domain_socket_policy.allowed)
    restricted = (
        bool(proxy.ports)
        or proxy.has_proxy_config
        or enforce_managed_network
        or (not network_policy.is_enabled() and has_some_unix_socket_access)
    )
    if restricted:
        policy = []
        if proxy.allow_local_binding:
            policy.extend(
                [
                    "; allow local binding and loopback traffic",
                    '(allow network-bind (local ip "*:*"))',
                    '(allow network-inbound (local ip "localhost:*"))',
                    '(allow network-outbound (remote ip "localhost:*"))',
                ]
            )
        if proxy.allow_local_binding and proxy.ports:
            policy.extend(
                [
                    "; allow DNS lookups while application traffic remains proxy-routed",
                    '(allow network-outbound (remote ip "*:53"))',
                ]
            )
        for port in proxy.ports:
            policy.append(f'(allow network-outbound (remote ip "localhost:{port}"))')
        socket_policy = unix_socket_policy(proxy)
        if socket_policy:
            policy.append("; allow unix domain sockets for local IPC")
            policy.append(socket_policy.rstrip("\n"))
        prefix = "\n".join(policy)
        return f"{prefix}\n{MACOS_SEATBELT_NETWORK_POLICY}" if prefix else MACOS_SEATBELT_NETWORK_POLICY

    if proxy.has_proxy_config or enforce_managed_network:
        return ""
    if network_policy.is_enabled():
        policy = "(allow network-outbound)\n(allow network-inbound)\n"
        socket_policy = unix_socket_policy(proxy)
        if socket_policy:
            policy += "; allow unix domain sockets for local IPC\n" + socket_policy
        return policy + MACOS_SEATBELT_NETWORK_POLICY
    return ""


def dynamic_network_policy(
    sandbox_policy: SandboxPolicy,
    enforce_managed_network: bool,
    proxy: ProxyPolicyInputs,
) -> str:
    network_policy = (
        sandbox_policy.network_access
        if isinstance(sandbox_policy.network_access, NetworkSandboxPolicy)
        else NetworkSandboxPolicy.ENABLED
        if sandbox_policy.has_full_network_access()
        else NetworkSandboxPolicy.RESTRICTED
    )
    return dynamic_network_policy_for_network(network_policy, enforce_managed_network, proxy)


def build_seatbelt_access_policy(
    action: str,
    param_prefix: str,
    roots: Sequence[SeatbeltAccessRoot],
) -> tuple[str, tuple[tuple[str, str], ...]]:
    components: list[str] = []
    params: list[tuple[str, str]] = []
    for index, access_root in enumerate(roots):
        root = _normalize_path_for_sandbox(access_root.root) or _posix_path_string(access_root.root)
        root_param = f"{param_prefix}_{index}"
        params.append((root_param, root))
        excluded = tuple(_normalize_path_for_sandbox(path) or _posix_path_string(path) for path in access_root.excluded_subpaths)
        if not excluded and not access_root.protected_metadata_names:
            components.append(f'(subpath (param "{root_param}"))')
            continue
        require_parts = [f'(subpath (param "{root_param}"))']
        for excluded_index, excluded_subpath in enumerate(excluded):
            excluded_param = f"{param_prefix}_{index}_EXCLUDED_{excluded_index}"
            params.append((excluded_param, excluded_subpath))
            require_parts.append(f'(require-not (literal (param "{excluded_param}")))')
            require_parts.append(f'(require-not (subpath (param "{excluded_param}")))')
        for metadata_name in access_root.protected_metadata_names:
            regex = seatbelt_protected_metadata_name_regex(root, metadata_name).replace('"', '\\"')
            require_parts.append(f'(require-not (regex #"{regex}"))')
        components.append(f"(require-all {' '.join(require_parts)} )")
    if not components:
        return "", ()
    return f"(allow {action}\n{' '.join(components)}\n)", tuple(params)


def seatbelt_protected_metadata_name_regex(root: str | PathLike[str], name: str) -> str:
    root_text = _posix_path_string(root).rstrip("/") or "/"
    escaped_root = re.escape(root_text)
    escaped_name = re.escape(name)
    if root_text == "/":
        return f"^/{escaped_name}(/.*)?$"
    return f"^{escaped_root}/{escaped_name}(/.*)?$"


def protected_metadata_names_for_writable_root(
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    writable_root: object,
    cwd: str | PathLike[str],
) -> tuple[str, ...]:
    names = list(getattr(writable_root, "protected_metadata_names", ()) or ())
    root = getattr(writable_root, "root")
    for name in PROTECTED_METADATA_PATH_NAMES:
        if name in names:
            continue
        if not file_system_sandbox_policy.can_write_path_with_cwd(Path(root) / name, Path(cwd)):
            names.append(name)
    return tuple(names)


def build_seatbelt_unreadable_glob_policy(
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    cwd: str | PathLike[str],
) -> str:
    components: list[str] = []
    for pattern in file_system_sandbox_policy.get_unreadable_globs_with_cwd(Path(cwd)):
        regexes = set()
        regex = seatbelt_regex_for_unreadable_glob(pattern)
        if regex is not None:
            regexes.add(regex)
        canonical = canonicalize_glob_static_prefix_for_sandbox(pattern)
        if canonical is not None:
            regex = seatbelt_regex_for_unreadable_glob(canonical)
            if regex is not None:
                regexes.add(regex)
        for regex in sorted(regexes):
            escaped = regex.replace('"', '\\"')
            components.append(f'(deny file-read* (regex #"{escaped}"))')
            components.append(f'(deny file-write-unlink (regex #"{escaped}"))')
    return "\n".join(components)


def canonicalize_glob_static_prefix_for_sandbox(pattern: str) -> str | None:
    first_glob_index = next((i for i, ch in enumerate(pattern) if ch in "*?[]"), None)
    if first_glob_index is None:
        return _normalize_path_for_sandbox(pattern)
    static_prefix = pattern[:first_glob_index]
    prefix_end = len(static_prefix) - 1 if static_prefix.endswith("/") else static_prefix.rfind("/")
    if prefix_end <= 0:
        return None
    root = _normalize_path_for_sandbox(pattern[:prefix_end])
    if root is None:
        return None
    normalized = f"{root}{pattern[prefix_end:]}"
    return normalized if normalized != pattern else None


def seatbelt_regex_for_unreadable_glob(pattern: str) -> str | None:
    if not pattern:
        return None
    chars = list(pattern)
    regex = ["^"]
    saw_glob = False
    index = 0
    while index < len(chars):
        ch = chars[index]
        if ch == "*":
            saw_glob = True
            if index + 1 < len(chars) and chars[index + 1] == "*":
                index += 2
                if index < len(chars) and chars[index] == "/":
                    index += 1
                    regex.append("(.*/)?")
                else:
                    regex.append(".*")
                continue
            regex.append("[^/]*")
        elif ch == "?":
            saw_glob = True
            regex.append("[^/]")
        elif ch == "[":
            saw_glob = True
            end = index + 1
            class_chars: list[str] = []
            closed = False
            while end < len(chars):
                if chars[end] == "]":
                    closed = True
                    break
                class_chars.append(chars[end])
                end += 1
            if not closed:
                regex.append(r"\[")
            else:
                regex.append("[")
                if class_chars:
                    first, *rest = class_chars
                    if first == "!":
                        regex.append("^")
                    elif first == "^":
                        regex.append(r"\^")
                    else:
                        regex.append(first)
                    regex.extend(r"\\" if item == "\\" else item for item in rest)
                regex.append("]")
                index = end
        elif ch == "]":
            saw_glob = True
            regex.append(r"\]")
        else:
            regex.append(re.escape(ch))
        index += 1
    if not saw_glob:
        regex.append("(/.*)?")
    regex.append("$")
    return "".join(regex)


def create_seatbelt_command_args_for_legacy_policy(
    command: Sequence[str],
    sandbox_policy: SandboxPolicy,
    sandbox_policy_cwd: str | PathLike[str],
    enforce_managed_network: bool = False,
    network: object | None = None,
) -> list[str]:
    file_system_sandbox_policy = FileSystemSandboxPolicy.from_legacy_sandbox_policy_for_cwd(
        sandbox_policy,
        Path(sandbox_policy_cwd),
    )
    network_policy = (
        sandbox_policy.network_access
        if isinstance(sandbox_policy.network_access, NetworkSandboxPolicy)
        else NetworkSandboxPolicy.ENABLED
        if sandbox_policy.has_full_network_access()
        else NetworkSandboxPolicy.RESTRICTED
    )
    return create_seatbelt_command_args(
        CreateSeatbeltCommandArgsParams(
            command=tuple(command),
            file_system_sandbox_policy=file_system_sandbox_policy,
            network_sandbox_policy=network_policy,
            sandbox_policy_cwd=sandbox_policy_cwd,
            enforce_managed_network=enforce_managed_network,
            network=network,
        )
    )


def create_seatbelt_command_args(args: CreateSeatbeltCommandArgsParams) -> list[str]:
    cwd = Path(args.sandbox_policy_cwd)
    fs_policy = args.file_system_sandbox_policy
    unreadable_roots = tuple(Path(root) for root in fs_policy.get_unreadable_roots_with_cwd(cwd))

    if fs_policy.has_full_disk_write_access():
        if unreadable_roots:
            file_write_policy, file_write_dir_params = build_seatbelt_access_policy(
                "file-write*",
                "WRITABLE_ROOT",
                (SeatbeltAccessRoot("/", tuple(unreadable_roots)),),
            )
        else:
            file_write_policy, file_write_dir_params = '(allow file-write* (regex #"^/"))', ()
    else:
        writable_roots = fs_policy.get_writable_roots_with_cwd(cwd)
        file_write_policy, file_write_dir_params = build_seatbelt_access_policy(
            "file-write*",
            "WRITABLE_ROOT",
            tuple(
                SeatbeltAccessRoot(
                    root=getattr(root, "root"),
                    excluded_subpaths=tuple(getattr(root, "read_only_subpaths", ()) or ()),
                    protected_metadata_names=protected_metadata_names_for_writable_root(fs_policy, root, cwd),
                )
                for root in writable_roots
            ),
        )

    if fs_policy.has_full_disk_read_access():
        if unreadable_roots:
            file_read_access, file_read_dir_params = build_seatbelt_access_policy(
                "file-read*",
                "READABLE_ROOT",
                (SeatbeltAccessRoot("/", unreadable_roots),),
            )
            file_read_policy = f"; allow read-only file operations\n{file_read_access}"
        else:
            file_read_policy, file_read_dir_params = "; allow read-only file operations\n(allow file-read*)", ()
    else:
        readable_roots = tuple(Path(root) for root in fs_policy.get_readable_roots_with_cwd(cwd))
        file_read_access, file_read_dir_params = build_seatbelt_access_policy(
            "file-read*",
            "READABLE_ROOT",
            tuple(
                SeatbeltAccessRoot(
                    root=root,
                    excluded_subpaths=tuple(path for path in unreadable_roots if _path_starts_with(path, root)),
                )
                for root in readable_roots
            ),
        )
        file_read_policy = f"; allow read-only file operations\n{file_read_access}" if file_read_access else ""

    proxy = proxy_policy_inputs(args.network, args.extra_allow_unix_sockets)
    network_policy = dynamic_network_policy_for_network(
        args.network_sandbox_policy,
        args.enforce_managed_network,
        proxy,
    )
    deny_read_policy = build_seatbelt_unreadable_glob_policy(fs_policy, cwd)

    sections = [
        MACOS_SEATBELT_BASE_POLICY,
        file_read_policy,
        file_write_policy,
        deny_read_policy,
        network_policy,
    ]
    if fs_policy.include_platform_defaults():
        sections.append(MACOS_RESTRICTED_READ_ONLY_PLATFORM_DEFAULTS)
    full_policy = "\n".join(sections)

    dir_params = (*file_read_dir_params, *file_write_dir_params, *unix_socket_dir_params(proxy))
    seatbelt_args = ["-p", full_policy]
    seatbelt_args.extend(f"-D{key}={value}" for key, value in dir_params)
    seatbelt_args.append("--")
    seatbelt_args.extend(str(part) for part in args.command)
    return seatbelt_args


def _network_bool(network: object, name: str) -> bool:
    value = getattr(network, name, False)
    return bool(value() if callable(value) else value)


def _network_sequence(network: object, name: str) -> tuple[str, ...]:
    value = getattr(network, name, ())
    value = value() if callable(value) else value
    if value is None:
        return ()
    return tuple(str(item) for item in value)


def _normalize_path_for_sandbox(path: str | PathLike[str]) -> str | None:
    text = _posix_path_string(path)
    if not text.startswith("/"):
        return None
    while len(text) > 1 and text.endswith("/"):
        text = text[:-1]
    return text or "/"


def _posix_path_string(path: str | PathLike[str]) -> str:
    text = fspath(path)
    text = text.replace("\\", "/")
    if text.startswith("//"):
        text = "/" + text.lstrip("/")
    return text


def _path_starts_with(path: Path, root: Path) -> bool:
    path_text = _normalize_path_for_sandbox(path) or _posix_path_string(path)
    root_text = _normalize_path_for_sandbox(root) or _posix_path_string(root)
    return path_text == root_text or path_text.startswith(root_text.rstrip("/") + "/")


__all__ = [
    "CreateSeatbeltCommandArgsParams",
    "MACOS_PATH_TO_SEATBELT_EXECUTABLE",
    "MACOS_RESTRICTED_READ_ONLY_PLATFORM_DEFAULTS",
    "MACOS_SEATBELT_BASE_POLICY",
    "MACOS_SEATBELT_NETWORK_POLICY",
    "PROXY_URL_ENV_KEYS",
    "ProxyPolicyInputs",
    "SeatbeltAccessRoot",
    "UnixDomainSocketPolicy",
    "UnixSocketPathParam",
    "build_seatbelt_access_policy",
    "build_seatbelt_unreadable_glob_policy",
    "canonicalize_glob_static_prefix_for_sandbox",
    "create_seatbelt_command_args",
    "create_seatbelt_command_args_for_legacy_policy",
    "dynamic_network_policy",
    "dynamic_network_policy_for_network",
    "has_proxy_url_env_vars",
    "is_loopback_host",
    "protected_metadata_names_for_writable_root",
    "proxy_loopback_ports_from_env",
    "proxy_policy_inputs",
    "proxy_scheme_default_port",
    "proxy_url_env_value",
    "seatbelt_protected_metadata_name_regex",
    "seatbelt_regex_for_unreadable_glob",
    "unix_socket_dir_params",
    "unix_socket_path_param_key",
    "unix_socket_path_params",
    "unix_socket_policy",
]
