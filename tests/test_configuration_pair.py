from pathlib import Path
import sys, shutil, uuid, unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'plugins/hancom-desktop/skills/hwpx-windows-finalize/scripts'))
import run_native_job as native

class ConfigurationPair(unittest.TestCase):
    def setUp(self):
        self.base=ROOT/('.test-config-'+uuid.uuid4().hex);self.base.mkdir()
        self.skill=self.base/'cache/skills/hwpx-windows-finalize';self.skill.mkdir(parents=True)
        self.home=self.base/'desktop'
    def tearDown(self):
        assert self.base.parent == ROOT and self.base.name.startswith('.test-config-')
        shutil.rmtree(self.base)
    def pair(self,root):
        result=(root/'hwpx-windows-finalize/environment.json',root/'hwpx/environment.json')
        for p in result:p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
        return result
    def test_missing_pair_blocked(self):
        with self.assertRaisesRegex(ValueError,'DESKTOP_NOT_CONFIGURED'):native.configuration_pair(self.skill,self.home)
    def test_plugin_cache_uses_current_desktop_pair(self):
        expected=self.pair(self.home/'skills');self.assertEqual(native.configuration_pair(self.skill,self.home),expected)
    def test_local_candidate_pair_takes_precedence(self):
        expected=self.pair(self.skill.parent);self.pair(self.home/'skills')
        self.assertEqual(native.configuration_pair(self.skill,self.home),expected)
    def test_partial_local_is_never_mixed(self):
        self.pair(self.home/'skills');(self.skill/'environment.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'incomplete local'):native.configuration_pair(self.skill,self.home)
    def test_partial_desktop_is_blocked(self):
        p=self.home/'skills/hwpx/environment.json';p.parent.mkdir(parents=True);p.write_text('{}')
        with self.assertRaisesRegex(ValueError,'DESKTOP_NOT_CONFIGURED'):native.configuration_pair(self.skill,self.home)
    def test_codex_home_is_honored(self):
        expected=self.pair(self.home/'skills')
        with patch.dict(native.os.environ,{'CODEX_HOME':str(self.home)}):
            self.assertEqual(native.configuration_pair(self.skill),expected)

if __name__=='__main__':unittest.main()
