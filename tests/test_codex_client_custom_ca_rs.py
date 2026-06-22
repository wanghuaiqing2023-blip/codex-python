import tempfile
import unittest
from pathlib import Path

from pycodex.codex_client.custom_ca import CODEX_CA_CERT_ENV
from pycodex.codex_client.custom_ca import SSL_CERT_FILE_ENV
from pycodex.codex_client.custom_ca import BuildClientWithCustomCa
from pycodex.codex_client.custom_ca import BuildClientWithSystemRoots
from pycodex.codex_client.custom_ca import ConfiguredCaBundle
from pycodex.codex_client.custom_ca import InvalidCaFile
from pycodex.codex_client.custom_ca import MapEnv
from pycodex.codex_client.custom_ca import ReadCaFile
from pycodex.codex_client.custom_ca import RegisterCertificate
from pycodex.codex_client.custom_ca import build_reqwest_client_for_subprocess_tests
from pycodex.codex_client.custom_ca import build_reqwest_client_with_env
from pycodex.codex_client.custom_ca import configured_ca_bundle
from pycodex.codex_client.custom_ca import der_item_length
from pycodex.codex_client.custom_ca import first_der_item
from pycodex.codex_client.custom_ca import maybe_build_rustls_client_config_with_custom_ca


FIXTURES = Path("codex/codex-rs/codex-client/tests/fixtures")
TEST_CERT = FIXTURES / "test-ca.pem"
TEST_INTERMEDIATE = FIXTURES / "test-intermediate.pem"
TRUSTED_TEST_CERT = FIXTURES / "test-ca-trusted.pem"


class FakeBuilder:
    def __init__(self, *, fail_add=None, fail_build=None):
        self.fail_add = fail_add
        self.fail_build = fail_build
        self.used_rustls = False
        self.no_proxy_called = False
        self.certificates = []

    def use_rustls_tls(self):
        self.used_rustls = True
        return self

    def add_root_certificate(self, cert):
        if self.fail_add is not None:
            raise self.fail_add
        self.certificates.append(cert)
        return self

    def no_proxy(self):
        self.no_proxy_called = True
        return self

    def build(self):
        if self.fail_build is not None:
            raise self.fail_build
        return {
            "used_rustls": self.used_rustls,
            "no_proxy_called": self.no_proxy_called,
            "certificate_count": len(self.certificates),
        }


def write_file(directory: Path, name: str, contents: str) -> Path:
    path = directory / name
    path.write_text(contents, encoding="utf-8")
    return path


class CodexClientCustomCaTests(unittest.TestCase):
    def test_ca_path_prefers_codex_env(self):
        # Rust crate/module/test: codex-client/src/custom_ca.rs
        # test ca_path_prefers_codex_env.
        env = MapEnv(
            {
                CODEX_CA_CERT_ENV: "/tmp/codex.pem",
                SSL_CERT_FILE_ENV: "/tmp/fallback.pem",
            }
        )

        bundle = configured_ca_bundle(env)

        self.assertEqual(bundle.path, Path("/tmp/codex.pem"))
        self.assertEqual(bundle.source_env, CODEX_CA_CERT_ENV)

    def test_ca_path_falls_back_to_ssl_cert_file(self):
        # Rust crate/module/test: codex-client/src/custom_ca.rs
        # test ca_path_falls_back_to_ssl_cert_file.
        bundle = configured_ca_bundle(MapEnv({SSL_CERT_FILE_ENV: "/tmp/fallback.pem"}))

        self.assertEqual(bundle.path, Path("/tmp/fallback.pem"))
        self.assertEqual(bundle.source_env, SSL_CERT_FILE_ENV)

    def test_ca_path_ignores_empty_values(self):
        # Rust crate/module/test: codex-client/src/custom_ca.rs
        # test ca_path_ignores_empty_values.
        env = MapEnv({CODEX_CA_CERT_ENV: "", SSL_CERT_FILE_ENV: "/tmp/fallback.pem"})

        bundle = configured_ca_bundle(env)

        self.assertEqual(bundle.path, Path("/tmp/fallback.pem"))

    def test_rustls_config_uses_custom_ca_bundle_when_configured(self):
        # Rust crate/module/test: codex-client/src/custom_ca.rs
        # test rustls_config_uses_custom_ca_bundle_when_configured.
        env = MapEnv({CODEX_CA_CERT_ENV: str(TEST_CERT)})

        config = maybe_build_rustls_client_config_with_custom_ca(env)

        self.assertTrue(config.enable_sni)
        self.assertEqual(len(config.certificates), 1)
        self.assertTrue(config.certificates[0].startswith(b"0"))

    def test_rustls_config_reports_invalid_ca_file(self):
        # Rust crate/module/test: codex-client/src/custom_ca.rs
        # test rustls_config_reports_invalid_ca_file.
        with tempfile.TemporaryDirectory() as temp:
            path = write_file(Path(temp), "empty.pem", "")
            env = MapEnv({CODEX_CA_CERT_ENV: str(path)})

            with self.assertRaises(InvalidCaFile) as caught:
                maybe_build_rustls_client_config_with_custom_ca(env)

        self.assertIn("no certificates found in PEM file", str(caught.exception))
        self.assertIn(CODEX_CA_CERT_ENV, str(caught.exception))
        self.assertIn(SSL_CERT_FILE_ENV, str(caught.exception))

    def test_loads_multi_certificate_bundle(self):
        # Rust crate/integration test: codex-client/tests/ca_env.rs
        # test handles_multi_certificate_bundle.
        with tempfile.TemporaryDirectory() as temp:
            bundle_path = Path(temp) / "bundle.pem"
            bundle_path.write_text(
                TEST_CERT.read_text(encoding="utf-8")
                + "\n"
                + TEST_INTERMEDIATE.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            certs = ConfiguredCaBundle(CODEX_CA_CERT_ENV, bundle_path).load_certificates()

        self.assertEqual(len(certs), 2)
        self.assertNotEqual(certs[0], certs[1])

    def test_accepts_openssl_trusted_certificate_and_trims_aux_der(self):
        # Rust crate/integration test: codex-client/tests/ca_env.rs
        # test accepts_openssl_trusted_certificate.
        trusted = ConfiguredCaBundle(CODEX_CA_CERT_ENV, TRUSTED_TEST_CERT).load_certificates()
        standard = ConfiguredCaBundle(CODEX_CA_CERT_ENV, TEST_CERT).load_certificates()

        self.assertEqual(trusted, standard)

    def test_accepts_bundle_with_crl(self):
        # Rust crate/integration test: codex-client/tests/ca_env.rs
        # test accepts_bundle_with_crl.
        crl = """-----BEGIN X509 CRL-----
MIIBYTBKAgEBMA0GCSqGSIb3DQEBCwUAMBIxEDAOBgNVBAMMB3Rlc3QtY2EXDTI1
MTIxMTIzMTI1MVoXDTI1MTIxMjIzMTI1MVqgDzANMAsGA1UdFAQEAgIDBDANBgkq
hkiG9w0BAQsFAAOCAQEAbG9jYWwtY3JsLWZpeHR1cmU=
-----END X509 CRL-----
"""
        with tempfile.TemporaryDirectory() as temp:
            bundle_path = Path(temp) / "with-crl.pem"
            bundle_path.write_text(TEST_CERT.read_text(encoding="utf-8") + crl, encoding="utf-8")

            certs = ConfiguredCaBundle(CODEX_CA_CERT_ENV, bundle_path).load_certificates()

        self.assertEqual(len(certs), 1)

    def test_rejects_malformed_pem_with_hint(self):
        # Rust crate/integration test: codex-client/tests/ca_env.rs
        # test rejects_malformed_pem_with_hint.
        with tempfile.TemporaryDirectory() as temp:
            path = write_file(
                Path(temp),
                "malformed.pem",
                "-----BEGIN CERTIFICATE-----\nnot base64!\n-----END CERTIFICATE-----\n",
            )

            with self.assertRaises(InvalidCaFile) as caught:
                ConfiguredCaBundle(CODEX_CA_CERT_ENV, path).load_certificates()

        self.assertIn("failed to parse PEM file", str(caught.exception))
        self.assertIn(CODEX_CA_CERT_ENV, str(caught.exception))
        self.assertIn(SSL_CERT_FILE_ENV, str(caught.exception))

    def test_read_error_preserves_read_variant(self):
        # Rust crate/module contract: BuildCustomCaTransportError::ReadCaFile.
        with self.assertRaises(ReadCaFile) as caught:
            ConfiguredCaBundle(CODEX_CA_CERT_ENV, Path("does-not-exist.pem")).load_certificates()

        self.assertIn("Failed to read CA certificate file", str(caught.exception))

    def test_der_item_length_supports_short_and_long_forms(self):
        # Rust crate/module helpers: first_der_item and der_item_length.
        self.assertEqual(der_item_length(b"\x30\x03abcxyz"), 5)
        self.assertEqual(first_der_item(b"\x30\x03abcxyz"), b"\x30\x03abc")
        self.assertEqual(der_item_length(b"\x30\x82\x00\x03abcxyz"), 7)
        self.assertEqual(first_der_item(b"\x30\x82\x00\x03abcxyz"), b"\x30\x82\x00\x03abc")
        self.assertIsNone(der_item_length(b"\x30\x80abc"))
        self.assertIsNone(first_der_item(b"\x30\x05abc"))

    def test_reqwest_builder_registers_custom_ca_and_uses_rustls(self):
        # Rust crate/module contract: build_reqwest_client_with_env custom-CA path.
        builder = FakeBuilder()

        result = build_reqwest_client_with_env(MapEnv({CODEX_CA_CERT_ENV: str(TEST_CERT)}), builder)

        self.assertTrue(result["used_rustls"])
        self.assertEqual(result["certificate_count"], 1)

    def test_reqwest_builder_uses_system_roots_without_env(self):
        # Rust crate/module contract: build_reqwest_client_with_env system-roots path.
        result = build_reqwest_client_with_env(MapEnv({}), FakeBuilder())

        self.assertFalse(result["used_rustls"])
        self.assertEqual(result["certificate_count"], 0)

    def test_reqwest_builder_maps_registration_and_build_errors(self):
        # Rust crate/module contract: RegisterCertificate and build-error variants.
        with self.assertRaises(RegisterCertificate):
            build_reqwest_client_with_env(
                MapEnv({CODEX_CA_CERT_ENV: str(TEST_CERT)}),
                FakeBuilder(fail_add=ValueError("bad cert")),
            )

        with self.assertRaises(BuildClientWithCustomCa):
            build_reqwest_client_with_env(
                MapEnv({CODEX_CA_CERT_ENV: str(TEST_CERT)}),
                FakeBuilder(fail_build=RuntimeError("build custom")),
            )

        with self.assertRaises(BuildClientWithSystemRoots):
            build_reqwest_client_with_env(MapEnv({}), FakeBuilder(fail_build=RuntimeError("build")))

    def test_subprocess_test_builder_disables_proxy_autodetection(self):
        # Rust crate/module contract: build_reqwest_client_for_subprocess_tests calls no_proxy.
        result = build_reqwest_client_for_subprocess_tests(
            FakeBuilder(), MapEnv({CODEX_CA_CERT_ENV: str(TEST_CERT)})
        )

        self.assertTrue(result["no_proxy_called"])
        self.assertTrue(result["used_rustls"])


if __name__ == "__main__":
    unittest.main()
