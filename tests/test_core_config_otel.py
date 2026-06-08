import unittest

from pycodex.core.config.otel import resolve_config
from pycodex.core.otel_init import OtelConfig, OtelExporterKind


class CoreConfigOtelTests(unittest.TestCase):
    def test_resolve_config_applies_rust_defaults(self) -> None:
        # Rust: codex-rs/core/src/config/otel.rs::resolve_config.
        warnings: list[str] = []

        config = resolve_config(None, warnings)

        self.assertFalse(config.log_user_prompt)
        self.assertEqual(config.environment, "dev")
        self.assertEqual(config.exporter, OtelExporterKind.none())
        self.assertEqual(config.trace_exporter, OtelExporterKind.none())
        self.assertEqual(config.metrics_exporter, OtelExporterKind.statsig())
        self.assertEqual(config.span_attributes, {})
        self.assertEqual(config.tracestate, {})
        self.assertEqual(warnings, [])

    def test_trace_exporter_defaults_to_none_even_when_log_exporter_is_configured(self) -> None:
        # Rust: config_tests.rs::load_config_otel_exporter_does_not_implicitly_set_trace_exporter.
        config = resolve_config(
            {
                "exporter": {
                    "kind": "otlp-http",
                    "endpoint": "https://otel.example/v1/logs",
                    "protocol": "json",
                }
            },
            [],
        )

        self.assertEqual(config.exporter.kind, "otlp-http")
        self.assertEqual(config.trace_exporter, OtelExporterKind.none())

    def test_resolve_config_applies_valid_trace_metadata(self) -> None:
        # Rust: config_tests.rs::load_config_applies_otel_trace_metadata.
        config = resolve_config(
            {
                "span_attributes": {"example.trace_attr": "enabled"},
                "tracestate": {"example": {"alpha": "one", "beta": "two"}},
            },
            [],
        )

        self.assertEqual(config.span_attributes, {"example.trace_attr": "enabled"})
        self.assertEqual(config.tracestate, {"example": {"alpha": "one", "beta": "two"}})

    def test_resolve_config_drops_invalid_trace_metadata_entries(self) -> None:
        # Rust: config_tests.rs::load_config_drops_invalid_otel_trace_metadata_entries.
        warnings: list[str] = []

        config = resolve_config(
            {
                "environment": "test",
                "span_attributes": {"": "missing-key", "example.trace_attr": "enabled"},
                "tracestate": {
                    "example": {"alpha": "one", "beta": "two\ntoo"},
                    "bad": {"alpha": "one\ntwo"},
                },
            },
            warnings,
        )

        self.assertEqual(config.environment, "test")
        self.assertEqual(config.span_attributes, {"example.trace_attr": "enabled"})
        self.assertEqual(config.tracestate, {"example": {"alpha": "one"}})
        self.assertTrue(
            any(
                "Ignoring invalid `otel.span_attributes` config" in warning
                and "configured span attribute key must not be empty" in warning
                for warning in warnings
            ),
            warnings,
        )
        self.assertTrue(
            any(
                "Ignoring invalid `otel.tracestate` config" in warning
                and "invalid configured tracestate value for example.beta" in warning
                for warning in warnings
            ),
            warnings,
        )
        self.assertTrue(
            any(
                "Ignoring invalid `otel.tracestate` config" in warning
                and "invalid configured tracestate value for bad.alpha" in warning
                for warning in warnings
            ),
            warnings,
        )

    def test_resolve_config_drops_member_when_combined_tracestate_is_invalid(self) -> None:
        warnings: list[str] = []

        config = resolve_config({"tracestate": {"Example": {"alpha": "one"}}}, warnings)

        self.assertEqual(config.tracestate, {})
        self.assertTrue(
            any(
                "Ignoring invalid `otel.tracestate` config" in warning
                and "invalid configured tracestate: invalid list-member key" in warning
                for warning in warnings
            ),
            warnings,
        )

    def test_resolve_config_accepts_existing_otel_config(self) -> None:
        warnings: list[str] = []
        source = OtelConfig(log_user_prompt=True, environment="prod", span_attributes={"app": "codex"})

        config = resolve_config(source, warnings)

        self.assertTrue(config.log_user_prompt)
        self.assertEqual(config.environment, "prod")
        self.assertEqual(config.span_attributes, {"app": "codex"})
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
