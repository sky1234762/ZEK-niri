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
                "preset_palette = ~/wp/a.jpg = ~/pal/a.json\n"
                "preset_palette = ~/wp/b.png = ~/pal/b.json\n",
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
            self._write_conf(t, "preset_palette = ~/wp/a.jpg = ~/pal/a.json\n")
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
            self._write_conf(t, "preset_palette = ~/wp/a.jpg = ~/pal/a.json\n")
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

    def test_apply_palette_unmapped_no_global(self):
        with TempEnv() as t:
            self._write_conf(t, "preset_palette = ~/wp/a.jpg = ~/pal/a.json\n")
            with mock.patch("zekniri.palette.shutil.which", return_value="/usr/bin/noctalia"):
                self.assertFalse(palette.apply_palette(str(t.home / "wp" / "none.jpg")))

    def test_apply_palette_unmapped_uses_global_default(self):
        with TempEnv() as t:
            self._write_conf(t, "preset_palette = ~/pal/default.json\n")
            default = t.home / "pal" / "default.json"
            default.parent.mkdir(parents=True)
            default.write_text("{}", encoding="utf-8")
            with mock.patch("zekniri.palette.shutil.which", return_value="/usr/bin/noctalia"), \
                    mock.patch("zekniri.palette.timed_run") as run:
                run.return_value = mock.Mock(returncode=0)
                self.assertTrue(palette.apply_palette(str(t.home / "wp" / "none.jpg")))
                self.assertEqual(run.call_args[0][0][-1], "default")
    def test_preset_mode_active_reads_style(self):
        with TempEnv() as t:
            style = t.home / ".config" / "waybar" / "style.css"
            style.parent.mkdir(parents=True, exist_ok=True)
            style.write_text('@import "colors.css";', encoding="utf-8")
            self.assertTrue(palette._preset_mode_active())
            style.write_text('@import "colors-noctalia.css";', encoding="utf-8")
            self.assertFalse(palette._preset_mode_active())

    def test_watch_applies_on_wallpaper_change(self):
        with TempEnv():
            calls = []
            with mock.patch("zekniri.palette.current_wallpaper", return_value=Path("/wp/a.jpg")), \
                    mock.patch("zekniri.palette.apply_palette", side_effect=lambda w: calls.append(w) or True), \
                    mock.patch("zekniri.palette._preset_mode_active", return_value=True), \
                    mock.patch("zekniri.palette.time.sleep", side_effect=KeyboardInterrupt):
                self.assertEqual(palette.watch(0), 0)
            self.assertEqual(calls, ["/wp/a.jpg"])

    def test_watch_skips_in_auto_mode(self):
        with TempEnv():
            with mock.patch("zekniri.palette.current_wallpaper", return_value=Path("/wp/a.jpg")), \
                    mock.patch("zekniri.palette.apply_palette") as apply, \
                    mock.patch("zekniri.palette._preset_mode_active", return_value=False), \
                    mock.patch("zekniri.palette.time.sleep", side_effect=KeyboardInterrupt):
                palette.watch(0)
            apply.assert_not_called()
    def test_apply_palette_wait_follows_change(self):
        with TempEnv() as t:
            self._write_conf(
                t,
                "preset_palette = ~/wp/a.jpg = ~/pal/a.json\n"
                "preset_palette = ~/wp/b.jpg = ~/pal/b.json\n",
            )
            for rel in ("wp/a.jpg", "wp/b.jpg", "pal/a.json", "pal/b.json"):
                p = t.home / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("x", encoding="utf-8")
            with mock.patch("zekniri.palette.shutil.which", return_value="/usr/bin/noctalia"), \
                    mock.patch(
                        "zekniri.palette.current_wallpaper",
                        side_effect=[t.home / "wp" / "a.jpg", t.home / "wp" / "b.jpg"],
                    ), \
                    mock.patch("zekniri.palette.time.sleep"), \
                    mock.patch("zekniri.palette.timed_run") as run:
                run.return_value = mock.Mock(returncode=0)
                self.assertTrue(palette.apply_palette(wait=1.0))
                self.assertEqual(run.call_args[0][0][-1], "b")

    def test_watch_lock_prevents_second(self):
        import fcntl

        with TempEnv() as t:
            lock = t.home / ".local" / "state" / "ZEKniri" / "watch.lock"
            lock.parent.mkdir(parents=True, exist_ok=True)
            fd = open(lock, "w")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                self.assertEqual(palette.watch(0), 0)  # already running
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                fd.close()
    def test_apply_waybar_colors_copies_external(self):
        with TempEnv() as t:
            self._write_conf(t, "waybar_colors = ~/wp/a.jpg = ~/wb/a.css\n")
            wp = t.home / "wp" / "a.jpg"
            wp.parent.mkdir(parents=True)
            wp.write_text("x", encoding="utf-8")
            css = t.home / "wb" / "a.css"
            css.parent.mkdir(parents=True)
            css.write_text("* { color: red; }", encoding="utf-8")
            style = t.home / ".config" / "waybar" / "style.css"
            style.parent.mkdir(parents=True, exist_ok=True)
            style.write_text('@import "colors.css";\n* {}', encoding="utf-8")

            with mock.patch("zekniri.palette._reload_waybar") as reload_:
                self.assertTrue(palette.apply_waybar_colors(wp))
                reload_.assert_called_once()
            self.assertIn('@import "colors-wallpaper.css";', style.read_text(encoding="utf-8"))
            self.assertTrue((style.parent / "colors-wallpaper.css").is_file())

    def test_apply_waybar_colors_relative_import(self):
        with TempEnv() as t:
            self._write_conf(t, "waybar_colors = ~/wp/a.jpg = ~/.config/waybar/colors/a.css\n")
            wp = t.home / "wp" / "a.jpg"
            wp.parent.mkdir(parents=True)
            wp.write_text("x", encoding="utf-8")
            css = t.home / ".config" / "waybar" / "colors" / "a.css"
            css.parent.mkdir(parents=True)
            css.write_text("* {}", encoding="utf-8")
            style = t.home / ".config" / "waybar" / "style.css"
            style.write_text('@import "colors.css";\n', encoding="utf-8")

            with mock.patch("zekniri.palette._reload_waybar"):
                self.assertTrue(palette.apply_waybar_colors(wp))
            self.assertIn('@import "colors/a.css";', style.read_text(encoding="utf-8"))

    def test_apply_waybar_colors_unmapped_is_noop(self):
        with TempEnv() as t:
            self._write_conf(t, "preset_palette = ~/wp/a.jpg = ~/pal/a.json\n")
            style = t.home / ".config" / "waybar" / "style.css"
            style.parent.mkdir(parents=True, exist_ok=True)
            style.write_text('@import "colors.css";\n', encoding="utf-8")
            with mock.patch("zekniri.palette._reload_waybar"):
                self.assertFalse(palette.apply_waybar_colors(t.home / "wp" / "none.jpg"))
            self.assertIn('@import "colors.css";', style.read_text(encoding="utf-8"))
    def test_apply_palette_skips_in_noctalia_mode(self):
        with TempEnv() as t:
            self._write_conf(t, "preset_palette = ~/wp/a.jpg = ~/pal/a.json\n")
            style = t.home / ".config" / "waybar" / "style.css"
            style.parent.mkdir(parents=True, exist_ok=True)
            style.write_text('@import "colors-noctalia.css";', encoding="utf-8")
            with mock.patch("zekniri.palette.shutil.which", return_value="/usr/bin/noctalia"), \
                    mock.patch("zekniri.palette.timed_run") as run:
                self.assertFalse(palette.apply_palette(str(t.home / "wp" / "a.jpg")))
                run.assert_not_called()

    def test_apply_palette_force_overrides_mode(self):
        with TempEnv() as t:
            self._write_conf(t, "preset_palette = ~/wp/a.jpg = ~/pal/a.json\n")
            style = t.home / ".config" / "waybar" / "style.css"
            style.parent.mkdir(parents=True, exist_ok=True)
            style.write_text('@import "colors-noctalia.css";', encoding="utf-8")
            with mock.patch("zekniri.palette.shutil.which", return_value="/usr/bin/noctalia"), \
                    mock.patch("zekniri.palette.timed_run") as run:
                run.return_value = mock.Mock(returncode=0)
                self.assertTrue(palette.apply_palette(str(t.home / "wp" / "a.jpg"), force=True))


if __name__ == "__main__":
    unittest.main()
