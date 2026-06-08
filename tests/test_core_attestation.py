import unittest

from pycodex.core.attestation import (
    X_OAI_ATTESTATION_HEADER,
    AttestationContext,
    generate_attestation_header_for_request,
    normalize_attestation_header_value,
)
from pycodex.protocol import ThreadId


class SyncProvider:
    def __init__(self) -> None:
        self.contexts = []

    def header_for_request(self, context: AttestationContext) -> str:
        self.contexts.append(context)
        return "attested"


class AsyncProvider:
    def __init__(self) -> None:
        self.contexts = []

    async def header_for_request(self, context: AttestationContext) -> str:
        self.contexts.append(context)
        return "async-attested"


class NoneProvider:
    def __init__(self) -> None:
        self.contexts = []

    def header_for_request(self, context: AttestationContext) -> None:
        self.contexts.append(context)
        return None


class AttestationTests(unittest.IsolatedAsyncioTestCase):
    def test_header_constant_matches_rust(self) -> None:
        self.assertEqual(X_OAI_ATTESTATION_HEADER, "x-oai-attestation")

    def test_context_requires_thread_id(self) -> None:
        with self.assertRaisesRegex(TypeError, "thread_id must be a ThreadId"):
            AttestationContext("not-a-thread-id")  # type: ignore[arg-type]

    async def test_omits_header_when_flag_disabled(self) -> None:
        provider = SyncProvider()
        thread_id = ThreadId.new()

        result = await generate_attestation_header_for_request(
            include_attestation=False,
            attestation_provider=provider,
            thread_id=thread_id,
        )

        self.assertIsNone(result)
        self.assertEqual(provider.contexts, [])

    async def test_omits_header_without_provider(self) -> None:
        result = await generate_attestation_header_for_request(
            include_attestation=True,
            attestation_provider=None,
            thread_id=ThreadId.new(),
        )

        self.assertIsNone(result)

    async def test_provider_can_decline_to_generate_header(self) -> None:
        # Rust AttestationProvider returns Future<Output = Option<HeaderValue>>.
        provider = NoneProvider()
        thread_id = ThreadId.new()

        result = await generate_attestation_header_for_request(
            include_attestation=True,
            attestation_provider=provider,
            thread_id=thread_id,
        )

        self.assertIsNone(result)
        self.assertEqual(provider.contexts, [AttestationContext(thread_id)])

    async def test_sync_provider_receives_context_and_returns_header(self) -> None:
        provider = SyncProvider()
        thread_id = ThreadId.new()

        result = await generate_attestation_header_for_request(
            include_attestation=True,
            attestation_provider=provider,
            thread_id=thread_id,
        )

        self.assertEqual(result, "attested")
        self.assertEqual(provider.contexts, [AttestationContext(thread_id)])

    async def test_async_provider_receives_context_and_returns_header(self) -> None:
        provider = AsyncProvider()
        thread_id = ThreadId.new()

        result = await generate_attestation_header_for_request(
            include_attestation=True,
            attestation_provider=provider,
            thread_id=thread_id,
        )

        self.assertEqual(result, "async-attested")
        self.assertEqual(provider.contexts, [AttestationContext(thread_id)])

    async def test_rejects_non_bool_include_flag(self) -> None:
        with self.assertRaisesRegex(TypeError, "include_attestation must be a bool"):
            await generate_attestation_header_for_request(
                include_attestation=1,  # type: ignore[arg-type]
                attestation_provider=None,
                thread_id=ThreadId.new(),
            )

    def test_normalize_header_rejects_invalid_values(self) -> None:
        self.assertIsNone(normalize_attestation_header_value(None))
        self.assertEqual(normalize_attestation_header_value("ok"), "ok")
        with self.assertRaisesRegex(TypeError, "must be a string"):
            normalize_attestation_header_value(b"bytes")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "CR or LF"):
            normalize_attestation_header_value("bad\nvalue")


if __name__ == "__main__":
    unittest.main()
