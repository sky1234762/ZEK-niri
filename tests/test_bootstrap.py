import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class BootstrapTests(unittest.TestCase):
    def shell(self, script, environment):
        # Load the actual bootstrap functions, without invoking its root/preflight entry.
        source=(ROOT/'install.sh').read_text().removesuffix('main "$@"\n')
        return subprocess.run(['bash','-c',source+'\n'+script],env={**os.environ,**environment},
                              capture_output=True,text=True,timeout=15)

    def test_completeness_covers_every_python_runtime_module(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'install.sh').touch();(root/'configs').mkdir();(root/'assets').mkdir()
            files=list((ROOT/'zekniri').rglob('*.py'))
            for file in files:
                target=root/file.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.touch()
            result=self.shell('engine_is_complete "$FIXTURE"',{'FIXTURE':temp})
            self.assertEqual(result.returncode,0,result.stderr)
            for name in ['config.py','workflow.py','deploy/tools.py']:
                target=root/'zekniri'/name;target.unlink()
                with self.subTest(name=name):
                    self.assertNotEqual(self.shell('engine_is_complete "$FIXTURE"',{'FIXTURE':temp}).returncode,0)
                target.touch()

    def test_failed_clone_or_validation_preserves_previous_cache(self):
        for body in ['return 1','mkdir -p "$2"; return 0']:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as temp:
                cache=Path(temp)/'cache with spaces';cache.mkdir();(cache/'keep').write_text('original')
                script='CACHE_DIR="$FIXTURE"\ngit_clone_timeout() { '+body+'; }\nengine_is_complete() { return 1; }\nreplace_cached_engine'
                result=self.shell(script,{'FIXTURE':str(cache)})
                self.assertNotEqual(result.returncode,0)
                self.assertEqual((cache/'keep').read_text(),'original')
                self.assertEqual(list(Path(temp).glob('.zekniri-bootstrap.*')),[])

    def test_successful_replacement_retains_old_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            cache=Path(temp)/'cache';cache.mkdir();(cache/'keep').write_text('original')
            script='''CACHE_DIR="$FIXTURE"
git_clone_timeout() { mkdir -p "$2"; touch "$2/ready"; }
engine_is_complete() { test -f "$1/ready"; }
replace_cached_engine
'''
            result=self.shell(script,{'FIXTURE':str(cache)})
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue((cache/'ready').exists())
            self.assertEqual(len(list(Path(temp).glob('.zekniri-previous.*/repo/keep'))),1)
