# codex-client src/custom_ca.rs

Rust source: `codex/codex-rs/codex-client/src/custom_ca.rs`

Python target: `pycodex/codex_client/custom_ca.py`

Status: `complete`

Implemented behavior:

- `CODEX_CA_CERTIFICATE` and `SSL_CERT_FILE` selection, with Codex-specific
  precedence and empty-value ignore semantics.
- User-facing `BuildCustomCaTransportError` variant messages for read,
  invalid-PEM, certificate-registration, client-build, and rustls-registration
  failures.
- Configured CA bundle loading from PEM files.
- Multi-certificate bundles.
- OpenSSL `TRUSTED CERTIFICATE` label normalization and DER first-item trimming
  to discard trailing X509_AUX metadata.
- Well-formed `X509 CRL` PEM sections are ignored.
- DER short-form and long-form outer item length parsing.
- Dependency-light builder hooks for custom-CA reqwest construction, system-root
  construction, and subprocess-test `no_proxy()` behavior.
- Dependency-light rustls config stand-in preserving the `enable_sni` observable
  from the Rust unit test.

Intentional adaptation:

- Rust registers certificates with `reqwest` and `rustls::RootCertStore`; Python
  has no reqwest/rustls equivalent and remains standard-library-first. The
  module therefore exposes parsed DER certificate bytes and injected builder
  hooks that preserve ordering, error mapping, and registration boundaries.
- Real TLS handshake tests from `codex-client/tests/ca_env.rs` remain runtime
  validation debt because they depend on Rust TLS stacks and generated local
  certificates/proxies; they do not leave the module-local custom-CA policy
  contract open.

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_custom_ca_rs -v`
  passed on 2026-06-20 with `15 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `60 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile`
  over all `pycodex/codex_client` modules and Rust-derived codex-client tests
  passed on 2026-06-20.
