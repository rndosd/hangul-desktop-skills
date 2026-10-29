from pathlib import Path
import hashlib
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import hangul_task as task


def namespace_conditions(path):
    with ZipFile(path) as package:
        root=ET.fromstring(package.read('Contents/header.xml'))
    return [value for node in root.iter() for key,value in node.attrib.items()
            if key.rsplit('}',1)[-1]=='required-namespace']


class CandidateBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source=ROOT/'assets/document-templates/source-library/extra-04.hwpx'
        self.output=Path(self.temp.name)/'edited.hwpx'
        self.original=self.source.read_bytes()
        self.request={
            'schemaVersion':'hwpx.agent-batch/v1',
            'input':{'filename':str(self.source)},
            'output':{'filename':str(self.output),'overwrite':False},
            'expectedRevision':'sha256:'+hashlib.sha256(self.original).hexdigest(),
            'idempotencyKey':'candidate-batch-test','dryRun':False,'quality':'transparent',
            'verificationRequirements':['package','reopen','openSafety','semanticDiff','bytePreservation'],
            'commands':[{'commandId':'title','op':'set',
                         'path':'/section[1]/paragraph[@id="2757524817"]/run[2]',
                         'properties':{'text':'[양식 연결 시험] ','color':'#145C52'}}],
        }

    def test_real_source_dry_run_and_apply_preserve_namespace_conditions(self):
        conditions=namespace_conditions(self.source)
        self.assertIn('http://www.hancom.co.kr/hwpml/2016/paragraph',conditions)
        dry=task.batch(self.request,True)
        self.assertTrue(dry['ok'],dry)
        self.assertFalse(dry['documentPublished'])
        self.assertIsNone(dry['verificationReport']['savePipeline']['outputPath'])
        self.assertFalse(self.request['dryRun'])
        self.assertFalse(self.output.exists())
        result=task.batch(self.request)
        self.assertTrue(result['ok'],result)
        self.assertTrue(result['documentPublished'])
        self.assertEqual(result['output']['filename'],str(self.output))
        self.assertEqual(result['verificationReport']['savePipeline']['outputPath'],str(self.output))
        self.assertEqual(result['outputSha256'],hashlib.sha256(self.output.read_bytes()).hexdigest())
        self.assertEqual(result['documentRevision'],'sha256:'+result['outputSha256'])
        self.assertEqual(self.request['output']['filename'],str(self.output))
        self.assertEqual(namespace_conditions(self.output),conditions)
        self.assertEqual(self.source.read_bytes(),self.original)
        with ZipFile(self.output) as package:
            xml=ET.fromstring(package.read('Contents/section0.xml'))
        texts=''.join(n.text or '' for n in xml.iter() if n.tag.rsplit('}',1)[-1]=='t')
        self.assertIn('[양식 연결 시험]',texts)
        self.assertNotIn('[학생 신청용]',texts)
        self.assertTrue(result['verificationReport']['openSafety']['ok'])

    def test_stale_revision_emits_no_output(self):
        self.request['expectedRevision']='sha256:'+'0'*64
        result=task.batch(self.request)
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'],'BLOCKED')
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(),self.original)

    def test_existing_output_is_preserved(self):
        self.output.write_bytes(b'existing user data')
        with self.assertRaises(ValueError):task.batch(self.request)
        self.assertEqual(self.output.read_bytes(),b'existing user data')

    def test_output_created_during_execution_is_preserved(self):
        task.activate()
        import hwpx_automation.office.agent as api
        real=api.apply_document_commands
        staged=[]
        marker=b'concurrent user data'
        def fault(stage,index):
            if stage=='before_save':self.output.write_bytes(marker)
        def injected(request):
            staged.append(Path(request['output']['filename']))
            return real(request,fault_injector=fault)
        with patch.object(api,'apply_document_commands',injected):
            with self.assertRaises(FileExistsError):task.batch(self.request)
        self.assertEqual(self.output.read_bytes(),marker)
        self.assertEqual(self.source.read_bytes(),self.original)
        self.assertNotEqual(staged[0],self.output)
        self.assertFalse(staged[0].parent.exists())

    def test_source_changed_during_execution_is_not_published(self):
        source=Path(self.temp.name)/'source-copy.hwpx'
        source.write_bytes(self.original)
        self.request['input']['filename']=str(source)
        task.activate()
        import hwpx_automation.office.agent as api
        real=api.apply_document_commands
        changed=self.original+b'changed during execution'
        def fault(stage,index):
            if stage=='before_save':source.write_bytes(changed)
        def injected(request):return real(request,fault_injector=fault)
        with patch.object(api,'apply_document_commands',injected):
            with self.assertRaisesRegex(ValueError,'원본 변경'):task.batch(self.request)
        self.assertFalse(self.output.exists())
        self.assertEqual(source.read_bytes(),changed)
        self.assertEqual(self.source.read_bytes(),self.original)

    def test_source_cannot_be_output(self):
        self.request['output']['filename']=str(self.source)
        with self.assertRaises(ValueError):task.batch(self.request)
        self.assertEqual(self.source.read_bytes(),self.original)

    def test_revision_required(self):
        self.request['expectedRevision']=None
        with self.assertRaises(ValueError):task.batch(self.request)
        self.assertFalse(self.output.exists())

    def test_output_requires_hwpx_extension(self):
        other=self.output.with_suffix('.pdf')
        self.request['output']['filename']=str(other)
        with self.assertRaises(ValueError):task.batch(self.request)
        self.assertFalse(other.exists())


if __name__=='__main__':unittest.main()
