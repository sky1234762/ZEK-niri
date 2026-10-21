import unittest
from unittest.mock import patch

from zekniri.menu_fullscreen import _window_is_fullscreen, focused_window_is_fullscreen


class MenuFullscreenTest(unittest.TestCase):
    def test_explicit_state_takes_precedence(self):
        self.assertTrue(_window_is_fullscreen({"is_fullscreen": True}, {"logical": {"width": 1920, "height": 1080}}))
        self.assertFalse(_window_is_fullscreen({"is_fullscreen": False, "layout": {"tile_size": [1920, 1080]}}, {"logical": {"width": 1920, "height": 1080}}))

    def test_full_output_tile_geometry_detects_fullscreen(self):
        window = {"layout": {"tile_size": [1920, 1080], "window_size": [1920, 1040]}}
        output = {"logical": {"width": 1920, "height": 1080}}
        self.assertTrue(_window_is_fullscreen(window, output))

    def test_regular_maximized_geometry_is_not_fullscreen(self):
        window = {"layout": {"tile_size": [1888, 1020], "window_size": [1888, 1020]}}
        output = {"logical": {"width": 1920, "height": 1080}}
        self.assertFalse(_window_is_fullscreen(window, output))

    def test_ipc_failures_do_not_block_menu(self):
        with patch("zekniri.menu_fullscreen.subprocess.run", side_effect=OSError("no IPC")):
            self.assertFalse(focused_window_is_fullscreen())


if __name__ == "__main__":
    unittest.main()
