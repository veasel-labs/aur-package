import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("aur_publish_gate.py")
SPEC = importlib.util.spec_from_file_location("aur_publish_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AurPublishGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.pkgbuild = Path(self.temp.name) / "PKGBUILD"
        self.pkgbuild.write_text("pkgver=0.103.2.next.0\npkgrel=1\n")

    def tearDown(self):
        self.temp.cleanup()

    def test_requires_requested_tag_to_match_reviewed_pkgbuild(self):
        with self.assertRaisesRegex(ValueError, "does not match requested"):
            MODULE.check("v0.103.1-next.0", self.pkgbuild)

    def test_older_aur_version_allows_publish(self):
        with patch.object(MODULE, "rpc_version", return_value="0.102.4.next.0-1"):
            self.assertEqual(MODULE.check("v0.103.2-next.0", self.pkgbuild), "publish")

    def test_equal_aur_version_skips_duplicate(self):
        with patch.object(MODULE, "rpc_version", return_value="0.103.2.next.0-1"):
            self.assertEqual(MODULE.check("v0.103.2-next.0", self.pkgbuild), "already-current")

    def test_newer_aur_version_rejects_downgrade(self):
        with patch.object(MODULE, "rpc_version", return_value="0.104.0.next.0-1"):
            with self.assertRaisesRegex(ValueError, "refusing downgrade"):
                MODULE.check("v0.103.2-next.0", self.pkgbuild)

    def test_newer_remote_commit_wins_over_stale_rpc(self):
        remote = Path(self.temp.name) / "remote"
        remote.write_text("pkgver=0.104.0.next.0\npkgrel=1\n")
        with patch.object(MODULE, "rpc_version", return_value="0.102.4.next.0-1"):
            with self.assertRaisesRegex(ValueError, "refusing downgrade"):
                MODULE.check("v0.103.2-next.0", self.pkgbuild, remote)

    def test_unregistered_desktop_package_can_be_published_after_review(self):
        with patch.object(MODULE, "rpc_version", return_value=None) as rpc:
            self.assertEqual(
                MODULE.check(
                    "v0.103.2-next.0",
                    self.pkgbuild,
                    package_name="veasel-desktop-bin",
                ),
                "publish",
            )
        rpc.assert_called_once_with("veasel-desktop-bin")

    def test_version_order_handles_stable_after_prerelease(self):
        self.assertGreater(MODULE.version_key("1.0.0"), MODULE.version_key("1.0.0.next.99"))


if __name__ == "__main__":
    unittest.main()
