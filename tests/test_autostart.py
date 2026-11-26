import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AutostartTest(unittest.TestCase):
    def test_waybar_and_watcher_have_niri_fallbacks(self):
        text = (ROOT / "configs" / "niri" / "cfg" / "autostart.kdl").read_text(encoding="utf-8")
        self.assertIn("systemctl --user start waybar.service", text)
        self.assertIn("|| exec waybar", text)
        self.assertIn("systemctl --user start zekniri-watch.service", text)
        self.assertIn("ZEK-niri", text)
        self.assertIn("waybar-enabled", text)
        self.assertIn("watcher-enabled", text)
        self.assertNotIn('// spawn-at-startup "waybar"', text)


if __name__ == "__main__":
    unittest.main()
