"""Regression checks use temporary homes and never touch the real session."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.utils import TempEnv
from zekniri import cli
from zekniri.core import Environment
from zekniri.deploy.deploy import deploy_selected_configs, test_deploy as sandbox_deploy
from zekniri.deploy.tools import enable_waybar_service
from zekniri.state.uninstall import uninstall_zekniri
from zekniri.palette import install_watcher


class InstallerRegressions(unittest.TestCase):
    def seed(self, t, name='app'):
        src = t.env.configs_src / name
        src.mkdir(parents=True)
        (src / 'conf').write_text('/home/user/new')
        return src

    def test_repeat_keep_data_retains_backups(self):
        with TempEnv() as t:
            self.seed(t)
            deploy_selected_configs(items_to_deploy=['app'])
            keep = t.env.nyx_dir / 'backups/important'
            keep.parent.mkdir(parents=True)
            keep.write_text('keep')
            self.assertTrue(uninstall_zekniri('keep-data'))
            self.assertTrue(uninstall_zekniri('keep-data'))
            self.assertEqual(keep.read_text(), 'keep')

    def test_render_does_not_touch_unselected_apps_or_snapshots(self):
        with TempEnv() as t:
            self.seed(t)
            self.seed(t, 'unselected')
            paths = [t.env.config_dir / 'unselected/conf',
                     t.env.config_dir / 'unrelated/conf',
                     t.env.nyx_dir / 'backups/snapshot_20260101_000000/app/conf']
            for path in paths:
                path.parent.mkdir(parents=True)
                path.write_text('/home/user/original')
            deploy_selected_configs(items_to_deploy=['app'])
            for path in paths:
                self.assertEqual(path.read_text(), '/home/user/original')
            self.assertEqual((t.env.config_dir / 'app/conf').read_text(), f'{t.home}/new')

    def test_xdg_config_outside_home_and_custom_preservation(self):
        with TempEnv() as t, tempfile.TemporaryDirectory() as other:
            with patch.dict(os.environ, {'XDG_CONFIG_HOME': other}):
                self.assertEqual(Environment().config_dir, Path(other))
                t.env.config_dir = Path(other)
                t.env.nyx_dir = Path(other) / 'ZEKniri'
                self.seed(t)
                dest = Path(other) / 'app'
                dest.mkdir()
                (dest / 'mine__custom__.conf').write_text('keep')
                self.assertEqual(deploy_selected_configs(items_to_deploy=['app']), [])
                self.assertEqual((dest / 'mine__custom__.conf').read_text(), 'keep')

    def test_sandbox_replaces_and_restores_exported_pictures(self):
        from zekniri.core import get_env, get_pics_dir
        from zekniri.deploy.assets import AssetDeployResult
        with TempEnv() as t:
            external = str(t.home / 'external')
            def inspect():
                self.assertTrue(get_pics_dir().is_relative_to(get_env().home))
                self.assertNotEqual(str(get_pics_dir()), external)
                return AssetDeployResult()
            with patch.dict(os.environ, {'XDG_PICTURES_DIR': external}), \
                 patch('zekniri.deploy.deploy.deploy_assets', side_effect=inspect):
                self.assertTrue(sandbox_deploy())
                self.assertEqual(os.environ['XDG_PICTURES_DIR'], external)
                self.assertFalse(Path(external).exists())

    def test_dependency_failure_aborts_before_deploy(self):
        with TempEnv(), patch('zekniri.cli.sys.stdin.isatty', return_value=False), \
             patch('zekniri.cli.get_missing_deps', return_value=['missing']), \
             patch('zekniri.cli.install_selected_deps', return_value=False), \
             patch('zekniri.cli.deploy_selected_configs') as deploy:
            self.assertFalse(cli.install_configs_workflow('full'))
            deploy.assert_not_called()

    def test_service_failures_are_reported(self):
        with TempEnv() as t:
            (t.home / 'install.sh').touch()
            with patch('zekniri.deploy.tools.shutil.which', return_value='/usr/bin/systemctl'), \
                 patch('zekniri.deploy.tools.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
                self.assertFalse(enable_waybar_service())
                self.assertFalse(install_watcher())

    def test_purge_removes_service_tools_and_owned_link(self):
        with TempEnv() as t:
            unit = t.env.config_dir / 'systemd/user/zekniri-watch.service'
            unit.parent.mkdir(parents=True)
            unit.write_text('[Service]\nExecStart=ZEK-niri watch\n')
            launcher = t.home / '.local/bin/ZEK-menu'
            launcher.write_text('menu')
            package = t.env.data_home / 'ZEKniri/zekniri'
            package.mkdir(parents=True)
            (package / 'menu_app.py').write_text('module')
            (t.env.state_dir / 'waybar-service-owned').touch()
            with patch('zekniri.state.uninstall.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
                self.assertTrue(uninstall_zekniri('purge'))
                calls = [c.args[0] for c in run.call_args_list]
                self.assertIn(['systemctl', '--user', 'disable', '--now', 'zekniri-watch.service'], calls)
                self.assertIn(['systemctl', '--user', 'disable', '--now', 'waybar.service'], calls)
            self.assertFalse(unit.exists())
            self.assertFalse(launcher.exists())
            self.assertFalse(package.exists())

    def test_failed_service_stop_preserves_data_and_tools(self):
        with TempEnv() as t:
            unit = t.env.config_dir / 'systemd/user/zekniri-watch.service'
            unit.parent.mkdir(parents=True)
            unit.write_text('service')
            launcher = t.home / '.local/bin/ZEK-menu'
            launcher.write_text('menu')
            with patch('zekniri.state.uninstall.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
                self.assertFalse(uninstall_zekniri('purge'))
            self.assertTrue(unit.exists())
            self.assertTrue(launcher.exists())
            self.assertTrue(t.env.state_dir.exists())

    def test_install_service_failure_returns_failure(self):
        with TempEnv() as t:
            self.seed(t, 'waybar')
            with patch('zekniri.cli.sys.stdin.isatty', return_value=False), \
                 patch('zekniri.cli.enable_waybar_service', return_value=False), \
                 patch('zekniri.cli.render_completion_screen') as completion:
                self.assertFalse(cli.install_configs_workflow('config'))
                completion.assert_not_called()

    def test_update_dependency_failure_is_propagated(self):
        with TempEnv(), patch('zekniri.cli.sys.stdin.isatty', return_value=False), \
             patch('zekniri.cli.get_missing_deps', return_value=['missing']), \
             patch('zekniri.cli.install_selected_deps', return_value=False):
            self.assertFalse(cli.check_new_deps_post_update())

    def test_purge_leaves_preexisting_waybar_service_alone(self):
        with TempEnv(), patch('zekniri.state.uninstall.subprocess.run') as run:
            self.assertTrue(uninstall_zekniri('purge'))
            run.assert_not_called()

    def test_rollback_does_not_render_unrelated_or_snapshot_files(self):
        from zekniri.state.backup import backup_configs, rollback_configs
        with TempEnv() as t:
            self.seed(t)
            dest = t.env.config_dir / 'app'
            dest.mkdir()
            (dest / 'conf').write_text('/home/user/saved')
            snapshot = backup_configs(interactive=False)
            other = t.env.config_dir / 'other/conf'
            other.parent.mkdir()
            other.write_text('/home/user/untouched')
            (dest / 'conf').write_text('current')
            self.assertTrue(rollback_configs(snapshot.name))
            self.assertEqual(other.read_text(), '/home/user/untouched')
            self.assertEqual((snapshot / 'app/conf').read_text(), '/home/user/saved')
            self.assertEqual((dest / 'conf').read_text(), f'{t.home}/saved')
