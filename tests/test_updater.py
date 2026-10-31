import hashlib
import io
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from updater import UpdateError, UpdateManager, _GitHubRedirectHandler, parse_version, version_is_newer


class UpdateVersionTests(unittest.TestCase):
    def test_parse_semver_with_v_prefix(self):
        self.assertEqual(parse_version("v1.0.0"), (1, 0, 0))

    def test_newer_version_comparison(self):
        self.assertTrue(version_is_newer("1.0.1", "1.0.0"))
        self.assertFalse(version_is_newer("1.0.0", "1.0.0"))
        self.assertFalse(version_is_newer("0.9.9", "1.0.0"))

    def test_rejects_non_semver_tags(self):
        for value in ("latest", "v1", "1.0.0-beta", "../1.0.0", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_version(value)

    def test_expected_platform_asset_names(self):
        self.assertEqual(
            UpdateManager.expected_asset_name("1.0.0", "Windows"),
            "EscritorAutomatico-Setup-v1.0.0.exe",
        )
        self.assertEqual(
            UpdateManager.expected_asset_name("1.0.0", "Linux"),
            "EscritorAutomatico-v1.0.0-linux-x86_64.tar.gz",
        )


    def test_rejects_dot_components_in_repository(self):
        manager = UpdateManager()
        with tempfile.TemporaryDirectory() as td:
            config = Path(td) / "update_config.json"
            config.write_text('{"repository":"../repo"}', encoding="utf-8")
            with patch("updater.resource_dir", return_value=Path(td)):
                with self.assertRaises(UpdateError):
                    manager._config()

    def test_redirect_handler_rejects_untrusted_destination(self):
        handler = _GitHubRedirectHandler()
        request = __import__("urllib.request", fromlist=["Request"]).Request(
            "https://github.com/owner/repo/releases/download/v1/file.exe"
        )
        with self.assertRaises(UpdateError):
            handler.redirect_request(
                request, None, 302, "Found", {}, "https://example.invalid/payload"
            )

    def test_redirect_handler_allows_expected_asset_host(self):
        handler = _GitHubRedirectHandler()
        request = __import__("urllib.request", fromlist=["Request"]).Request(
            "https://github.com/owner/repo/releases/download/v1/file.exe"
        )
        redirected = handler.redirect_request(
            request, None, 302, "Found", {}, "https://objects.githubusercontent.com/payload"
        )
        self.assertEqual(redirected.full_url, "https://objects.githubusercontent.com/payload")

    def test_checksum_must_match_exact_asset_name(self):
        digest = hashlib.sha256(b"installer").hexdigest()
        text = f"{digest}  EscritorAutomatico-Setup-v1.0.0.exe\n"
        self.assertEqual(
            UpdateManager._find_checksum(text, "EscritorAutomatico-Setup-v1.0.0.exe"), digest
        )
        with self.assertRaises(UpdateError):
            UpdateManager._find_checksum(text, "another-file.exe")


class FakeResponse(io.BytesIO):
    def __init__(self, payload, final_url):
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}
        self._final_url = final_url

    def geturl(self):
        return self._final_url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


class UpdateDownloadTests(unittest.TestCase):
    def test_windows_download_is_verified_before_being_returned(self):
        payload = b"MZ" + b"x" * 120_000
        asset_name = "EscritorAutomatico-Setup-v1.0.1.exe"
        digest = hashlib.sha256(payload).hexdigest()
        checksum = f"{digest}  {asset_name}\n".encode("utf-8")
        release_url = "https://github.com/example/escritor/releases/download/v1.0.1/"
        responses = [
            FakeResponse(checksum, release_url + "SHA256SUMS.txt"),
            FakeResponse(b"valid-ed25519-signature", release_url + "SHA256SUMS.txt.sig"),
            FakeResponse(payload, "https://objects.githubusercontent.com/release-asset"),
        ]
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td) / "cache"
            release = {
                "version": "1.0.1",
                "tag": "v1.0.1",
                "assets": [
                    {"name": asset_name, "url": release_url + asset_name, "size": len(payload)},
                    {"name": "SHA256SUMS.txt", "url": release_url + "SHA256SUMS.txt", "size": len(checksum)},
                    {"name": "SHA256SUMS.txt.sig", "url": release_url + "SHA256SUMS.txt.sig", "size": 64},
                ],
                "repository": "example/escritor",
            }
            with patch("updater.user_cache_dir", return_value=cache), patch(
                "updater.verify_release_manifest", return_value=True
            ), patch("updater._open_github_url", side_effect=responses):
                prepared = UpdateManager().download_and_prepare(release, os_name="Windows")
            self.assertEqual(prepared["kind"], "windows")
            self.assertEqual(prepared["sha256"], digest)
            self.assertEqual(Path(prepared["path"]).read_bytes(), payload)

    def test_windows_download_rejected_on_hash_mismatch(self):
        payload = b"MZ" + b"x" * 120_000
        asset_name = "EscritorAutomatico-Setup-v1.0.1.exe"
        checksum = ("0" * 64 + "  " + asset_name + "\n").encode("utf-8")
        release_url = "https://github.com/example/escritor/releases/download/v1.0.1/"
        responses = [
            FakeResponse(checksum, release_url + "SHA256SUMS.txt"),
            FakeResponse(b"valid-ed25519-signature", release_url + "SHA256SUMS.txt.sig"),
            FakeResponse(payload, "https://objects.githubusercontent.com/release-asset"),
        ]
        with tempfile.TemporaryDirectory() as td:
            release = {
                "version": "1.0.1", "tag": "v1.0.1", "repository": "example/escritor",
                "assets": [
                    {"name": asset_name, "url": release_url + asset_name, "size": len(payload)},
                    {"name": "SHA256SUMS.txt", "url": release_url + "SHA256SUMS.txt", "size": len(checksum)},
                    {"name": "SHA256SUMS.txt.sig", "url": release_url + "SHA256SUMS.txt.sig", "size": 64},
                ],
            }
            with patch("updater.user_cache_dir", return_value=Path(td) / "cache"), patch(
                "updater.verify_release_manifest", return_value=True
            ), patch("updater._open_github_url", side_effect=responses):
                with self.assertRaisesRegex(UpdateError, "SHA-256 falló"):
                    UpdateManager().download_and_prepare(release, os_name="Windows")


    def test_signature_failure_stops_before_installer_download(self):
        asset_name = "EscritorAutomatico-Setup-v1.0.2.exe"
        base = "https://github.com/example/escritor/releases/download/v1.0.2/"
        checksum = ("a" * 64 + "  " + asset_name + "\n").encode("utf-8")
        responses = [
            FakeResponse(checksum, base + "SHA256SUMS.txt"),
            FakeResponse(b"forged-signature", base + "SHA256SUMS.txt.sig"),
        ]
        release = {
            "version": "1.0.2", "tag": "v1.0.2", "repository": "example/escritor",
            "assets": [
                {"name": asset_name, "url": base + asset_name, "size": 120000},
                {"name": "SHA256SUMS.txt", "url": base + "SHA256SUMS.txt", "size": len(checksum)},
                {"name": "SHA256SUMS.txt.sig", "url": base + "SHA256SUMS.txt.sig", "size": 64},
            ],
        }
        with patch("updater.verify_release_manifest", return_value=False), patch(
            "updater._open_github_url", side_effect=responses
        ) as open_url, patch.object(UpdateManager, "_download_to_file") as download:
            with self.assertRaisesRegex(UpdateError, "firma Ed25519"):
                UpdateManager().download_and_prepare(release, os_name="Windows")
        self.assertEqual(open_url.call_count, 2)
        download.assert_not_called()



class SafeLinuxArchiveTests(unittest.TestCase):
    def test_extracts_regular_files_and_root_dot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "package"
            (source / "EscritorAutomatico").mkdir(parents=True)
            (source / "EscritorAutomatico" / "EscritorAutomatico").write_bytes(b"fake executable")
            (source / "instalar_escritor_automatico_linux.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            archive_path = root / "good.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                archive.add(source / "EscritorAutomatico", arcname="./EscritorAutomatico")
                archive.add(source / "instalar_escritor_automatico_linux.sh", arcname="./instalar_escritor_automatico_linux.sh")
            destination = root / "out"
            destination.mkdir()
            UpdateManager._safe_extract_linux_package(archive_path, destination)
            self.assertEqual((destination / "EscritorAutomatico" / "EscritorAutomatico").read_bytes(), b"fake executable")
            self.assertTrue((destination / "instalar_escritor_automatico_linux.sh").is_file())

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive_path = root / "bad.tar.gz"
            payload = b"do not write outside"
            info = tarfile.TarInfo("../../outside.txt")
            info.size = len(payload)
            with tarfile.open(archive_path, "w:gz") as archive:
                archive.addfile(info, io.BytesIO(payload))
            destination = root / "out"
            destination.mkdir()
            with self.assertRaises(UpdateError):
                UpdateManager._safe_extract_linux_package(archive_path, destination)
            self.assertFalse((root.parent / "outside.txt").exists())

    def test_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive_path = root / "link.tar.gz"
            link = tarfile.TarInfo("EscritorAutomatico/link")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../outside"
            with tarfile.open(archive_path, "w:gz") as archive:
                archive.addfile(link)
            destination = root / "out"
            destination.mkdir()
            with self.assertRaises(UpdateError):
                UpdateManager._safe_extract_linux_package(archive_path, destination)


if __name__ == "__main__":
    unittest.main()
