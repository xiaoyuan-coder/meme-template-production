from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, load_module


release_tools = load_module("release_tools", "scripts/release_tools.py")


class ReleaseInstallTests(unittest.TestCase):
    def test_formal_build_rejects_unborn_dirty_and_untracked_states(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with mock.patch.object(release_tools, "_source_revision", return_value=None), \
                    mock.patch.object(release_tools, "_git_worktree_dirty", return_value=False):
                with self.assertRaises(release_tools.ReleaseError):
                    release_tools.build_skill_package(
                        ROOT, "meme-template-image-producer", output / "unborn"
                    )
            with mock.patch.object(release_tools, "_source_revision", return_value="a" * 40), \
                    mock.patch.object(release_tools, "_git_worktree_dirty", return_value=True):
                with self.assertRaises(release_tools.ReleaseError):
                    release_tools.build_skill_package(
                        ROOT, "meme-template-image-producer", output / "dirty"
                    )
            with mock.patch.object(release_tools, "_source_revision", return_value="b" * 40), \
                    mock.patch.object(release_tools, "_git_worktree_dirty", return_value=False):
                package, _ = release_tools.build_skill_package(
                    ROOT, "meme-template-image-producer", output / "clean"
                )
                manifest, _ = release_tools._read_package(package)
                self.assertEqual(manifest["sourceRevision"], "b" * 40)
                self.assertNotIn("maintenanceOnly", manifest)

    def test_both_skills_build_reproducibly_and_install_independently(self):
        for skill_name in sorted(release_tools.ALLOWED_SKILLS):
            with self.subTest(skill=skill_name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                package_a, digest_a = release_tools.build_skill_package(
                    ROOT, skill_name, root / "packages-a", allow_uncommitted=True
                )
                package_b, digest_b = release_tools.build_skill_package(
                    ROOT, skill_name, root / "packages-b", allow_uncommitted=True
                )
                self.assertEqual(digest_a, digest_b)
                self.assertEqual(package_a.read_bytes(), package_b.read_bytes())
                installed, receipt = release_tools.install_skill_package(
                    package_a,
                    root / "installed",
                    expected_package_sha256=digest_a,
                )
                self.assertTrue((installed / "SKILL.md").is_file())
                self.assertTrue(receipt.is_file())
                manifest, _ = release_tools._read_package(package_a)
                release_tools.verify_installed_skill(installed, manifest)
                active = release_tools.activate_installed_skill(installed, root / "discovery")
                self.assertTrue(active.is_symlink())
                self.assertEqual(active.resolve(), installed.resolve())
                self.assertEqual(
                    release_tools.activate_installed_skill(installed, root / "discovery"),
                    active,
                )

    def test_install_rejects_untrusted_package_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package, _ = release_tools.build_skill_package(
                ROOT, "meme-template-image-producer", root / "packages", allow_uncommitted=True
            )
            with self.assertRaises(release_tools.ReleaseError):
                release_tools.install_skill_package(
                    package, root / "installed", expected_package_sha256="0" * 64
                )


if __name__ == "__main__":
    unittest.main()
