import subprocess
import unittest
from unittest.mock import patch

from tests.utils import TempEnv
from zekniri import deps
from zekniri.deploy.deploy import deploy_selected_configs


class InstallEngineTests(unittest.TestCase):
    def test_dependency_success_invalidates_package_cache(self):
        with TempEnv(), patch('zekniri.deps.shutil.which',return_value='/usr/bin/pacman'), \
                patch('zekniri.deps.timed_run',return_value=subprocess.CompletedProcess([],0)):
            deps._PACMAN_INSTALLED_CACHE={'old'}
            self.assertTrue(deps.install_selected_deps(['new']))
            self.assertIsNone(deps._PACMAN_INSTALLED_CACHE)

    def test_state_failure_reports_app_instead_of_crashing(self):
        with TempEnv() as t:
            app=t.env.configs_src/'app';app.mkdir();(app/'config').write_text('new')
            with patch('zekniri.deploy.deploy._deploy_state_files',side_effect=PermissionError('denied')):
                self.assertEqual(deploy_selected_configs(items_to_deploy=['app']),['app'])

    def test_noctalia_deploy_does_not_touch_separately_installed_plugins(self):
        with TempEnv() as t:
            source=t.env.configs_src/'noctalia';source.mkdir();(source/'config.toml').write_text('enabled=true')
            installed=t.env.data_home/'noctalia/plugins/separate-plugin';installed.mkdir(parents=True)
            (installed/'marker').write_text('preserve')
            self.assertEqual(deploy_selected_configs(items_to_deploy=['noctalia']),[])
            self.assertEqual((installed/'marker').read_text(),'preserve')
            self.assertEqual(list(installed.parent.iterdir()),[installed])
