import unittest
from unittest.mock import patch

from zekniri.menu_fullscreen import (
    _window_is_fullscreen,
    focused_window_is_fullscreen,
    pointer_over_window,
)


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

    def test_pointer_hit_test_blocks_when_window_is_under_cursor(self):
        payload = '[{"is_under_cursor": true}]'
        completed = type("Result", (), {"returncode": 0, "stdout": payload})()
        with patch("zekniri.menu_fullscreen.subprocess.run", return_value=completed):
            self.assertTrue(pointer_over_window())

    def test_pointer_hit_test_allows_desktop_when_no_window_is_under_cursor(self):
        payload = '[{"is_under_cursor": false}]'
        completed = type("Result", (), {"returncode": 0, "stdout": payload})()
        with patch("zekniri.menu_fullscreen.subprocess.run", return_value=completed):
            self.assertFalse(pointer_over_window())

    def test_pointer_hit_test_fails_open_when_ipc_is_unavailable(self):
        with patch("zekniri.menu_fullscreen.subprocess.run", side_effect=OSError("no IPC")):
            self.assertFalse(pointer_over_window())


if __name__ == "__main__":
    unittest.main()
