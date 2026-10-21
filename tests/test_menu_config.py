import tempfile
import unittest
from pathlib import Path

from zekniri.menu_config import expand_config_path, menu_config_path, read_menu_entries


class MenuConfigTest(unittest.TestCase):
    def test_reads_repeated_paths_preserving_blank_slot_indexes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            conf = root / "menu.conf"
            conf.write_text(
                "appimage_path = ~/Apps/First.AppImage\n"
                "appimage_path =\n"
                'appimage_path = "~/Apps/Second App.AppImage"\n'
                "memo_path = ~/Notes/notes.txt\n",
                encoding="utf-8",
            )
            apps, memo = read_menu_entries(conf, root)
            self.assertEqual([i for i, _, _ in apps], [1, 3])
            self.assertEqual([p for _, _, p in apps], [root / "Apps/First.AppImage", root / "Apps/Second App.AppImage"])
            self.assertEqual(memo, root / "Notes/notes.txt")

    def test_user_config_path_uses_xdg_location(self):
        home = Path("/home/example")
        self.assertEqual(menu_config_path(home), home / ".config/ZEKniri/ZEKniri-menu.conf")
        self.assertEqual(menu_config_path(home, "/tmp/config"), Path("/tmp/config/ZEKniri/ZEKniri-menu.conf"))

    def test_expands_home_and_quotes(self):
        self.assertEqual(expand_config_path('"~/Notes/one file.txt"', Path("/home/example")), Path("/home/example/Notes/one file.txt"))


if __name__ == "__main__":
    unittest.main()
