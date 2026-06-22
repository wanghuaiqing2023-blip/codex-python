"""Custom CA policy helpers for Rust ``codex-client/src/custom_ca.rs``.

The real Rust module wires parsed certificates into reqwest and rustls.  This
Python port keeps the dependency-light parts exact: environment precedence,
PEM normalization, DER prefix trimming for OpenSSL trusted certificates, and
user-facing error shape.  HTTP/TLS registration remains an injected boundary.
"""

from __future__ import annotations

import base64
import binascii
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, Protocol, Sequence


CODEX_CA_CERT_ENV = "CODEX_CA_CERTIFICATE"
SSL_CERT_FILE_ENV = "SSL_CERT_FILE"
CA_CERT_HINT = (
    "If you set CODEX_CA_CERTIFICATE or SSL_CERT_FILE, ensure it points to a PEM file "
    "containing one or more CERTIFICATE blocks, or unset it to use system roots."
)


class BuildCustomCaTransportError(Exception):
    """Base error mirroring Rust ``BuildCustomCaTransportError`` variants."""

    variant: str


@dataclass
class ReadCaFile(BuildCustomCaTransportError):
    source_env: str
    path: Path
    source: OSError
    variant: str = "ReadCaFile"

    def __str__(self) -> str:
        return (
            f"Failed to read CA certificate file {self.path} selected by {self.source_env}: "
            f"{self.source}. {CA_CERT_HINT}"
        )


@dataclass
class InvalidCaFile(BuildCustomCaTransportError):
    source_env: str
    path: Path
    detail: str
    variant: str = "InvalidCaFile"

    def __str__(self) -> str:
        return (
            f"Failed to load CA certificates from {self.path} selected by {self.source_env}: "
            f"{self.detail}. {CA_CERT_HINT}"
        )


@dataclass
class RegisterCertificate(BuildCustomCaTransportError):
    source_env: str
    path: Path
    certificate_index: int
    source: Exception
    variant: str = "RegisterCertificate"

    def __str__(self) -> str:
        return (
            f"Failed to parse certificate #{self.certificate_index} from {self.path} "
            f"selected by {self.source_env}: {self.source}. {CA_CERT_HINT}"
        )


@dataclass
class BuildClientWithCustomCa(BuildCustomCaTransportError):
    source_env: str
    path: Path
    source: Exception
    variant: str = "BuildClientWithCustomCa"

    def __str__(self) -> str:
        return (
            f"Failed to build HTTP client while using CA bundle from {self.source_env} "
            f"({self.path}): {self.source}"
        )


@dataclass
class BuildClientWithSystemRoots(BuildCustomCaTransportError):
    source: Exception
    variant: str = "BuildClientWithSystemRoots"

    def __str__(self) -> str:
        return f"Failed to build HTTP client while using system root certificates: {self.source}"


@dataclass
class RegisterRustlsCertificate(BuildCustomCaTransportError):
    source_env: str
    path: Path
    certificate_index: int
    source: Exception
    variant: str = "RegisterRustlsCertificate"

    def __str__(self) -> str:
        return (
            f"Failed to register certificate #{self.certificate_index} from {self.path} "
            f"selected by {self.source_env} in rustls root store: {self.source}. {CA_CERT_HINT}"
        )


class EnvSource(Protocol):
    def var(self, key: str) -> Optional[str]: ...


@dataclass(frozen=True)
class MapEnv:
    values: Mapping[str, str]

    def var(self, key: str) -> Optional[str]:
        return self.values.get(key)


class ProcessEnv:
    def var(self, key: str) -> Optional[str]:
        return os.environ.get(key)


@dataclass(frozen=True)
class ConfiguredCaBundle:
    source_env: str
    path: Path

    def load_certificates(self) -> list[bytes]:
        return self.parse_certificates()

    def parse_certificates(self) -> list[bytes]:
        pem_data = self.read_pem_data()
        normalized_pem = NormalizedPem.from_pem_data(self.source_env, self.path, pem_data)
        certificates: list[bytes] = []

        try:
            sections = list(normalized_pem.sections())
        except (NoPemItemsFound, ValueError) as error:
            raise self.pem_parse_error(error) from error

        for section_kind, der in sections:
            if section_kind == "CERTIFICATE":
                cert_der = normalized_pem.certificate_der(der)
                if cert_der is None:
                    raise self.invalid_ca_file(
                        "failed to extract certificate data from TRUSTED CERTIFICATE: "
                        "invalid DER length"
                    )
                certificates.append(bytes(cert_der))
            elif section_kind == "X509 CRL":
                continue

        if not certificates:
            raise self.pem_parse_error(NoPemItemsFound())
        return certificates

    def read_pem_data(self) -> bytes:
        try:
            return self.path.read_bytes()
        except OSError as source:
            raise ReadCaFile(self.source_env, self.path, source) from source

    def pem_parse_error(self, error: Exception) -> InvalidCaFile:
        if isinstance(error, NoPemItemsFound):
            detail = "no certificates found in PEM file"
        else:
            detail = f"failed to parse PEM file: {error}"
        return self.invalid_ca_file(detail)

    def invalid_ca_file(self, detail: object) -> InvalidCaFile:
        return InvalidCaFile(self.source_env, self.path, str(detail))


class NoPemItemsFound(Exception):
    def __str__(self) -> str:
        return "no PEM items found"


@dataclass(frozen=True)
class NormalizedPem:
    contents: str
    trusted_certificate: bool = False

    @classmethod
    def from_pem_data(cls, source_env: str, path: Path, pem_data: bytes) -> "NormalizedPem":
        del source_env, path
        pem = pem_data.decode("utf-8", errors="replace")
        if "TRUSTED CERTIFICATE" in pem:
            return cls(
                pem.replace("BEGIN TRUSTED CERTIFICATE", "BEGIN CERTIFICATE").replace(
                    "END TRUSTED CERTIFICATE", "END CERTIFICATE"
                ),
                trusted_certificate=True,
            )
        return cls(pem)

    def sections(self) -> Iterable[tuple[str, bytes]]:
        found = False
        for match in _PEM_BLOCK_RE.finditer(self.contents):
            found = True
            label = match.group("label")
            end_label = match.group("end_label")
            if label != end_label:
                raise ValueError(f"PEM end label {end_label!r} did not match {label!r}")
            body = re.sub(r"\s+", "", match.group("body"))
            try:
                der = base64.b64decode(body, validate=True)
            except binascii.Error as error:
                raise ValueError(str(error)) from error
            yield label, der
        if not found:
            raise NoPemItemsFound()

    def certificate_der(self, der: bytes) -> Optional[bytes]:
        if not self.trusted_certificate:
            return der
        return first_der_item(der)


_PEM_BLOCK_RE = re.compile(
    r"-----BEGIN (?P<label>[A-Z0-9 ]+)-----\s*"
    r"(?P<body>.*?)"
    r"-----END (?P<end_label>[A-Z0-9 ]+)-----",
    re.DOTALL,
)


def non_empty_path(env_source: EnvSource, key: str) -> Optional[Path]:
    value = env_source.var(key)
    if value is None or value == "":
        return None
    return Path(value)


def configured_ca_bundle(env_source: EnvSource) -> Optional[ConfiguredCaBundle]:
    codex_path = non_empty_path(env_source, CODEX_CA_CERT_ENV)
    if codex_path is not None:
        return ConfiguredCaBundle(CODEX_CA_CERT_ENV, codex_path)
    ssl_path = non_empty_path(env_source, SSL_CERT_FILE_ENV)
    if ssl_path is not None:
        return ConfiguredCaBundle(SSL_CERT_FILE_ENV, ssl_path)
    return None


def first_der_item(der: bytes) -> Optional[bytes]:
    length = der_item_length(der)
    if length is None:
        return None
    return der[:length]


def der_item_length(der: bytes) -> Optional[int]:
    if len(der) < 2:
        return None
    length_octet = der[1]
    if length_octet & 0x80 == 0:
        length = 2 + length_octet
        return length if length <= len(der) else None

    length_octets = length_octet & 0x7F
    if length_octets == 0:
        return None
    length_start = 2
    length_end = length_start + length_octets
    if length_end > len(der):
        return None

    content_length = 0
    for byte in der[length_start:length_end]:
        content_length = content_length * 256 + byte
    length = length_end + content_length
    return length if length <= len(der) else None


@dataclass(frozen=True)
class RustlsClientConfig:
    """Dependency-light stand-in for the Rust ``Arc<ClientConfig>`` result."""

    certificates: tuple[bytes, ...]
    enable_sni: bool = True


class _BuilderLike(Protocol):
    def build(self): ...


def maybe_build_rustls_client_config_with_custom_ca(
    env_source: Optional[EnvSource] = None,
) -> Optional[RustlsClientConfig]:
    bundle = configured_ca_bundle(env_source or ProcessEnv())
    if bundle is None:
        return None
    return RustlsClientConfig(tuple(bundle.load_certificates()))


def build_reqwest_client_with_custom_ca(
    builder: _BuilderLike,
    env_source: Optional[EnvSource] = None,
):
    return build_reqwest_client_with_env(env_source or ProcessEnv(), builder)


def build_reqwest_client_for_subprocess_tests(
    builder: _BuilderLike,
    env_source: Optional[EnvSource] = None,
):
    if hasattr(builder, "no_proxy"):
        builder = builder.no_proxy()
    return build_reqwest_client_with_env(env_source or ProcessEnv(), builder)


def build_reqwest_client_with_env(env_source: EnvSource, builder: _BuilderLike):
    bundle = configured_ca_bundle(env_source)
    if bundle is not None:
        if hasattr(builder, "use_rustls_tls"):
            builder = builder.use_rustls_tls()
        for idx, cert in enumerate(bundle.load_certificates(), start=1):
            try:
                if hasattr(builder, "add_root_certificate"):
                    builder = builder.add_root_certificate(cert)
            except Exception as source:  # pragma: no cover - exercised by tests
                raise RegisterCertificate(bundle.source_env, bundle.path, idx, source) from source
        try:
            return builder.build()
        except Exception as source:
            raise BuildClientWithCustomCa(bundle.source_env, bundle.path, source) from source

    try:
        return builder.build()
    except Exception as source:
        raise BuildClientWithSystemRoots(source) from source


__all__ = [
    "BuildClientWithCustomCa",
    "BuildClientWithSystemRoots",
    "BuildCustomCaTransportError",
    "CA_CERT_HINT",
    "CODEX_CA_CERT_ENV",
    "ConfiguredCaBundle",
    "InvalidCaFile",
    "MapEnv",
    "NormalizedPem",
    "ProcessEnv",
    "ReadCaFile",
    "RegisterCertificate",
    "RegisterRustlsCertificate",
    "RustlsClientConfig",
    "SSL_CERT_FILE_ENV",
    "build_reqwest_client_for_subprocess_tests",
    "build_reqwest_client_with_custom_ca",
    "build_reqwest_client_with_env",
    "configured_ca_bundle",
    "der_item_length",
    "first_der_item",
    "maybe_build_rustls_client_config_with_custom_ca",
    "non_empty_path",
]
