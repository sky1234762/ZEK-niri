import unittest
from pathlib import Path

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
                "log_path = $HOME/z.log\n"
                "preset_palette = ~/wp/a.jpg = ~/p/A.json\n"
                "preset_palette = ~/p/Default.json\n",
            )
            config.reload_config()
            cfg = config.get_config()
            self.assertTrue(cfg.ask_language_each_start)
            self.assertEqual(cfg.log_path, t.home / "z.log")
            self.assertEqual(
                cfg.wallpaper_palettes,
                ((t.home / "wp" / "a.jpg", t.home / "p" / "A.json"),),
            )
            self.assertEqual(cfg.default_palettes, (t.home / "p" / "Default.json",))
            self.assertEqual(cfg.preset_palette, t.home / "p" / "Default.json")
            # deploy dir is derived from the mapped wallpaper's parent
            self.assertEqual(cfg.wallpaper_dirs, (t.home / "wp",))

    def test_user_copy_overrides_repo(self):
        with TempEnv() as t:
            self._write(t, "noctalia_scheme_name = fromrepo\npreset_palette = ~/wp/a.jpg = ~/repo.json\n")
            self._write(t, "noctalia_scheme_name = fromuser\n", user=True)
            config.reload_config()
            cfg = config.get_config()
            self.assertEqual(cfg.noctalia_scheme_name, "fromuser")
            self.assertEqual(
                cfg.wallpaper_palettes,
                ((t.home / "wp" / "a.jpg", t.home / "repo.json"),),
            )

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

    def test_multiple_wallpaper_palette_pairs(self):
        with TempEnv() as t:
            self._write(
                t,
                "preset_palette = ~/wp1/a.jpg = ~/p/One.json\n"
                "preset_palette = ~/wp2/b.jpg = ~/p/Two.json\n"
                "preset_palette = ~/p/Fallback.json, ~/p/Other.json\n",
            )
            config.reload_config()
            cfg = config.get_config()
            self.assertEqual(cfg.wallpaper_dirs, (t.home / "wp1", t.home / "wp2"))
            self.assertEqual(cfg.palette_for(t.home / "wp1" / "a.jpg"), t.home / "p" / "One.json")
            self.assertEqual(cfg.palette_for(t.home / "wp2" / "b.jpg"), t.home / "p" / "Two.json")
            self.assertEqual(
                cfg.default_palettes, (t.home / "p" / "Fallback.json", t.home / "p" / "Other.json")
            )
            self.assertEqual(cfg.preset_palette, t.home / "p" / "Fallback.json")
            self.assertEqual(cfg.preset_palette_names, ("Fallback", "Other"))

    def test_waybar_colors_mapping(self):
        with TempEnv() as t:
            self._write(
                t,
                "waybar_colors = ~/wp/a.jpg = ~/wb/a.css\n"
                "waybar_colors = ~/wp/b.jpg = ~/wb/b.css\n",
            )
            config.reload_config()
            cfg = config.get_config()
            self.assertEqual(
                cfg.waybar_colors,
                (
                    (t.home / "wp" / "a.jpg", t.home / "wb" / "a.css"),
                    (t.home / "wp" / "b.jpg", t.home / "wb" / "b.css"),
                ),
            )
            self.assertEqual(cfg.waybar_colors_for(t.home / "wp" / "a.jpg"), t.home / "wb" / "a.css")
            self.assertIsNone(cfg.waybar_colors_for(Path("/elsewhere/z.jpg")))

    def test_user_copy_replaces_repo_list(self):
        with TempEnv() as t:
            (t.home / "ZEK-niri.conf").write_text(
                "preset_palette = ~/a.jpg = ~/a.json\n", encoding="utf-8"
            )
            user = t.home / ".config" / "ZEKniri" / "ZEK-niri.conf"
            user.parent.mkdir(parents=True, exist_ok=True)
            user.write_text("preset_palette = ~/b.jpg = ~/b.json\n", encoding="utf-8")
            config.reload_config()
            self.assertEqual(
                config.get_config().wallpaper_palettes,
                ((t.home / "b.jpg", t.home / "b.json"),),
            )

    def test_wallpaper_palette_alias(self):
        with TempEnv() as t:
            self._write(t, "wallpaper_palette = ~/wp/a.jpg = ~/p/A.json\n")
            config.reload_config()
            self.assertEqual(
                config.get_config().wallpaper_palettes,
                ((t.home / "wp" / "a.jpg", t.home / "p" / "A.json"),),
            )

    def test_user_conf_path(self):
        with TempEnv() as t:
            self.assertEqual(config.user_conf_path(), t.home / ".config" / "ZEKniri" / "ZEK-niri.conf")


if __name__ == "__main__":
    unittest.main()
