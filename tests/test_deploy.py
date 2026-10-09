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
            # an existing user copy is never overwritten
            (t.home / "ZEK-niri.conf").write_text(
                "noctalia_scheme_name = other\n", encoding="utf-8"
            )
            self.assertFalse(deploy_runtime_conf())
            self.assertEqual(dest.read_text(encoding="utf-8"), "noctalia_scheme_name = vivid\n")

    def test_missing_source_reports_failure(self):
        with TempEnv() as t:
            (t.home / "configs").mkdir(exist_ok=True)
            failed = _phase_atomic_deployment(["ghost"])
            self.assertEqual(failed, ["ghost"])


if __name__ == "__main__":
    unittest.main()
