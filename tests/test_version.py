import unittest
from pathlib import Path

import zekniri.core as core
from zekniri import __version__

ROOT = Path(__file__).resolve().parents[1]


class VersionTest(unittest.TestCase):
    def setUp(self):
        core._VERSION_CACHE = ""

    def tearDown(self):
        core._VERSION_CACHE = ""

    def test_version_matches_changelog(self):
        self.assertEqual(__version__, "1.1.3-rc2")
        self.assertEqual(core.get_version(ROOT), __version__)


if __name__ == "__main__":
    unittest.main()
