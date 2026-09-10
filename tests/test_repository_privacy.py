"""Prevent personal research and image libraries from re-entering Git."""
import subprocess
import unittest
from helpers import ROOT


class RepositoryPrivacyTests(unittest.TestCase):
    def test_git_tracks_only_shareable_resources(self):
        paths = subprocess.check_output(
            ['git', 'ls-files', '-z'], cwd=ROOT, text=True,
        ).split('\0')
        forbidden = ('docs/', 'reports/', 'stage-0/', 'local-data/',
                     'skills/template-atmosphere-image-producer/assets/',
                     'skills/template-atmosphere-image-producer/references/style-card-catalog.md')
        leaked = [path for path in paths if path.startswith(forbidden)]
        self.assertEqual(leaked, [])
