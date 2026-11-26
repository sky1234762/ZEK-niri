import tomllib
import unittest
from pathlib import Path

from tests.utils import TempEnv
from zekniri.deploy.deploy import deploy_selected_configs
from zekniri.deploy.noctalia import disable_native_bar, enable_native_bar


class NoctaliaBarTest(unittest.TestCase):
    def _state(self, t, body):
        path = t.home / ".local" / "state" / "noctalia" / "settings.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_disables_bar_sections_and_preserves_others(self):
        with TempEnv() as t:
            state = self._state(
                t,
                "[bar]\n"
                'order = [ "default", "bar" ]\n'
                "\n"
                "    [bar.bar]\n"
                "    enabled = true\n"
                "    auto_hide = true\n"
                "\n"
                "    [bar.default]\n"
                "    enabled = true\n"
                '    name = "x"\n'
                "\n"
                "[dock]\n"
                "enabled = true\n",
            )
            self.assertTrue(disable_native_bar())
            text = state.read_text(encoding="utf-8")
            self.assertIn("[bar.bar]\n    enabled = false", text)
            self.assertIn("[bar.default]\n    enabled = false", text)
            self.assertIn("auto_hide = true", text)
            self.assertIn("[dock]\nenabled = true", text)

    def test_inserts_enabled_when_missing(self):
        with TempEnv() as t:
            state = self._state(t, "[bar.default]\nname = \"x\"\n")
            self.assertTrue(disable_native_bar())
            self.assertIn("enabled = false", state.read_text(encoding="utf-8"))

    def test_already_disabled_is_noop(self):
        with TempEnv() as t:
            state = self._state(t, "[bar.default]\nenabled = false\n")
            self.assertFalse(disable_native_bar())
            self.assertEqual(state.read_text(encoding="utf-8"), "[bar.default]\nenabled = false\n")

    def test_missing_state_is_noop(self):
        with TempEnv():
            self.assertFalse(disable_native_bar())

    def test_deploy_noctalia_leaves_native_bar_to_installer_policy(self):
        with TempEnv() as t:
            app = t.home / "configs" / "noctalia"
            app.mkdir(parents=True)
            (app / "conf").write_text("x", encoding="utf-8")
            state = self._state(t, "[bar.default]\nenabled = true\n")
            deploy_selected_configs(items_to_deploy=["noctalia"])
            self.assertIn("enabled = true", state.read_text(encoding="utf-8"))

    def test_enable_native_bar_restores_main_section(self):
        with TempEnv() as t:
            state = self._state(t, "[bar.default]\nenabled = false\n[bar.bar]\nenabled = false\n")
            self.assertTrue(enable_native_bar())
            text = state.read_text(encoding="utf-8")
            self.assertIn("[bar.default]\nenabled = true", text)
            self.assertIn("[bar.bar]\nenabled = false", text)

    def test_enable_native_bar_already_enabled_is_noop(self):
        with TempEnv() as t:
            state = self._state(t, "[bar.default]\nenabled = true\n")
            self.assertFalse(enable_native_bar())
            self.assertEqual(state.read_text(encoding="utf-8"), "[bar.default]\nenabled = true\n")

    def test_repo_state_seed_is_portable(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "configs" / "noctalia" / "settings.toml").read_text(encoding="utf-8")
        self.assertNotIn("/home/zek", text)
        data = tomllib.loads(text)
        wallpaper = data["wallpaper"]
        self.assertEqual(wallpaper["directory"], "")
        self.assertEqual(wallpaper["default"]["path"], "")
        self.assertEqual(wallpaper["last"]["path"], "")
        self.assertNotIn("monitors", wallpaper)
        self.assertTrue(data["bar"]["default"]["enabled"])
        self.assertFalse(data["bar"]["bar"]["enabled"])
        self.assertEqual(data["shell"]["avatar_path"], "")


if __name__ == "__main__":
    unittest.main()
