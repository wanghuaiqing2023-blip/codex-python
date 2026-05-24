import unittest

from pycodex.protocol import AgentPath


class AgentPathTests(unittest.TestCase):
    def test_root_has_expected_name(self):
        root = AgentPath.root()

        self.assertEqual(root.as_str(), AgentPath.ROOT)
        self.assertEqual(root.name(), "root")
        self.assertTrue(root.is_root())
        self.assertIsInstance(root, str)

    def test_morpheus_has_expected_name(self):
        morpheus = AgentPath.morpheus()

        self.assertEqual(morpheus.as_str(), AgentPath.MORPHEUS)
        self.assertEqual(morpheus.name(), "morpheus")
        self.assertFalse(morpheus.is_root())

    def test_join_builds_child_paths(self):
        child = AgentPath.root().join("researcher")

        self.assertEqual(child.as_str(), "/root/researcher")
        self.assertEqual(child.name(), "researcher")

    def test_resolve_supports_relative_and_absolute_references(self):
        current = AgentPath("/root/researcher")

        self.assertEqual(current.resolve("worker"), AgentPath("/root/researcher/worker"))
        self.assertEqual(current.resolve("/root/other"), AgentPath("/root/other"))
        self.assertEqual(current.resolve("/root"), AgentPath.root())

    def test_invalid_names_and_paths_are_rejected(self):
        cases = [
            (lambda: AgentPath.root().join("BadName"), "agent_name must use only lowercase letters"),
            (lambda: AgentPath("/not-root"), "absolute agent paths must start with `/root` or be `/morpheus`"),
            (lambda: AgentPath.root().resolve("../sibling"), "agent_name `..` is reserved"),
            (lambda: AgentPath.root().join("root"), "agent_name `root` is reserved"),
            (lambda: AgentPath("/root/"), "absolute agent path must not end with `/`"),
            (lambda: AgentPath.root().resolve("child/"), "relative agent path must not end with `/`"),
        ]
        for call, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    call()


if __name__ == "__main__":
    unittest.main()
