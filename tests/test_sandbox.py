import unittest

from tests.utils import TempEnv
from zekniri.deploy.deploy import test_deploy


class SandboxTest(unittest.TestCase):
    def test_test_deploy_does_not_touch_real_config(self):
        with TempEnv() as t:
            marker = t.home / ".config" / "marker"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("keep", encoding="utf-8")

            self.assertTrue(test_deploy())

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            self.assertFalse((t.home / ".config" / "waybar").exists())


if __name__ == "__main__":
    unittest.main()
