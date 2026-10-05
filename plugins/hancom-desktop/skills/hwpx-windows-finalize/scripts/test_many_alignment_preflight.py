"""Invalid write requests must fail before any COM worker is launched."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


class ManyWritePreflightTest(unittest.TestCase):
    def test_invalid_hash_range_and_legacy_scope_do_not_launch_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/'source.hwpx'
            source.write_bytes(b'not-a-real-document: never opened')
            sha=hashlib.sha256(source.read_bytes()).hexdigest()
            for index,(operation,expected,hash_value,reason) in enumerate([
                ('SetAlignmentMany','3','0'*64,'matching source hash'),
                ('SetAlignmentMany','0',sha,'only verified 3 to 2'),
                ('SetAlignment','3',sha,'legacy alignment range'),
            ]):
                run=root/f'run{index}'
                args=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_name('Invoke-HancomCell.ps1')),
                      '-Operation',operation,'-InputPath',str(source),'-TargetText','A','-ParentText','B',
                      '-Expected',expected,'-Alignment','2','-ExpectedSourceSha256',hash_value,
                      '-OutputPath',str(root/f'out{index}.hwpx'),'-PdfPath',str(root/f'out{index}.pdf'),
                      '-RunDirectory',str(run)]
                result=subprocess.run(args,capture_output=True,timeout=15)
                self.assertTrue((run/'receipt.json').exists(),repr(result.stderr))
                receipt=json.loads((run/'receipt.json').read_text(encoding='utf-8-sig'))
                self.assertEqual(receipt['status'],'FAIL_PREFLIGHT')
                self.assertIn(reason,receipt['failure']['message'])
                self.assertIsNone(receipt['worker'])
                self.assertFalse((run/'job.json').exists())
                self.assertFalse((root/f'out{index}.hwpx').exists())
                self.assertTrue(receipt['sourceUnchanged'])


if __name__=='__main__':unittest.main(verbosity=2)
