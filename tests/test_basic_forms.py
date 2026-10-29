"""Current entrypoints expose three prepared plans and reject retired IDs."""
from pathlib import Path
import json
import subprocess
import sys
import unittest

SKILL=Path(__file__).resolve().parents[1]/'plugins/hancom-desktop/skills/hwpx'
IDS=['plan-school','plan-education','plan-project']

class BasicForms(unittest.TestCase):
    def cli(self,script,*args):
        return subprocess.run([sys.executable,'-X','utf8','-B',str(SKILL/'scripts'/script),*args],capture_output=True,text=True,encoding='utf-8')

    def test_source_selection_only_prepared_plans(self):
        result=self.cli('select_document_template.py','--all')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual([x['id'] for x in json.loads(result.stdout)['templates']],IDS)
        for old in ['source-A','style-01','extra-04']:
            with self.subTest(old=old):
                self.assertNotEqual(self.cli('select_document_template.py','--id',old).returncode,0)

    def test_default_fill_uses_verified_prepared_inputs(self):
        result=self.cli('select_document_block.py','--list','--summary')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual([x['id'] for x in json.loads(result.stdout)['blocks']],IDS)
        for key in IDS:
            with self.subTest(plan=key):
                result=self.cli('hangul_task.py','fill','--template',key)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertEqual(json.loads(result.stdout)['status'],'PREPARED_FORM')

    def test_retired_assets_excluded_and_origins_preserved(self):
        root=SKILL/'assets/document-templates'
        for name in ['blocks.json','component-index.json']:
            self.assertFalse((root/name).exists())
        for name in ['reusable-blocks','reusable-forms','component-previews']:
            self.assertFalse(any(p.is_file() for p in (root/name).rglob('*')))
        self.assertEqual(sorted(p.name for p in (root/'source-library').glob('*.hwpx')),['source-A.hwpx','source-B.hwpx','source-C.hwpx'])

if __name__=='__main__':unittest.main()
