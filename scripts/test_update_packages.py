import importlib.util
import io
import json
import os
import tarfile
import unittest
from pathlib import Path
from unittest.mock import call, patch


SCRIPT = Path(__file__).with_name("update-packages.py")
SPEC = importlib.util.spec_from_file_location("update_packages", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UpdatePackageTests(unittest.TestCase):
    @staticmethod
    def make_archive(names: list[str]) -> bytes:
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:gz") as archive:
            for name in names:
                content = b"fixture"
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        return data.getvalue()

    def test_linux_release_archive_requires_standalone_backend_and_tui(self):
        MODULE.validate_linux_bundle(self.make_archive(["veasel", "veasel-tui", "build.json"]))

    def test_linux_release_archive_rejects_old_bun_client_layout(self):
        with self.assertRaisesRegex(ValueError, "veasel-tui"):
            MODULE.validate_linux_bundle(self.make_archive(["veasel", "tui/package.json", "build.json"]))

    def test_linux_release_archive_rejects_symlinked_client(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:gz") as archive:
            for name in ("veasel", "build.json"):
                content = b"fixture"
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
            link = tarfile.TarInfo("veasel-tui")
            link.type = tarfile.SYMTYPE
            link.linkname = "/tmp/untrusted"
            archive.addfile(link)
        with self.assertRaisesRegex(ValueError, "regular file"):
            MODULE.validate_linux_bundle(data.getvalue())

    def test_release_tag_requires_semver_and_maps_to_arch_version(self):
        match = MODULE.TAG_PATTERN.fullmatch("v0.15.1-next.2")
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.group("version").replace("-next.", ".next."), "0.15.1.next.2")
        self.assertIsNone(MODULE.TAG_PATTERN.fullmatch("v0.15.1-rc.1"))

    def test_explicit_tag_uses_direct_release_lookup(self):
        tag = "v0.69.14-next.0"
        release = {"tag_name": tag, "draft": False}
        with patch.object(MODULE, "request", return_value=json.dumps(release).encode()) as request:
            self.assertEqual(MODULE.resolve_release(tag), release)
        request.assert_called_once_with(f"{MODULE.API}/tags/{tag}")

    def test_github_token_authenticates_api_requests_only(self):
        from unittest.mock import MagicMock

        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"ok"
        with patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-token"}), patch.object(
            MODULE.urllib.request, "urlopen", return_value=response
        ) as urlopen:
            self.assertEqual(MODULE.request(f"{MODULE.API}/tags/v0.1.0"), b"ok")
            api_request = urlopen.call_args.args[0]
            self.assertEqual(api_request.get_header("Authorization"), "Bearer fixture-token")
        with patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-token"}), patch.object(
            MODULE.urllib.request, "urlopen", return_value=response
        ) as urlopen:
            MODULE.request("https://github.com/veasel-labs/veasel/releases/download/tag/release.json")
            asset_request = urlopen.call_args.args[0]
            self.assertIsNone(asset_request.get_header("Authorization"))

    def test_explicit_invalid_tag_is_rejected_before_network_request(self):
        with patch.object(MODULE, "request") as request:
            with self.assertRaisesRegex(ValueError, "Unsupported Veasel tag"):
                MODULE.resolve_release("v0.69.14/next")
        request.assert_not_called()

    def test_release_tag_resolves_to_commit(self):
        commit = "a" * 40
        with patch.object(MODULE, "request", return_value=json.dumps({"object": {"type": "commit", "sha": commit}}).encode()) as request:
            self.assertEqual(MODULE.resolve_tag_commit("v1.2.3-next.0"), commit)
        request.assert_called_once_with(f"{MODULE.GIT_API}/ref/tags/v1.2.3-next.0")

    def test_release_tag_resolves_annotated_tag(self):
        tag_sha = "b" * 40
        commit_sha = "c" * 40
        responses = [
            {"object": {"type": "tag", "sha": tag_sha}},
            {"object": {"type": "commit", "sha": commit_sha}},
        ]
        with patch.object(MODULE, "request", side_effect=[json.dumps(item).encode() for item in responses]) as request:
            self.assertEqual(MODULE.resolve_tag_commit("v1.2.3-next.0"), commit_sha)
        self.assertEqual(request.call_count, 2)

    def test_release_tag_rejects_non_commit_target(self):
        with patch.object(MODULE, "request", return_value=json.dumps({"object": {"type": "tree", "sha": "a" * 40}}).encode()):
            with self.assertRaisesRegex(ValueError, "does not resolve to a commit"):
                MODULE.resolve_tag_commit("v1.2.3-next.0")

    def test_release_asset_requires_matching_github_sha256(self):
        content = b"immutable release asset"
        release = {"assets": [{"name": "release.json", "digest": f"sha256:{MODULE.sha256(content)}"}]}
        self.assertEqual(MODULE.verify_github_asset_digest(release, "release.json", content), MODULE.sha256(content))
        with self.assertRaisesRegex(ValueError, "does not match GitHub"):
            MODULE.verify_github_asset_digest(release, "release.json", b"tampered")
        with self.assertRaisesRegex(ValueError, "no SHA-256 digest"):
            MODULE.verify_github_asset_digest({"assets": [{"name": "release.json"}]}, "release.json", content)
        duplicate = {"assets": release["assets"] * 2}
        with self.assertRaisesRegex(ValueError, "ambiguous or missing"):
            MODULE.verify_github_asset_digest(duplicate, "release.json", content)

    def test_linux_manifest_requires_tag_provenance_and_published_platform(self):
        archive = self.make_archive(["veasel", "veasel-tui", "build.json"])
        manifest = {
            "tag": "v1.2.3-next.0",
            "version": "1.2.3-next.0",
            "source_commit": "a" * 40,
            "platforms": {"linux": {"status": "published", "ci_result": "success", "arch": "x86_64"}},
            "assets": [{
                "name": "veasel-Linux.tar.gz",
                "platform": "linux",
                "arch": "x86_64",
                "kind": "cli-archive",
                "sha256": MODULE.sha256(archive),
            }],
        }
        self.assertEqual(
            MODULE.validate_linux_manifest(manifest, "v1.2.3-next.0", "1.2.3-next.0", "a" * 40)["sha256"],
            MODULE.sha256(archive),
        )
        with self.assertRaisesRegex(ValueError, "source commit"):
            MODULE.validate_linux_manifest(manifest, "v1.2.3-next.0", "1.2.3-next.0", "b" * 40)
        manifest["platforms"]["linux"]["status"] = "failed"
        with self.assertRaisesRegex(ValueError, "does not declare a successful"):
            MODULE.validate_linux_manifest(manifest, "v1.2.3-next.0", "1.2.3-next.0", "a" * 40)

    def test_update_pins_release_manifest_assets_and_license_to_tag_commit(self):
        import tempfile

        tag = "v1.2.3-next.0"
        commit = "a" * 40
        archive = self.make_archive(["veasel", "veasel-tui", "build.json"])
        license_file = b"MIT license at immutable source commit"
        manifest = {
            "tag": tag,
            "version": "1.2.3-next.0",
            "source_commit": commit,
            "platforms": {"linux": {"status": "published", "ci_result": "success", "arch": "x86_64"}},
            "assets": [{
                "name": "veasel-Linux.tar.gz",
                "platform": "linux",
                "arch": "x86_64",
                "kind": "cli-archive",
                "sha256": MODULE.sha256(archive),
            }],
        }
        manifest_bytes = json.dumps(manifest).encode()
        release = {
            "tag_name": tag,
            "draft": False,
            "assets": [
                {"name": "release.json", "digest": f"sha256:{MODULE.sha256(manifest_bytes)}"},
                {"name": "veasel-Linux.tar.gz", "digest": f"sha256:{MODULE.sha256(archive)}"},
            ],
        }
        api_release = f"{MODULE.API}/tags/{tag}"
        api_tag = f"{MODULE.GIT_API}/ref/tags/{tag}"
        manifest_url = f"https://github.com/veasel-labs/veasel/releases/download/{tag}/release.json"
        archive_url = f"https://github.com/veasel-labs/veasel/releases/download/{tag}/veasel-Linux.tar.gz"
        license_url = f"{MODULE.RAW}/{commit}/LICENSE"
        responses = {
            api_release: json.dumps(release).encode(),
            api_tag: json.dumps({"object": {"type": "commit", "sha": commit}}).encode(),
            manifest_url: manifest_bytes,
            archive_url: archive,
            license_url: license_file,
        }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "create-veasel-code-bin"
            package.mkdir()
            pkgbuild = package / "PKGBUILD"
            pkgbuild.write_text("pkgver=0.1.0\npkgrel=1\nsha256sums=(\n  'old'\n)\n")
            with patch.object(MODULE, "ROOT", root), patch.object(
                MODULE, "request", side_effect=lambda url: responses[url]
            ) as request:
                self.assertEqual(MODULE.update(tag), tag)

            content = pkgbuild.read_text()
            self.assertIn("pkgver=1.2.3.next.0", content)
            self.assertIn(MODULE.sha256(archive), content)
            self.assertIn(MODULE.sha256(license_file), content)
            self.assertIn(call(api_tag), request.call_args_list)
            self.assertIn(call(license_url), request.call_args_list)

    def test_checksum_replacement_updates_only_pkg_metadata(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "PKGBUILD"
            path.write_text("pkgver=0.1.0\npkgrel=1\nsha256sums=(\n  'old'\n)\n")
            MODULE.replace_pkg_metadata(path, "0.2.0.next.0", ["a" * 64, "b" * 64])
            content = path.read_text()
            self.assertIn("pkgver=0.2.0.next.0", content)
            self.assertIn("'" + "a" * 64 + "'", content)
            self.assertIn("'" + "b" * 64 + "'", content)
            self.assertNotIn("old", content)


if __name__ == "__main__":
    unittest.main()
