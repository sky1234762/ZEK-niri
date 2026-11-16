import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.utils import TempEnv
from zekniri import outputs


class OutputsTest(unittest.TestCase):
    def test_detect_current_modes(self):
        payload = {
            "eDP-1": {
                "name": "eDP-1",
                "modes": [
                    {"width": 2560, "height": 1600, "refresh_rate": 60000},
                    {"width": 2560, "height": 1600, "refresh_rate": 300000},
                ],
                "current_mode": 1,
            }
        }
        completed = type("Result", (), {"returncode": 0, "stdout": json.dumps(payload)})()
        with mock.patch("zekniri.outputs.subprocess.run", return_value=completed):
            self.assertEqual(outputs.detect_output_modes(), [("eDP-1", "2560x1600@300.00")])

    def test_detect_choices_lists_all_modes_sorted(self):
        payload = {
            "eDP-1": {
                "name": "eDP-1",
                "modes": [
                    {"width": 2560, "height": 1600, "refresh_rate": 60000},
                    {"width": 640, "height": 480, "refresh_rate": 59940},
                    {"width": 2560, "height": 1600, "refresh_rate": 300000},
                    {"width": 2560, "height": 1600, "refresh_rate": 240000},
                ],
                "current_mode": 2,
            }
        }
        completed = type("Result", (), {"returncode": 0, "stdout": json.dumps(payload)})()
        with mock.patch("zekniri.outputs.subprocess.run", return_value=completed):
            self.assertEqual(
                outputs.detect_output_choices(),
                [
                    (
                        "eDP-1",
                        [
                            "2560x1600@300.00",
                            "2560x1600@240.00",
                            "2560x1600@60.00",
                            "640x480@59.94",
                        ],
                        0,
                    )
                ],
            )

    def test_detect_failure_is_empty(self):
        completed = type("Result", (), {"returncode": 1, "stdout": ""})()
        with mock.patch("zekniri.outputs.subprocess.run", return_value=completed):
            self.assertEqual(outputs.detect_output_modes(), [])

    def test_write_updates_existing_mode_and_preserves_other_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.kdl"
            path.write_text(
                'include "./cfg/display.kdl"\n'
                'output "eDP-1" {\n'
                '    mode "2560x1600@60.00"\n'
                "    scale 1.5\n"
                "}\n",
                encoding="utf-8",
            )
            self.assertTrue(outputs.write_output_modes(path, [("eDP-1", "2560x1600@300.00")]))
            text = path.read_text(encoding="utf-8")
            self.assertIn('    mode "2560x1600@300.00"', text)
            self.assertIn("    scale 1.5", text)
            self.assertIn('include "./cfg/display.kdl"', text)

    def test_write_appends_new_output(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.kdl"
            path.write_text('output "eDP-1" {\n    mode "2560x1600@300.00"\n}\n', encoding="utf-8")
            self.assertTrue(
                outputs.write_output_modes(
                    path,
                    [("eDP-1", "2560x1600@300.00"), ("HDMI-A-1", "1920x1080@60.00")],
                )
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn('output "HDMI-A-1" {\n    mode "1920x1080@60.00"\n}', text)

    def test_write_inserts_mode_when_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.kdl"
            path.write_text('output "eDP-1" {\n    scale 1.5\n}\n', encoding="utf-8")
            self.assertTrue(outputs.write_output_modes(path, [("eDP-1", "2560x1600@300.00")]))
            text = path.read_text(encoding="utf-8")
            self.assertIn('    mode "2560x1600@300.00"', text)
            self.assertIn("    scale 1.5", text)

    def test_write_no_change_returns_false(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.kdl"
            path.write_text('output "eDP-1" {\n    mode "2560x1600@300.00"\n}\n', encoding="utf-8")
            self.assertFalse(outputs.write_output_modes(path, [("eDP-1", "2560x1600@300.00")]))

    def test_choose_modes_selects_one_per_output(self):
        with TempEnv() as t:
            path = t.home / ".config" / "niri" / "config.kdl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                'output "eDP-1" {\n    mode "2560x1600@300.00"\n}\n'
                'output "HDMI-A-1" {\n    mode "1280x720@60.00"\n}\n',
                encoding="utf-8",
            )
            choices = [
                ("eDP-1", ["2560x1600@300.00", "2560x1600@60.00"], 0),
                ("HDMI-A-1", ["1920x1080@60.00", "1280x720@60.00"], 1),
            ]
            with mock.patch("zekniri.outputs.detect_output_choices", return_value=choices), \
                    mock.patch("zekniri.outputs.Menu") as menu_cls:
                menu_cls.return_value.run.side_effect = [1, 0]
                self.assertTrue(outputs.choose_and_write_output_modes())
            text = path.read_text(encoding="utf-8")
            self.assertIn('output "eDP-1" {\n    mode "2560x1600@60.00"', text)
            self.assertIn('output "HDMI-A-1" {\n    mode "1920x1080@60.00"', text)

    def test_choose_modes_cancel_writes_nothing(self):
        with TempEnv() as t:
            path = t.home / ".config" / "niri" / "config.kdl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('output "eDP-1" {\n    mode "2560x1600@60.00"\n}\n', encoding="utf-8")
            with mock.patch(
                "zekniri.outputs.detect_output_choices",
                return_value=[("eDP-1", ["2560x1600@300.00", "2560x1600@60.00"], 0)],
            ), mock.patch("zekniri.outputs.Menu") as menu_cls:
                menu_cls.return_value.run.return_value = None
                self.assertFalse(outputs.choose_and_write_output_modes())
            self.assertIn('mode "2560x1600@60.00"', path.read_text(encoding="utf-8"))

    def test_choose_modes_keep_leaves_config_untouched(self):
        with TempEnv() as t:
            path = t.home / ".config" / "niri" / "config.kdl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('output "eDP-1" {\n    mode "2560x1600@60.00"\n}\n', encoding="utf-8")
            with mock.patch(
                "zekniri.outputs.detect_output_choices",
                return_value=[("eDP-1", ["2560x1600@300.00", "2560x1600@60.00"], 0)],
            ), mock.patch("zekniri.outputs.Menu") as menu_cls:
                menu_cls.return_value.run.return_value = 2  # keep-current item
                self.assertFalse(outputs.choose_and_write_output_modes())
            self.assertIn('mode "2560x1600@60.00"', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
