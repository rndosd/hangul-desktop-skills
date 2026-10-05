"""Focused completion-gate tests. COM receipts are synthetic fixtures, not COM proof."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

import pymupdf
import hancom_completion_gate as g


def save(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


def hwpx(path, alignment='0', text='alpha'):
    with ZipFile(path, 'w') as z:
        z.writestr('Contents/content.hpf','<package><manifest><item id="s0" href="Contents/section0.xml"/></manifest><spine><itemref idref="s0"/></spine></package>')
        z.writestr('Contents/section0.xml', f'<section><tbl><p align="{alignment}"><t>{text}</t></p></tbl></section>')
        z.writestr('BinData/a.bin', b'unchanged-image')


class CompletionGateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.final, self.pdf, self.run, self.bundle = [self.root/n for n in ('source.hwpx','final.hwpx','final.pdf','run','bundle')]
        hwpx(self.source)
        g.prepare(self.bundle, self.source, self.final, self.pdf, self.run)
        hwpx(self.final, alignment='2')
        with pymupdf.open() as doc:
            doc.new_page().insert_text((72,72), 'alpha')
            doc.save(self.pdf)
        self.run.mkdir()
        save(self.run/'job.json', {'input':str(self.source),'output':str(self.final),'pdf':str(self.pdf)})
        self.receipt = {'status':'PASS_COM','sourceUnchanged':True,'worker':{'firstOpen':True,'saveAs':True,'reopen':True,'pdfExport':True,'cleanup':{'quit':True}},'cleanup':{'forced':False,'remaining':[]},'artifacts':[g.ref(self.final),g.ref(self.pdf)]}
        save(self.run/'receipt.json',self.receipt)
        g.collect(self.bundle)
        self.review = g.load(self.bundle/'review-template.json')
        self.review['reviewer']='synthetic test reviewer'
        self.review['reviewedAt']='2026-09-08T00:00:00+09:00'
        self.review['preservation']['performed']=True
        for item in self.review['preservation']['checks'].values():
            item.update(outcome='pass',observation='Synthetic fixture: exact content and intended alignment verified.')
        for item in self.review['preservation']['reviewedMembers']:
            item['reason']='Synthetic fixture: only the planned alignment attribute changed.'
        self.review['visual']['performed']=True
        for item in self.review['visual']['pages']:
            item.update(outcome='pass',observation='Synthetic review record for testing gate mechanics only.')
        self.review_path=self.bundle/'review.json'
        save(self.review_path,self.review)

    def assert_gate(self, reason, state='blocked'):
        with self.assertRaises(g.GateError) as ctx:
            g.check(self.bundle,self.review_path)
        self.assertEqual(ctx.exception.state,state)
        self.assertIn(reason,ctx.exception.reason)

    def test_complete_bound_record(self):
        self.assertEqual(g.check(self.bundle,self.review_path)['status'],'complete')

    def test_lone_pass_rejected(self):
        save(self.review_path,{'status':'PASS'})
        self.assert_gate('review_not_bound')

    def test_missing_review_pending(self):
        self.review_path.unlink()
        self.assert_gate('missing:','pending')

    def test_unperformed_review_pending(self):
        self.review['visual']['performed']=False
        save(self.review_path,self.review)
        self.assert_gate('reviews_not_performed','pending')

    def test_unreviewed_difference_pending(self):
        self.review['preservation']['reviewedMembers']=[]
        save(self.review_path,self.review)
        self.assert_gate('unreviewed_structural','pending')

    def test_missing_page_pending(self):
        self.review['visual']['pages']=[]
        save(self.review_path,self.review)
        self.assert_gate('visual_pages_missing','pending')

    def test_visual_failure_blocks(self):
        self.review['visual']['pages'][0]['outcome']='fail'
        save(self.review_path,self.review)
        self.assert_gate('visual_review_failed')

    def test_changed_source_blocks(self):
        hwpx(self.source,text='changed')
        self.assert_gate('file_changed')

    def test_changed_final_blocks(self):
        hwpx(self.final,text='changed')
        self.assert_gate('COM_artifact_hash_mismatch')

    def test_changed_pdf_blocks(self):
        with self.pdf.open('ab') as f: f.write(b'changed')
        self.assert_gate('COM_artifact_hash_mismatch')

    def test_changed_page_image_blocks(self):
        Path(self.review['visual']['pages'][0]['image']['path']).write_bytes(b'fake')
        self.assert_gate('file_changed')

    def test_changed_receipt_blocks(self):
        self.receipt['worker']['reopen']=False
        save(self.run/'receipt.json',self.receipt)
        self.assert_gate('COM_steps_not_performed')

    def test_wrong_job_path_blocks(self):
        save(self.run/'job.json',{'input':str(self.final),'output':str(self.final),'pdf':str(self.pdf)})
        self.assert_gate('COM_job_path_mismatch')

    def test_preservation_failure_blocks(self):
        self.review['preservation']['checks']['non_target_structure']['outcome']='fail'
        save(self.review_path,self.review)
        self.assert_gate('preservation_failed')

    def test_empty_observation_pending(self):
        self.review['visual']['pages'][0]['observation']='PASS'
        save(self.review_path,self.review)
        self.assert_gate('visual_page_not_checked','pending')

    def test_modified_diff_file_blocks(self):
        save(self.bundle/'differences.json',{'status':'PASS'})
        self.assert_gate('file_changed')

    def test_prepare_refuses_existing_outputs(self):
        with self.assertRaises(g.GateError):
            g.prepare(self.root/'another_bundle',self.source,self.final,self.pdf,self.root/'another_run')

    def test_native_text_change_blocks_collect(self):
        other=self.root/'other_bundle'
        other.mkdir()
        save(other/'plan.json',g.load(self.bundle/'plan.json'))
        hwpx(self.final,text='lost original text')
        self.receipt['artifacts']=[g.ref(self.final),g.ref(self.pdf)]
        save(self.run/'receipt.json',self.receipt)
        result=g.collect(other)
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['reason'],'native_content_counts_or_assets_changed')
        self.assertTrue((other/'review-template.json').is_file())
        with self.assertRaises(g.GateError) as ctx:
            g.check(other,other/'review-template.json')
        self.assertEqual(ctx.exception.reason,'native_content_counts_or_assets_changed')

    def test_general_finalize_receipt_supported_and_bound(self):
        plan=g.load(self.bundle/'plan.json')
        receipt=copy.deepcopy(self.receipt)
        receipt.update(receipt.pop('worker'))
        receipt.update(evidenceSchema='hwpx.hancom-finalize.v2',status='PASS_FULL',mode='SaveAs',sourceSha256Before=plan['source']['sha256'],sourceSha256After=plan['source']['sha256'],candidatePath=str(self.source),finalPath=str(self.final))
        receipt['cleanup'].update(owned=True,forced=False,remaining=[])
        save(self.run/'receipt.json',receipt)
        self.assertEqual(g.native_evidence(plan)['final'],g.ref(self.final))
        receipt['sourceSha256Before']='0'*64
        save(self.run/'receipt.json',receipt)
        with self.assertRaises(g.GateError) as ctx:g.native_evidence(plan)
        self.assertEqual(ctx.exception.reason,'COM_source_hash_mismatch')

    def test_legacy_lone_pass_full_not_accepted(self):
        receipt=copy.deepcopy(self.receipt)
        receipt['status']='PASS_FULL'
        save(self.run/'receipt.json',receipt)
        self.assert_gate('COM_not_successful')

    def test_spine_order_changes_are_not_filename_sorted(self):
        def make(path,order):
            with ZipFile(path,'w') as z:
                z.writestr('Contents/content.hpf','<package><manifest><item id="a" href="Contents/section0.xml"/><item id="b" href="Contents/section1.xml"/></manifest><spine>'+''.join(f'<itemref idref="{x}"/>' for x in order)+'</spine></package>')
                z.writestr('Contents/section0.xml','<section><p><t>first</t></p></section>')
                z.writestr('Contents/section1.xml','<section><p><t>second</t></p></section>')
        make(self.source,'ab');make(self.final,'ba')
        comparison=g.compare(self.source,self.final)
        self.assertFalse(comparison['invariants']['sections'])
        self.assertFalse(comparison['invariants']['texts'])
        self.assertEqual(g.read_package(self.final)['texts'],['second','first'])

    def test_binary_rename_preserves_bytes_and_reference_but_swap_blocks(self):
        def make(path,renamed=False,swap=False):
            names=['BinData/new2.JPG','BinData/new1.PNG'] if renamed else ['BinData/a.png','BinData/b.jpg']
            ids=['newA','newB'] if renamed else ['a','b']
            with ZipFile(path,'w') as z:
                z.writestr('Contents/content.hpf','<package><manifest><item id="s0" href="Contents/section0.xml"/>'+''.join(f'<item id="{i}" href="{n}"/>' for i,n in zip(ids,names))+'</manifest><spine><itemref idref="s0"/></spine></package>')
                z.writestr('Contents/section0.xml',f'<section><pic binaryItemIDRef="{ids[1] if swap else ids[0]}"/></section>')
                z.writestr(names[0],b'asset A');z.writestr(names[1],b'asset B')
        make(self.source);make(self.final,True)
        comparison=g.compare(self.source,self.final)
        self.assertFalse(comparison['binaryPathsEqual'])
        self.assertTrue(all(comparison['invariants'].values()))
        self.assertTrue(comparison['changes'])
        make(self.final,True,True)
        comparison=g.compare(self.source,self.final)
        self.assertTrue(comparison['invariants']['binaryPayloads'])
        self.assertFalse(comparison['invariants']['binaryReferences'])


class ControlPreservationTest(unittest.TestCase):
    def test_missing_changed_and_reordered_controls_fail_invariant(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/'a.hwpx', Path(tmp)/'b.hwpx'
            def make(path, controls):
                with ZipFile(path, 'w') as z:
                    z.writestr('Contents/content.hpf', '<package><manifest><item id="s" href="Contents/section0.xml"/></manifest><spine><itemref idref="s"/></spine></package>')
                    z.writestr('Contents/section0.xml', '<section><p><run>'+controls+'<t>same</t></run></p></section>')
            first='<ctrl><pageNum pos="BOTTOM_CENTER"/></ctrl>'
            second='<ctrl><pageNum pos="TOP_RIGHT"/></ctrl>'
            make(a,first+second)
            make(b,first+second)
            self.assertTrue(g.compare(a,b)['invariants']['controls'])
            for changed in ('',first,second+first,first+first):
                make(b,changed)
                result=g.compare(a,b)
                self.assertTrue(result['invariants']['texts'])
                self.assertTrue(result['invariants']['counts'])
                self.assertFalse(result['invariants']['controls'])


if __name__=='__main__':
    unittest.main(verbosity=2)
