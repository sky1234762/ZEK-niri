import os
import unittest
from unittest import mock

import zekniri.config as config
from tests.utils import TempEnv
from zekniri.deploy.assets import assets_present, deploy_assets


class AssetsTest(unittest.TestCase):
    def _seed(self, t, names=("a.jpg", "b.png")):
        wdir = t.home / "assets" / "wallpapers"
        wdir.mkdir(parents=True, exist_ok=True)
        for name in names:
            (wdir / name).write_text("x", encoding="utf-8")
        return wdir

    def test_deploy_goes_to_pictures_wallpaper(self):
        with TempEnv() as t:
            self._seed(t)
            self.assertTrue(assets_present())
            result = deploy_assets()
            dest = t.home / "Pictures" / "wallpaper"
            self.assertEqual(result.destination, str(dest))
            self.assertEqual(result.copied, 2)
            self.assertTrue((dest / "a.jpg").is_file())
            self.assertTrue((dest / "b.png").is_file())

    def test_no_clobber_keeps_existing_file(self):
        with TempEnv() as t:
            self._seed(t)
            dest = t.home / "Pictures" / "wallpaper"
            dest.mkdir(parents=True)
            (dest / "a.jpg").write_text("mine", encoding="utf-8")
            result = deploy_assets()
            self.assertEqual((dest / "a.jpg").read_text(encoding="utf-8"), "mine")
            self.assertEqual(result.skipped, 1)
            self.assertEqual(result.copied, 1)

    def test_deploys_to_every_derived_dir(self):
        with TempEnv() as t:
            self._seed(t)
            (t.home / "ZEK-niri.conf").write_text(
                "preset_palette = ~/wp1/a.jpg = ~/pal/a.json\n"
                "preset_palette = ~/wp2/b.jpg = ~/pal/b.json\n",
                encoding="utf-8",
            )
            config.reload_config()
            result = deploy_assets()
            self.assertEqual(result.copied, 4)  # 2 files × 2 derived dirs
            for dest in (t.home / "wp1", t.home / "wp2"):
                self.assertTrue((dest / "a.jpg").is_file())
                self.assertTrue((dest / "b.png").is_file())
            # a rerun keeps everything
            again = deploy_assets()
            self.assertEqual(again.copied, 0)
            self.assertEqual(again.skipped, 4)

    def test_missing_wallpapers_is_a_noop(self):
        with TempEnv() as t:
            (t.home / "assets").mkdir(exist_ok=True)
            self.assertFalse(assets_present())
            result = deploy_assets()
            self.assertEqual(result.copied, 0)
            self.assertFalse((t.home / "Pictures" / "wallpaper").exists())

    def test_pics_dir_reads_xdg_user_dirs(self):
        from zekniri.core import get_pics_dir

        with TempEnv() as t:
            conf = t.home / ".config" / "user-dirs.dirs"
            conf.parent.mkdir(parents=True, exist_ok=True)
            conf.write_text('XDG_PICTURES_DIR="$HOME/图片"\n', encoding="utf-8")
            self.assertEqual(get_pics_dir(), t.home / "图片")

    def test_pics_dir_env_override(self):
        from zekniri.core import get_pics_dir

        with TempEnv() as t:
            with mock.patch.dict(os.environ, {"XDG_PICTURES_DIR": str(t.home / "MyPics")}):
                self.assertEqual(get_pics_dir(), t.home / "MyPics")

    def test_pics_dir_ignores_home_entry(self):
        from zekniri.core import get_pics_dir

        with TempEnv() as t:
            conf = t.home / ".config" / "user-dirs.dirs"
            conf.parent.mkdir(parents=True, exist_ok=True)
            conf.write_text('XDG_PICTURES_DIR="$HOME"\n', encoding="utf-8")
            self.assertEqual(get_pics_dir(), t.home / "Pictures")

    def _seed_noctalia_state(self, t, body: str):
        state = t.home / ".local" / "state" / "noctalia" / "settings.toml"
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(body, encoding="utf-8")
        return state

    def test_syncs_noctalia_directory_from_pictures_root(self):
        from zekniri.core import get_pics_dir

        with TempEnv() as t:
            self._seed(t)
            state = self._seed_noctalia_state(
                t, f'[wallpaper]\ndirectory = "{get_pics_dir()}"\ntransition_on_startup = true\n'
            )
            deploy_assets()
            self.assertIn(
                f'directory = "{get_pics_dir() / "wallpaper"}"',
                state.read_text(encoding="utf-8"),
            )

    def test_keeps_custom_noctalia_directory(self):
        with TempEnv() as t:
            self._seed(t)
            custom = t.home / "MyWallpapers"
            state = self._seed_noctalia_state(t, f'[wallpaper]\ndirectory = "{custom}"\n')
            deploy_assets()
            self.assertIn(f'directory = "{custom}"', state.read_text(encoding="utf-8"))

    def test_inserts_noctalia_directory_when_missing(self):
        with TempEnv() as t:
            self._seed(t)
            state = self._seed_noctalia_state(t, "[wallpaper]\ntransition_on_startup = true\n")
            deploy_assets()
            self.assertIn('directory = "', state.read_text(encoding="utf-8"))

    def test_missing_noctalia_state_is_noop(self):
        with TempEnv() as t:
            self._seed(t)
            result = deploy_assets()
            self.assertEqual(result.copied, 2)


if __name__ == "__main__":
    unittest.main()
