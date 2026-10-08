import unittest
from pathlib import Path
from unittest import mock

import zekniri.config as config
import zekniri.palette as palette
from tests.utils import TempEnv


class PaletteTest(unittest.TestCase):
    def _write_conf(self, t, body):
        (t.home / "ZEK-niri.conf").write_text(body, encoding="utf-8")
        config.reload_config()

    def test_pairs_parsed(self):
        with TempEnv() as t:
            self._write_conf(
                t,
                "wallpaper_palette = ~/wp/a.jpg = ~/pal/a.json\n"
                "wallpaper_palette = ~/wp/b.png = ~/pal/b.json\n",
            )
            cfg = config.get_config()
            self.assertEqual(
                cfg.wallpaper_palettes,
                (
                    (t.home / "wp" / "a.jpg", t.home / "pal" / "a.json"),
                    (t.home / "wp" / "b.png", t.home / "pal" / "b.json"),
                ),
            )

    def test_palette_for_exact_and_basename(self):
        with TempEnv() as t:
            self._write_conf(t, "wallpaper_palette = ~/wp/a.jpg = ~/pal/a.json\n")
            cfg = config.get_config()
            self.assertEqual(cfg.palette_for(t.home / "wp" / "a.jpg"), t.home / "pal" / "a.json")
            # basename fallback: noctalia may report a path in another directory
            self.assertEqual(cfg.palette_for(Path("/elsewhere/a.jpg")), t.home / "pal" / "a.json")
            self.assertIsNone(cfg.palette_for(Path("/elsewhere/z.jpg")))

    def test_current_wallpaper_from_settings(self):
        with TempEnv() as t:
            state = t.home / ".local" / "state" / "noctalia"
            state.mkdir(parents=True)
            (state / "settings.toml").write_text(
                '[wallpaper]\n    [wallpaper.last]\n    path = "/x/one.png"\n',
                encoding="utf-8",
            )
            self.assertEqual(palette.current_wallpaper(), Path("/x/one.png"))

    def test_current_wallpaper_missing_is_none(self):
        with TempEnv():
            self.assertIsNone(palette.current_wallpaper())

    def test_ensure_palette_installed_copies(self):
        with TempEnv() as t:
            src = t.home / "pal" / "a.json"
            src.parent.mkdir(parents=True)
            src.write_text("{}", encoding="utf-8")
            dest = palette.ensure_palette_installed(src)
            self.assertEqual(dest, t.home / ".config" / "noctalia" / "palettes" / "a.json")
            self.assertTrue(dest.is_file())

    def test_apply_palette_runs_noctalia(self):
        with TempEnv() as t:
            self._write_conf(t, "wallpaper_palette = ~/wp/a.jpg = ~/pal/a.json\n")
            wallpaper = t.home / "wp" / "a.jpg"
            wallpaper.parent.mkdir(parents=True)
            wallpaper.write_text("x", encoding="utf-8")
            palette_file = t.home / "pal" / "a.json"
            palette_file.parent.mkdir(parents=True)
            palette_file.write_text("{}", encoding="utf-8")

            with mock.patch("zekniri.palette.shutil.which", return_value="/usr/bin/noctalia"), \
                    mock.patch("zekniri.palette.timed_run") as run:
                run.return_value = mock.Mock(returncode=0)
                self.assertTrue(palette.apply_palette(str(wallpaper)))
                cmd = run.call_args[0][0]
                self.assertEqual(cmd, ["noctalia", "msg", "color-scheme-set", "custom", "a"])

    def test_apply_palette_unmapped(self):
        with TempEnv() as t:
            self._write_conf(t, "preset_palette = ~/pal/default.json\n")
            with mock.patch("zekniri.palette.shutil.which", return_value="/usr/bin/noctalia"):
                self.assertFalse(palette.apply_palette(str(t.home / "wp" / "none.jpg")))


if __name__ == "__main__":
    unittest.main()
