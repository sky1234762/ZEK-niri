import unittest

import zekniri.config as config
from tests.utils import TempEnv


class ConfigTest(unittest.TestCase):
    def _write(self, t, body, user=False):
        if user:
            path = t.home / ".config" / "ZEKniri" / "ZEK-niri.conf"
        else:
            path = t.home / "ZEK-niri.conf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_defaults_without_file(self):
        with TempEnv() as t:
            cfg = config.get_config()
            self.assertFalse(cfg.ask_language_each_start)
            self.assertIsNone(cfg.wallpaper_dir)
            self.assertIsNone(cfg.log_path)
            self.assertEqual(cfg.noctalia_scheme_source, "wallpaper")
            self.assertEqual(cfg.noctalia_scheme_name, "soft")
            self.assertEqual(cfg.preset_palette.parent, t.home / ".config" / "noctalia" / "palettes")
            self.assertEqual(cfg.preset_palette_name, "ZEKniri-preset")

    def test_repo_file_parsed_and_paths_expanded(self):
        with TempEnv() as t:
            self._write(
                t,
                "ask_language_each_start = yes\n"
                "wallpaper_dir = ~/wall\n"
                "log_path = $HOME/z.log\n"
                "preset_palette = ~/p/My.json\n",
            )
            config.reload_config()
            cfg = config.get_config()
            self.assertTrue(cfg.ask_language_each_start)
            self.assertEqual(cfg.wallpaper_dir, t.home / "wall")
            self.assertEqual(cfg.log_path, t.home / "z.log")
            self.assertEqual(cfg.preset_palette, t.home / "p" / "My.json")
            self.assertEqual(cfg.preset_palette_name, "My")

    def test_user_copy_does_not_shadow_repo(self):
        with TempEnv() as t:
            self._write(t, "noctalia_scheme_name = fromrepo\nwallpaper_dir = ~/a\n")
            self._write(t, "noctalia_scheme_name = fromuser\n", user=True)
            config.reload_config()
            cfg = config.get_config()
            self.assertEqual(cfg.noctalia_scheme_name, "fromrepo")
            self.assertEqual(cfg.wallpaper_dir, t.home / "a")

    def test_comments_blank_lines_and_inline(self):
        with TempEnv() as t:
            self._write(t, "# comment\n\n  # indented\n; ini comment\nlog_path = ~/l.log  # inline\n")
            config.reload_config()
            self.assertEqual(config.get_config().log_path, t.home / "l.log")

    def test_bool_variants(self):
        for raw, expected in (
            ("true", True), ("1", True), ("on", True),
            ("false", False), ("0", False), ("no", False), ("", False),
        ):
            with TempEnv() as t:
                self._write(t, f"ask_language_each_start = {raw}\n")
                config.reload_config()
                self.assertEqual(config.get_config().ask_language_each_start, expected, raw)

    def test_multiple_paths(self):
        with TempEnv() as t:
            self._write(
                t,
                "wallpaper_dir = ~/wp1, ~/wp2 ; ~/wp3\n"
                "preset_palette = ~/p/One.json, ~/p/Two.json\n",
            )
            config.reload_config()
            cfg = config.get_config()
            self.assertEqual(cfg.wallpaper_dirs, (t.home / "wp1", t.home / "wp2", t.home / "wp3"))
            self.assertEqual(cfg.wallpaper_dir, t.home / "wp1")
            self.assertEqual(cfg.preset_palettes, (t.home / "p" / "One.json", t.home / "p" / "Two.json"))
            self.assertEqual(cfg.preset_palette, t.home / "p" / "One.json")
            self.assertEqual(cfg.preset_palette_name, "One")
            self.assertEqual(cfg.preset_palette_names, ("One", "Two"))

    def test_user_copy_ignored_for_lists(self):
        with TempEnv() as t:
            (t.home / "ZEK-niri.conf").write_text(
                "wallpaper_palette = ~/a.jpg = ~/a.json\n", encoding="utf-8"
            )
            user = t.home / ".config" / "ZEKniri" / "ZEK-niri.conf"
            user.parent.mkdir(parents=True, exist_ok=True)
            user.write_text("wallpaper_palette = ~/b.jpg = ~/b.json\n", encoding="utf-8")
            config.reload_config()
            self.assertEqual(
                config.get_config().wallpaper_palettes,
                ((t.home / "a.jpg", t.home / "a.json"),),
            )

    def test_user_conf_path(self):
        with TempEnv() as t:
            self.assertEqual(config.user_conf_path(), t.home / ".config" / "ZEKniri" / "ZEK-niri.conf")


if __name__ == "__main__":
    unittest.main()
