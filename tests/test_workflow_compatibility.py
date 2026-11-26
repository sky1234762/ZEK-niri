import contextlib,io,json,unittest
from pathlib import Path
from unittest.mock import patch
from tests.utils import TempEnv
from zekniri import cli,i18n
from zekniri.deploy.assets import AssetDeployResult
from zekniri.deploy.tools import ToolDeployResult

SCENARIOS = {
 'full': dict(configs=['niri','waybar','noctalia'], assets=True, zeklive=True, backup=True),
 'config': dict(configs=['kitty'], assets=False, zeklive=False, backup=False),
 'assets': dict(configs=[], assets=True, zeklive=False, backup=True),
 'tools': dict(configs=[], assets=False, zeklive=True, backup=False),
 'cancel': None,
 'empty': dict(configs=[], assets=False, zeklive=False, backup=True),
 'deploy_fail': dict(configs=['kitty'], assets=False, zeklive=False, backup=False),
 'service_fail': dict(configs=['waybar','noctalia'], assets=True, zeklive=True, backup=True),
 'dependency_fail': dict(configs=['kitty'], assets=False, zeklive=False, backup=False),
 'update': dict(configs=['waybar','noctalia'], assets=True, zeklive=False, backup=True),
}

def capture(name,language):
 chosen=SCENARIOS[name];events=[];out=io.StringIO();err=io.StringIO()
 with TempEnv(),contextlib.ExitStack() as stack:
  i18n.set_language(language)
  def record(label,result):
   def call(*args,**kw):
    events.append([label,args,kw]);return result
   return call
  hooks={'deploy_runtime_conf':True,'run_master_component_menu':chosen,
         'get_missing_deps':['dependency'] if name in ('full','dependency_fail') else [],
         'install_selected_deps':name!='dependency_fail',
         'deploy_selected_configs':['kitty'] if name=='deploy_fail' else [],
         'deploy_assets':AssetDeployResult(), 'enable_waybar_service':name!='service_fail',
         'install_watcher':name!='service_fail','_service_setup_available':True,
         'disable_native_bar':True,'enable_native_bar':True,
         'deploy_zeklive':ToolDeployResult(), 'choose_and_write_output_modes':None,
         'render_completion_screen':None,'discover_config_items': chosen['configs'] if chosen else [],
         'assets_present':bool(chosen and chosen['assets']),'zeklive_present':bool(chosen and chosen['zeklive'])}
  for hook,result in hooks.items():stack.enter_context(patch.object(cli,hook,side_effect=record(hook,result)))
  stack.enter_context(patch.object(cli.sys.stdin,'isatty',return_value=True))
  with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
   result=cli.offer_overwrite_upgrade('--force') if name=='update' else cli.install_configs_workflow('full' if name in ('full','dependency_fail') else 'config')
 def plain(obj):
  if hasattr(obj,'__dataclass_fields__'):return vars(obj)
  raise TypeError(type(obj))
 return json.loads(json.dumps({'result':result,'stdout':out.getvalue(),'stderr':err.getvalue(),'events':events},default=plain))

class WorkflowCompatibilityTests(unittest.TestCase):
    def test_recorded_workflow_output_and_side_effect_order(self):
        baseline=json.loads((Path(__file__).parent/'fixtures/install_workflow.json').read_text())
        for key,expected in baseline.items():
            language,name=key.split(':')
            with self.subTest(language=language,scenario=name):
                self.assertEqual(capture(name,language),expected)
