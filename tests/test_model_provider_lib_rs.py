import unittest

import pycodex.model_provider as model_provider
from pycodex.model_provider import (
    BearerAuthProvider,
    CoreAuthProvider,
    ModelProvider,
    ProviderAccount,
    ProviderAccountError,
    ProviderAccountState,
    ProviderCapabilities,
    SharedModelProvider,
    auth_provider_from_auth,
    create_model_provider,
    unauthenticated_auth_provider,
)
from pycodex.model_provider.auth import auth_provider_from_auth as module_auth_provider_from_auth
from pycodex.model_provider.auth import unauthenticated_auth_provider as module_unauthenticated_auth_provider
from pycodex.model_provider.bearer_auth_provider import BearerAuthProvider as ModuleBearerAuthProvider
from pycodex.model_provider.provider import create_model_provider as module_create_model_provider


class ModelProviderLibRsTests(unittest.TestCase):
    def test_lib_reexports_rust_public_api_surface(self) -> None:
        # Rust crate/module: codex-model-provider/src/lib.rs public reexports.
        self.assertIs(BearerAuthProvider, ModuleBearerAuthProvider)
        self.assertIs(CoreAuthProvider, ModuleBearerAuthProvider)
        self.assertIs(auth_provider_from_auth, module_auth_provider_from_auth)
        self.assertIs(unauthenticated_auth_provider, module_unauthenticated_auth_provider)
        self.assertIs(create_model_provider, module_create_model_provider)
        self.assertIs(model_provider.ProviderAccount, ProviderAccount)
        self.assertIs(model_provider.ModelProvider, ModelProvider)
        self.assertIs(model_provider.ProviderAccountError, ProviderAccountError)
        self.assertIs(model_provider.ProviderAccountState, ProviderAccountState)
        self.assertIs(model_provider.ProviderCapabilities, ProviderCapabilities)
        self.assertIs(model_provider.SharedModelProvider, SharedModelProvider)

    def test_core_auth_provider_alias_constructs_bearer_provider(self) -> None:
        # Rust crate/module: codex-model-provider/src/lib.rs aliases
        # BearerAuthProvider as CoreAuthProvider.
        auth = CoreAuthProvider.for_test("token", "workspace")

        self.assertIsInstance(auth, BearerAuthProvider)
        self.assertEqual(
            auth.to_auth_headers(),
            {
                "Authorization": "Bearer token",
                "ChatGPT-Account-ID": "workspace",
            },
        )


if __name__ == "__main__":
    unittest.main()
