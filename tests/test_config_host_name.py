import unittest
from unittest.mock import patch

from pycodex.config import host_name
from pycodex.config.host_name import _normalize_fqdn_candidate, _normalize_host_name


class ConfigHostNameTests(unittest.TestCase):
    def tearDown(self) -> None:
        host_name.cache_clear()

    def test_normalize_fqdn_candidate_accepts_dns_qualified_name(self) -> None:
        # Rust crate: codex-config
        # Rust module: src/host_name.rs
        # Rust test: normalize_fqdn_candidate_accepts_dns_qualified_name
        self.assertEqual(
            _normalize_fqdn_candidate("runner-01.ci.example.com"),
            "runner-01.ci.example.com",
        )

    def test_normalize_fqdn_candidate_rejects_short_name(self) -> None:
        # Rust test: normalize_fqdn_candidate_rejects_short_name
        self.assertIsNone(_normalize_fqdn_candidate("runner-01"))

    def test_normalize_fqdn_candidate_trims_trailing_dot_and_normalizes_case(self) -> None:
        # Rust test: normalize_fqdn_candidate_trims_trailing_dot_and_normalizes_case
        self.assertEqual(
            _normalize_fqdn_candidate("RUNNER-01.CI.EXAMPLE.COM."),
            "runner-01.ci.example.com",
        )

    def test_normalize_host_name_trims_trailing_dot_and_rejects_empty(self) -> None:
        # Rust source: normalize_host_name trims whitespace/trailing dots,
        # lowercases, and returns None for an empty result.
        self.assertEqual(_normalize_host_name(" RUNNER-01. "), "runner-01")
        self.assertIsNone(_normalize_host_name(" . "))

    def test_host_name_prefers_fqdn_when_resolver_returns_one(self) -> None:
        # Rust source: compute_host_name prefers a canonical FQDN when local
        # resolution provides a DNS-qualified name.
        with patch("pycodex.config.host_name.socket.gethostname", return_value="Runner-01"), patch(
            "pycodex.config.host_name.socket.getfqdn",
            return_value="Runner-01.CI.Example.Com.",
        ):
            self.assertEqual(host_name(), "runner-01.ci.example.com")
            self.assertEqual(host_name(), "runner-01.ci.example.com")

    def test_host_name_falls_back_to_kernel_hostname_when_fqdn_is_unavailable(self) -> None:
        # Rust source: compute_host_name falls back to the cleaned kernel
        # hostname when canonical FQDN lookup does not yield a qualified name.
        with patch("pycodex.config.host_name.socket.gethostname", return_value=" Runner-01. "), patch(
            "pycodex.config.host_name.socket.getfqdn",
            return_value="runner-01",
        ):
            self.assertEqual(host_name(), "runner-01")

    def test_host_name_returns_none_for_empty_kernel_hostname(self) -> None:
        # Rust source: empty normalized kernel hostname returns None.
        with patch("pycodex.config.host_name.socket.gethostname", return_value=" . "):
            self.assertIsNone(host_name())


if __name__ == "__main__":
    unittest.main()
