import unittest

from tests.utils import TempEnv
from zekniri.deploy.deploy import deploy_selected_configs, _phase_atomic_deployment


class DeployTest(unittest.TestCase):
    def _make_app(self, t, name: str, *, preserve=None, chmod=None):
        app = t.home / "configs" / name
        app.mkdir(parents=True)
        (app / "conf").write_text("hello", encoding="utf-8")
        lines = ["[packages]"]
        if preserve:
            lines.append(f'preserve = {preserve!r}')
        if chmod:
            lines.append(f'chmod = {chmod!r}')
        (app / ".module.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return app

    def test_deploy_copies_config(self):
        with TempEnv() as t:
            self._make_app(t, "kitty")
            failed = deploy_selected_configs(items_to_deploy=["kitty"])
            self.assertEqual(failed, [])
            self.assertTrue((t.home / ".config" / "kitty" / "conf").is_file())

    def test_custom_survives_redeploy(self):
        with TempEnv() as t:
            app = self._make_app(t, "kitty")
            deploy_selected_configs(items_to_deploy=["kitty"])
            custom = t.home / ".config" / "kitty" / "mine__custom__.conf"
            custom.write_text("private", encoding="utf-8")
            (app / "conf").write_text("updated", encoding="utf-8")
            deploy_selected_configs(items_to_deploy=["kitty"])
            self.assertEqual(custom.read_text(encoding="utf-8"), "private")
            self.assertEqual((t.home / ".config" / "kitty" / "conf").read_text(encoding="utf-8"), "updated")

    def test_chmod_glob_applied(self):
        with TempEnv() as t:
            app = self._make_app(t, "tool", chmod=["scripts/*.sh"])
            scripts = app / "scripts"
            scripts.mkdir()
            s = scripts / "run.sh"
            s.write_text("#!/bin/sh\n", encoding="utf-8")
            s.chmod(0o644)
            deploy_selected_configs(items_to_deploy=["tool"])
            deployed = t.home / ".config" / "tool" / "scripts" / "run.sh"
            self.assertTrue(deployed.stat().st_mode & 0o111)

    def test_manifest_skipped_from_dest(self):
        with TempEnv() as t:
            self._make_app(t, "kitty")
            deploy_selected_configs(items_to_deploy=["kitty"])
            self.assertFalse((t.home / ".config" / "kitty" / ".module.toml").exists())

    def test_state_file_goes_to_state_home_not_config(self):
        with TempEnv() as t:
            app = t.home / "configs" / "noctalia"
            app.mkdir(parents=True)
            (app / "conf").write_text("hello", encoding="utf-8")
            (app / "settings.toml").write_text("v = 1", encoding="utf-8")
            (app / ".module.toml").write_text(
                '[packages]\nstate = ["settings.toml"]\n', encoding="utf-8"
            )
            failed = deploy_selected_configs(items_to_deploy=["noctalia"])
            self.assertEqual(failed, [])
            # state file must NOT land in ~/.config
            self.assertFalse((t.home / ".config" / "noctalia" / "settings.toml").exists())
            self.assertTrue((t.home / ".config" / "noctalia" / "conf").is_file())
            # ...it lands in ~/.local/state/noctalia/
            state_file = t.home / ".local" / "state" / "noctalia" / "settings.toml"
            self.assertEqual(state_file.read_text(encoding="utf-8"), "v = 1")

    def test_state_file_is_no_clobber(self):
        with TempEnv() as t:
            app = t.home / "configs" / "noctalia"
            app.mkdir(parents=True)
            (app / "settings.toml").write_text("repo", encoding="utf-8")
            (app / ".module.toml").write_text(
                '[packages]\nstate = ["settings.toml"]\n', encoding="utf-8"
            )
            state_dir = t.home / ".local" / "state" / "noctalia"
            state_dir.mkdir(parents=True)
            (state_dir / "settings.toml").write_text("mine", encoding="utf-8")
            deploy_selected_configs(items_to_deploy=["noctalia"])
            self.assertEqual((state_dir / "settings.toml").read_text(encoding="utf-8"), "mine")

    def test_runtime_conf_seeded_no_clobber(self):
        from zekniri.deploy.deploy import deploy_runtime_conf

        with TempEnv() as t:
            (t.home / "ZEK-niri.conf").write_text(
                "noctalia_scheme_name = vivid\n", encoding="utf-8"
            )
            self.assertTrue(deploy_runtime_conf())
            dest = t.home / ".config" / "ZEKniri" / "ZEK-niri.conf"
            self.assertEqual(dest.read_text(encoding="utf-8"), "noctalia_scheme_name = vivid\n")
            (t.home / "ZEK-niri.conf").write_text("noctalia_scheme_name = other\n", encoding="utf-8")
            self.assertFalse(deploy_runtime_conf())
            self.assertEqual(dest.read_text(encoding="utf-8"), "noctalia_scheme_name = vivid\n")

    def _make_menu(self, t):
        src = t.home / "configs" / "ZEKniri-menu"
        src.mkdir(parents=True)
        (src / "ZEK-menu").write_text("#!/usr/bin/python3\nfrom zekniri.menu_app import main\n", encoding="utf-8")
        (src / "ZEKniri-menu.conf").write_text(
            "appimage_path = ~/Apps/tool.AppImage\n", encoding="utf-8"
        )
        (src / ".module.toml").write_text("[packages]\nrepo = []\ndeploy = false\n", encoding="utf-8")
        package = t.home / "zekniri"
        package.mkdir()
        for name in ("__init__.py", "menu_app.py", "menu_config.py", "menu_instance.py", "menu_fullscreen.py"):
            (package / name).write_text("# module\n", encoding="utf-8")

    def test_standalone_menu_deployed(self):
        from zekniri.deploy.tools import deploy_menu

        with TempEnv() as t:
            self._make_menu(t)
            result = deploy_menu()
            self.assertEqual(result.name, "ZEK-menu")
            self.assertGreaterEqual(result.copied, 6)
            installed = t.home / ".local" / "share" / "ZEKniri" / "zekniri"
            self.assertTrue((installed / "menu_app.py").is_file())
            self.assertTrue((installed / "menu_config.py").is_file())
            self.assertTrue((installed / "menu_instance.py").is_file())
            self.assertTrue((installed / "menu_fullscreen.py").is_file())
            launcher = t.home / ".local" / "bin" / "ZEK-menu"
            self.assertTrue(launcher.stat().st_mode & 0o111)
            self.assertIn("from zekniri.menu_app import main", launcher.read_text(encoding="utf-8"))
            conf = t.home / ".config" / "ZEKniri" / "ZEKniri-menu.conf"
            self.assertEqual(conf.read_text(encoding="utf-8"), "appimage_path = ~/Apps/tool.AppImage\n")

    def test_menu_conf_is_not_overwritten(self):
        from zekniri.deploy.tools import deploy_menu

        with TempEnv() as t:
            self._make_menu(t)
            conf = t.home / ".config" / "ZEKniri" / "ZEKniri-menu.conf"
            conf.parent.mkdir(parents=True, exist_ok=True)
            conf.write_text("appimage_path = ~/Apps/mine.AppImage\n", encoding="utf-8")
            deploy_menu()
            self.assertEqual(conf.read_text(encoding="utf-8"), "appimage_path = ~/Apps/mine.AppImage\n")

    def test_menu_source_not_deployed_to_config(self):
        from zekniri.deploy.manifest import discover_deployable_apps

        with TempEnv() as t:
            self._make_menu(t)
            self.assertNotIn("ZEKniri-menu", discover_deployable_apps())

    def test_menu_does_not_add_a_package(self):
        from zekniri.deps import _aggregate_required_packages

        with TempEnv() as t:
            self._make_menu(t)
            self.assertNotIn("ZEKniri-menu", _aggregate_required_packages())

    def test_missing_source_reports_failure(self):
        with TempEnv() as t:
            (t.home / "configs").mkdir(exist_ok=True)
            failed = _phase_atomic_deployment(["ghost"])
            self.assertEqual(failed, ["ghost"])


if __name__ == "__main__":
    unittest.main()
