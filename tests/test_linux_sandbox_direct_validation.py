import importlib
import inspect
import os
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path


LINUX_SANDBOX_TEST_MODULES = (
    "tests.test_linux_sandbox_bazel_bwrap_rs",
    "tests.test_linux_sandbox_bundled_bwrap_rs",
    "tests.test_linux_sandbox_bwrap_rs",
    "tests.test_linux_sandbox_exec_util_rs",
    "tests.test_linux_sandbox_landlock_rs",
    "tests.test_linux_sandbox_launcher_rs",
    "tests.test_linux_sandbox_lib_rs",
    "tests.test_linux_sandbox_main_rs",
    "tests.test_linux_sandbox_proxy_routing_rs",
)

LINUX_SANDBOX_UNITTEST_MODULES = (
    "tests.test_linux_sandbox_linux_run_main_rs",
)


class _RaisesContext:
    def __init__(self, expected_exception, match=None):
        self.expected_exception = expected_exception
        self.match = match
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            raise AssertionError(f"expected {self.expected_exception.__name__} to be raised")
        if not issubclass(exc_type, self.expected_exception):
            return False
        self.value = exc
        if self.match is not None and re.search(self.match, str(exc)) is None:
            raise AssertionError(f"exception message {str(exc)!r} did not match {self.match!r}")
        return True


class _MonkeyPatch:
    def __init__(self):
        self._undo = []

    def setattr(self, target, name, value):
        original = getattr(target, name)
        self._undo.append(lambda: setattr(target, name, original))
        setattr(target, name, value)

    def setitem(self, mapping, name, value):
        old = mapping.get(name)
        had_old = name in mapping
        self._undo.append(lambda: _restore_mapping_item(mapping, name, old, had_old))
        mapping[name] = value

    def setenv(self, name, value):
        old = os.environ.get(name)
        had_old = name in os.environ
        self._undo.append(lambda: _restore_env(name, old, had_old))
        os.environ[name] = value

    def delenv(self, name, raising=True):
        old = os.environ.get(name)
        had_old = name in os.environ
        if not had_old and raising:
            raise KeyError(name)
        self._undo.append(lambda: _restore_env(name, old, had_old))
        os.environ.pop(name, None)

    def undo(self):
        for undo in reversed(self._undo):
            undo()
        self._undo.clear()


def _restore_env(name, value, had_value):
    if had_value:
        os.environ[name] = value
    else:
        os.environ.pop(name, None)


def _restore_mapping_item(mapping, name, value, had_value):
    if had_value:
        mapping[name] = value
    else:
        mapping.pop(name, None)


def _fake_pytest_module():
    module = types.ModuleType("pytest")
    module.MonkeyPatch = _MonkeyPatch
    module.raises = lambda expected, match=None: _RaisesContext(expected, match)
    return module


def _run_pytest_style_function(function):
    kwargs = {}
    temporary_directories = []
    monkeypatch = None
    try:
        for parameter in inspect.signature(function).parameters:
            if parameter == "tmp_path":
                tempdir = tempfile.TemporaryDirectory()
                temporary_directories.append(tempdir)
                kwargs[parameter] = Path(tempdir.name)
            elif parameter == "monkeypatch":
                monkeypatch = _MonkeyPatch()
                kwargs[parameter] = monkeypatch
            else:
                raise AssertionError(f"unsupported fixture {parameter!r} for {function.__module__}.{function.__name__}")
        function(**kwargs)
    finally:
        if monkeypatch is not None:
            monkeypatch.undo()
        for tempdir in reversed(temporary_directories):
            tempdir.cleanup()


@unittest.skipIf("pytest" in sys.modules, "pytest runtime should collect the linux-sandbox tests directly")
class LinuxSandboxDirectValidationTests(unittest.TestCase):
    def test_linux_sandbox_tests_without_pytest_runtime(self):
        # Rust crate: codex-linux-sandbox
        # Rust modules: src/lib.rs, src/main.rs, src/bazel_bwrap.rs,
        # src/bundled_bwrap.rs, src/exec_util.rs, src/launcher.rs,
        # src/landlock.rs, src/proxy_routing.rs, src/bwrap.rs
        # Contract: fallback validation for the pure Python Rust-derived test
        # functions when the local Python runtime has no pytest package.
        original_pytest = sys.modules.get("pytest")
        sys.modules["pytest"] = _fake_pytest_module()
        try:
            executed = 0
            for module_name in LINUX_SANDBOX_TEST_MODULES:
                sys.modules.pop(module_name, None)
                module = importlib.import_module(module_name)
                for name, value in vars(module).items():
                    if name.startswith("test_") and inspect.isfunction(value):
                        with self.subTest(test=f"{module_name}.{name}"):
                            _run_pytest_style_function(value)
                        executed += 1
            self.assertEqual(executed, 78)
        finally:
            for module_name in LINUX_SANDBOX_TEST_MODULES:
                sys.modules.pop(module_name, None)
            if original_pytest is None:
                sys.modules.pop("pytest", None)
            else:
                sys.modules["pytest"] = original_pytest

        # Rust crate: codex-linux-sandbox
        # Rust module: src/linux_run_main.rs
        # Contract: keep unittest-style Rust-derived linux-sandbox modules
        # reachable from the same fallback crate validation entrypoint.
        loader = unittest.defaultTestLoader
        suite = unittest.TestSuite()
        for module_name in LINUX_SANDBOX_UNITTEST_MODULES:
            module = importlib.import_module(module_name)
            suite.addTests(loader.loadTestsFromModule(module))

        result = unittest.TestResult()
        suite.run(result)

        if not result.wasSuccessful():
            details = [
                f"{test}: {err}"
                for test, err in [*result.failures, *result.errors]
            ]
            raise AssertionError("\n".join(details))
        self.assertEqual(result.testsRun, 17)
