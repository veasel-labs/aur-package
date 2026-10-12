import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("update-packages.py")
SPEC = importlib.util.spec_from_file_location("update_packages", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UpdatePackageTests(unittest.TestCase):
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
