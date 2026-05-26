from __future__ import annotations

import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from pycodex.core import (
    HttpResponse,
    RemoteSkillAuth,
    RemoteSkillDownloadResult,
    RemoteSkillProductSurface,
    RemoteSkillScope,
    RemoteSkillSummary,
    as_query_product_surface,
    as_query_scope,
    ensure_codex_backend_auth,
    export_remote_skill,
    extract_zip_to_dir,
    is_zip_payload,
    list_remote_skills,
    normalize_zip_name,
    safe_join,
)


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class RemoteSkillsTests(unittest.TestCase):
    def test_query_scope_and_product_surface_match_upstream_values(self) -> None:
        self.assertEqual(as_query_scope(RemoteSkillScope.WORKSPACE_SHARED), "workspace-shared")
        self.assertEqual(as_query_scope("all-shared"), "all-shared")
        self.assertEqual(as_query_product_surface(RemoteSkillProductSurface.CODEX), "codex")
        self.assertEqual(as_query_product_surface("atlas"), "atlas")

    def test_auth_rejects_missing_or_api_key_auth(self) -> None:
        with self.assertRaisesRegex(ValueError, "chatgpt authentication required"):
            ensure_codex_backend_auth(None)
        with self.assertRaisesRegex(ValueError, "api key auth is not supported"):
            ensure_codex_backend_auth(RemoteSkillAuth(False))

    def test_list_remote_skills_builds_url_headers_and_parses_response(self) -> None:
        calls = []

        def fake_get(url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
            calls.append((url, headers, timeout))
            return HttpResponse(
                200,
                b'{"hazelnuts":[{"id":"s1","name":"Skill One","description":"Does one"}]}',
            )

        skills = list_remote_skills(
            "https://chatgpt.test/backend-api/",
            RemoteSkillAuth(headers={"Authorization": "Bearer token"}),
            RemoteSkillScope.PERSONAL,
            RemoteSkillProductSurface.CODEX,
            enabled=True,
            http_get=fake_get,
            timeout=12.0,
        )

        self.assertEqual(skills, (RemoteSkillSummary("s1", "Skill One", "Does one"),))
        self.assertEqual(len(calls), 1)
        url, headers, timeout = calls[0]
        self.assertEqual(
            url,
            "https://chatgpt.test/backend-api/hazelnuts?product_surface=codex&scope=personal&enabled=true",
        )
        self.assertEqual(headers, {"Authorization": "Bearer token"})
        self.assertEqual(timeout, 12.0)

    def test_list_remote_skills_reports_status_and_parse_failures(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Request failed with status 500"):
            list_remote_skills(
                "https://chatgpt.test",
                RemoteSkillAuth(),
                RemoteSkillScope.EXAMPLE,
                RemoteSkillProductSurface.CHATGPT,
                http_get=lambda _url, _headers, _timeout: HttpResponse(500, b"bad"),
            )
        with self.assertRaisesRegex(ValueError, "Failed to parse skills response"):
            list_remote_skills(
                "https://chatgpt.test",
                RemoteSkillAuth(),
                RemoteSkillScope.EXAMPLE,
                RemoteSkillProductSurface.CHATGPT,
                http_get=lambda _url, _headers, _timeout: HttpResponse(200, b"not-json"),
            )

    def test_zip_payload_and_name_normalization_match_remote_rs(self) -> None:
        self.assertTrue(is_zip_payload(b"PK\x03\x04abc"))
        self.assertTrue(is_zip_payload(b"PK\x05\x06"))
        self.assertFalse(is_zip_payload(b"not a zip"))
        self.assertEqual(normalize_zip_name("./skill-id/SKILL.md", ["skill-id"]), "SKILL.md")
        self.assertEqual(normalize_zip_name("skill-id/scripts/run.py", ["skill-id"]), "scripts/run.py")
        self.assertIsNone(normalize_zip_name("skill-id/", ["skill-id"]))

    def test_safe_join_rejects_absolute_or_parent_paths(self) -> None:
        base = Path("/tmp/out")
        self.assertEqual(safe_join(base, "nested/file.txt"), base / "nested" / "file.txt")
        self.assertEqual(safe_join(base, r"nested\file.txt"), base / "nested" / "file.txt")
        for name in ("/abs/file.txt", "../escape.txt", "nested/../escape.txt", "C:/escape.txt"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "Invalid file path"):
                    safe_join(base, name)

    def test_extract_zip_to_dir_strips_prefix_and_skips_empty_directory_entries(self) -> None:
        payload = zip_bytes(
            {
                "skill-id/SKILL.md": b"# Skill",
                "skill-id/scripts/run.py": b"print('ok')",
                "other.txt": b"kept",
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)

            extract_zip_to_dir(payload, output, ["skill-id"])

            self.assertEqual((output / "SKILL.md").read_bytes(), b"# Skill")
            self.assertEqual((output / "scripts" / "run.py").read_bytes(), b"print('ok')")
            self.assertEqual((output / "other.txt").read_bytes(), b"kept")

    def test_extract_zip_to_dir_rejects_unsafe_entry(self) -> None:
        payload = zip_bytes({"skill-id/../escape.txt": b"nope"})
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "Invalid file path"):
                extract_zip_to_dir(payload, Path(tmp), ["skill-id"])

    def test_export_remote_skill_downloads_zip_into_codex_home(self) -> None:
        payload = zip_bytes({"skill-id/SKILL.md": b"# Downloaded"})
        calls = []

        def fake_get(url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
            calls.append((url, headers, timeout))
            return HttpResponse(200, payload)

        with tempfile.TemporaryDirectory() as tmp:
            result = export_remote_skill(
                "https://chatgpt.test/",
                tmp,
                {"uses_codex_backend": True, "headers": {"Authorization": "Bearer token"}},
                "skill-id",
                http_get=fake_get,
            )

            self.assertEqual(result, RemoteSkillDownloadResult("skill-id", Path(tmp) / "skills" / "skill-id"))
            self.assertEqual((Path(tmp) / "skills" / "skill-id" / "SKILL.md").read_bytes(), b"# Downloaded")
            self.assertEqual(calls[0][0], "https://chatgpt.test/hazelnuts/skill-id/export")
            self.assertEqual(calls[0][1], {"Authorization": "Bearer token"})

    def test_export_remote_skill_rejects_non_zip_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "not a zip archive"):
                export_remote_skill(
                    "https://chatgpt.test",
                    tmp,
                    RemoteSkillAuth(),
                    "skill-id",
                    http_get=lambda _url, _headers, _timeout: HttpResponse(200, b"plain text"),
                )


if __name__ == "__main__":
    unittest.main()
