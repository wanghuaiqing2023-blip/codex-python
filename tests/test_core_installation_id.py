from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from pycodex.core.installation_id import INSTALLATION_ID_FILENAME, resolve_installation_id


class InstallationIdTests(unittest.TestCase):
    def test_resolve_installation_id_generates_and_persists_uuid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            persisted_path = codex_home / INSTALLATION_ID_FILENAME

            installation_id = resolve_installation_id(codex_home)

            self.assertEqual(persisted_path.read_text(encoding="utf-8"), installation_id)
            self.assertEqual(str(uuid.UUID(installation_id)), installation_id)
            if sys.platform != "win32":
                self.assertEqual(persisted_path.stat().st_mode & 0o777, 0o644)

    def test_resolve_installation_id_creates_codex_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir) / "missing" / "nested"

            installation_id = resolve_installation_id(codex_home)

            self.assertEqual((codex_home / INSTALLATION_ID_FILENAME).read_text(encoding="utf-8"), installation_id)

    def test_resolve_installation_id_reuses_existing_uuid_canonically(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            existing = str(uuid.uuid4()).upper()
            (codex_home / INSTALLATION_ID_FILENAME).write_text(f"\n{existing}\n", encoding="utf-8")

            resolved = resolve_installation_id(codex_home)

            self.assertEqual(resolved, str(uuid.UUID(existing)))
            self.assertEqual((codex_home / INSTALLATION_ID_FILENAME).read_text(encoding="utf-8"), f"\n{existing}\n")

    def test_resolve_installation_id_rewrites_invalid_file_contents(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            path = codex_home / INSTALLATION_ID_FILENAME
            path.write_text("not-a-uuid", encoding="utf-8")

            resolved = resolve_installation_id(codex_home)

            self.assertEqual(str(uuid.UUID(resolved)), resolved)
            self.assertEqual(path.read_text(encoding="utf-8"), resolved)

    @unittest.skipIf(sys.platform == "win32", "Unix mode correction is Unix-specific upstream")
    def test_resolve_installation_id_repairs_file_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            codex_home = Path(tmpdir)
            path = codex_home / INSTALLATION_ID_FILENAME
            path.write_text(str(uuid.uuid4()), encoding="utf-8")
            os.chmod(path, 0o600)

            resolve_installation_id(codex_home)

            self.assertEqual(path.stat().st_mode & 0o777, 0o644)


if __name__ == "__main__":
    unittest.main()
