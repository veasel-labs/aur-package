import importlib.util
import io
import tarfile
import unittest
from pathlib import Path


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
