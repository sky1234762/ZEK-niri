import unittest

from tests.utils import TempEnv
from zekniri.deploy.tools import deploy_zeklive, zeklive_present


class ToolsTest(unittest.TestCase):
    def _seed(self, t):
        d = t.home / "ZEKlive"
        (d / "scirpt").mkdir(parents=True)
        (d / "ZEK-blv").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        (d / "ZEK-danmaku").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        (d / "scirpt" / "bilibili_live_stream-1").write_text("# dep\n", encoding="utf-8")
        return d

    def test_deploy_zeklive(self):
        with TempEnv() as t:
            self._seed(t)
            self.assertTrue(zeklive_present())
            result = deploy_zeklive()
            self.assertEqual(result.copied, 3)
            blv = t.home / ".local" / "bin" / "ZEK-blv"
            self.assertTrue(blv.is_file())
            self.assertTrue(blv.stat().st_mode & 0o111)
            self.assertTrue((t.home / ".local" / "bin" / "ZEK-danmaku").is_file())
            self.assertTrue(
                (t.home / ".local" / "share" / "ZEK-blv" / "bilibili_live_stream").is_file()
            )

    def test_absent_is_noop(self):
        with TempEnv() as t:
            self.assertFalse(zeklive_present())
            result = deploy_zeklive()
            self.assertEqual(result.copied, 0)


if __name__ == "__main__":
    unittest.main()
