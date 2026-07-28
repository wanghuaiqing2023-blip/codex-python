"""Port of ``codex-client/src/bin/custom_ca_probe.rs``."""

from __future__ import annotations

import os
import ssl
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping

from ..custom_ca import ConfiguredCaBundle
from ..custom_ca import configured_ca_bundle


PROBE_TLS13_ENV = "CODEX_CUSTOM_CA_PROBE_TLS13"
PROBE_PROXY_ENV = "CODEX_CUSTOM_CA_PROBE_PROXY"
PROBE_URL_ENV = "CODEX_CUSTOM_CA_PROBE_URL"


def run_probe(env: Mapping[str, str] | None = None) -> None:
    values = os.environ if env is None else env
    proxy_url = values.get(PROBE_PROXY_ENV)
    target_url = values.get(PROBE_URL_ENV)
    client = build_probe_client(
        proxy_url,
        tls13=PROBE_TLS13_ENV in values,
        env=values,
    )
    if target_url is not None:
        post_probe_request(client, target_url)


def build_probe_client(
    proxy_url: str | None,
    *,
    tls13: bool = False,
    env: Mapping[str, str] | None = None,
) -> urllib.request.OpenerDirector:
    bundle = configured_ca_bundle(_MappingEnv(os.environ if env is None else env))
    context = _probe_ssl_context(bundle)
    if tls13:
        context.minimum_version = ssl.TLSVersion.TLSv1_3

    proxy_handler = (
        urllib.request.ProxyHandler({"https": proxy_url})
        if proxy_url is not None
        else urllib.request.ProxyHandler({})
    )
    return urllib.request.build_opener(
        proxy_handler,
        urllib.request.HTTPSHandler(context=context),
    )


def post_probe_request(client: urllib.request.OpenerDirector, url: str) -> None:
    request = urllib.request.Request(
        url,
        data=b"grant_type=authorization_code&code=test",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with client.open(request, timeout=5) as response:
            status = response.status
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        status = error.code
        body = error.read().decode("utf-8", errors="replace")
    except BaseException as error:
        raise RuntimeError(f"probe request failed: {error!r}") from error

    if not 200 <= status <= 299:
        raise RuntimeError(f"probe request returned {status}: {body}")
    if body != "ok":
        raise RuntimeError(f"probe response body mismatch: {body}")


def main() -> int:
    try:
        run_probe()
    except BaseException as error:
        print(error, file=sys.stderr)
        return 1
    print("ok")
    return 0


class _MappingEnv:
    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = values

    def var(self, key: str) -> str | None:
        return self._values.get(key)


def _probe_ssl_context(bundle: ConfiguredCaBundle | None) -> ssl.SSLContext:
    if bundle is None:
        return ssl.create_default_context()
    bundle.load_certificates()
    return ssl.create_default_context(cafile=str(bundle.path))


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "PROBE_PROXY_ENV",
    "PROBE_TLS13_ENV",
    "PROBE_URL_ENV",
    "build_probe_client",
    "main",
    "post_probe_request",
    "run_probe",
]
