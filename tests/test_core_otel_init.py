import unittest
from pathlib import Path
from types import SimpleNamespace

from pycodex.features import Feature, Features
from pycodex.core.otel_init import (
    OtelConfig,
    OtelExporterKind,
    OtelHttpProtocol,
    OtelTlsConfig,
    build_provider,
    codex_export_filter,
    install_sqlite_telemetry,
    record_process_start,
)


class OtelInitTests(unittest.TestCase):
    def test_build_provider_returns_none_when_all_exporters_disabled(self) -> None:
        config = SimpleNamespace(
            otel=OtelConfig(
                exporter=OtelExporterKind.none(),
                trace_exporter=OtelExporterKind.none(),
                metrics_exporter=OtelExporterKind.none(),
            ),
            analytics_enabled=True,
            features=Features.with_defaults(),
            codex_home=Path("/tmp/codex"),
        )

        self.assertIsNone(build_provider(config, "1.0", None, True))

    def test_build_provider_disables_metrics_when_analytics_disabled(self) -> None:
        config = SimpleNamespace(
            otel=OtelConfig(metrics_exporter=OtelExporterKind.statsig()),
            analytics_enabled=False,
            features=Features.with_defaults(),
            codex_home=Path("/tmp/codex"),
        )

        self.assertIsNone(build_provider(config, "1.0", None, True))

    def test_build_provider_maps_http_exporter_tls_and_runtime_metrics(self) -> None:
        features = Features.with_defaults().enable(Feature.RUNTIME_METRICS)
        config = SimpleNamespace(
            otel=OtelConfig(
                environment="prod",
                exporter=OtelExporterKind.otlp_http(
                    "https://otel.example/v1/logs",
                    headers={"x-api-key": "secret"},
                    protocol=OtelHttpProtocol.BINARY,
                    tls=OtelTlsConfig(ca_certificate=Path("/ca.pem")),
                ),
                trace_exporter=OtelExporterKind.none(),
                metrics_exporter=OtelExporterKind.statsig(),
                span_attributes={"app": "codex"},
                tracestate={"vendor": {"k": "v"}},
            ),
            analytics_enabled=True,
            features=features,
            codex_home=Path("/tmp/codex"),
        )

        provider = build_provider(config, "1.2.3", "custom-service", True, originator="desktop")

        self.assertIsNotNone(provider)
        assert provider is not None
        self.assertEqual(provider.settings.service_name, "custom-service")
        self.assertEqual(provider.settings.service_version, "1.2.3")
        self.assertEqual(provider.settings.exporter.endpoint, "https://otel.example/v1/logs")
        self.assertEqual(provider.settings.exporter.protocol, OtelHttpProtocol.BINARY)
        self.assertTrue(provider.settings.runtime_metrics)
        self.assertEqual(provider.settings.span_attributes, {"app": "codex"})
        self.assertEqual(provider.settings.tracestate, {"vendor": {"k": "v"}})

    def test_build_provider_maps_grpc_exporter_and_originator_service_name(self) -> None:
        config = {
            "otel": {
                "environment": "stage",
                "exporter": {
                    "kind": "otlp-grpc",
                    "endpoint": "https://otel.example:4317",
                    "headers": {"authorization": "token"},
                    "tls": {"client_certificate": "/client.pem", "client_private_key": "/key.pem"},
                },
                "trace_exporter": "none",
                "metrics_exporter": "none",
            },
            "analytics_enabled": None,
            "features": Features.with_defaults(),
            "codex_home": "/tmp/codex",
        }

        provider = build_provider(config, "2.0", None, default_analytics_enabled=False, originator="codex-cli")

        self.assertIsNotNone(provider)
        assert provider is not None
        self.assertEqual(provider.settings.service_name, "codex-cli")
        self.assertEqual(provider.settings.environment, "stage")
        self.assertEqual(provider.settings.exporter.kind, "otlp-grpc")
        self.assertEqual(provider.settings.exporter.headers, {"authorization": "token"})
        self.assertEqual(provider.settings.exporter.tls.client_certificate, Path("/client.pem"))
        self.assertEqual(provider.settings.metrics_exporter.kind, "none")

    def test_codex_export_filter_matches_codex_otel_targets(self) -> None:
        self.assertTrue(codex_export_filter("codex_otel::metrics"))
        self.assertFalse(codex_export_filter("codex_core"))

        class Meta:
            def target(self) -> str:
                return "codex_otel::traces"

        self.assertTrue(codex_export_filter(Meta()))

    def test_process_and_sqlite_telemetry_use_metrics_presence(self) -> None:
        config = {
            "otel": {"metrics_exporter": "statsig"},
            "analytics_enabled": True,
            "codex_home": "/tmp/codex",
        }
        provider = build_provider(config, "1.0", None, True)

        self.assertTrue(record_process_start(provider, "codex"))
        self.assertTrue(install_sqlite_telemetry(provider, "codex"))


if __name__ == "__main__":
    unittest.main()
