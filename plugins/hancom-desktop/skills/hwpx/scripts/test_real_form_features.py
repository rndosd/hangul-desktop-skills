# SPDX-License-Identifier: Apache-2.0
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E
from zipfile import ZipFile
from hwpx import HwpxDocument
from safe_edit import inspect_targets,make_plan,apply_plan,digest
from form_fill import inspect_form,make_form_plan,apply_form,validate_request
from safe_format import apply_format,SCHEMA
from hwpx.opc import xml_utils
from test_form_fill import field,request
from test_safe_edit import read_document


class RealFormFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.source=Path(self.temp.name)/'source.hwpx';self.output=Path(self.temp.name)/'candidate.hwpx'

    def save(self,doc):doc.save_to_path(self.source);doc.close();self.original=self.source.read_bytes()

    def test_leading_text_free_section_metadata_title_preserved(self):
        d=HwpxDocument.new();d.sections[0].paragraphs[0].add_run('FIRST TITLE');self.save(d)
        with ZipFile(self.source) as z:parts={n:z.read(n) for n in z.namelist()}
        root=E.fromstring(parts['Contents/section0.xml']);metadata=root[0].find('{*}run')
        for t in metadata.findall('{*}t'):metadata.remove(t)
        parts['Contents/section0.xml']=E.tostring(root,encoding='utf-8')
        with ZipFile(self.source,'w') as z:
            for n,data in parts.items():z.writestr(n,data)
        self.original=self.source.read_bytes();listing=inspect_targets(self.source,'FIRST TITLE')
        self.assertTrue(listing['targets'][0]['supported'])
        apply_plan(self.source,self.output,make_plan(listing,[listing['targets'][0]['target_id']],'NEW TITLE'))
        before,shape_before,other_before=read_document(self.source);after,shape_after,other_after=read_document(self.output)
        self.assertEqual(shape_before,shape_after);self.assertEqual(other_before,other_after)
        self.assertEqual([text for text,_ in after],['NEW TITLE']);self.assertEqual(self.original,self.source.read_bytes())

    def test_merged_label_explicit_row_offset_changes_only_chosen_neighbor(self):
        d=HwpxDocument.new();t=d.add_table(3,2);t.merge_cells(0,0,2,0);t.cell(0,0).set_text('내 용')
        for row in range(3):t.cell(row,1).set_text('')
        self.save(d);req=request(field('내 용',target_row_offset=1))
        plan=make_form_plan(inspect_form(self.source,req));self.assertEqual(plan['fields'][0]['targets'][0]['target_cell']['row'],2)
        apply_form(self.source,self.output,plan)
        texts=[text for text,_ in read_document(self.output)[0]];self.assertEqual(texts.count('합성 제목'),1)
        self.assertEqual(self.original,self.source.read_bytes())

    def test_merged_label_explicit_column_offset(self):
        d=HwpxDocument.new();t=d.add_table(2,2);t.merge_cells(0,0,0,1);t.cell(0,0).set_text('내 용');self.save(d)
        plan=make_form_plan(inspect_form(self.source,request(field('내 용',direction='below',target_column_offset=1))))
        self.assertEqual(plan['fields'][0]['targets'][0]['target_cell']['column'],2)
        apply_form(self.source,self.output,plan)

    def test_offset_wrong_direction_bool_negative_and_outside_span_block(self):
        for kwargs in ({'target_row_offset':-1},{'target_row_offset':True},{'target_column_offset':0}):
            with self.assertRaises(ValueError):validate_request(request(field(**kwargs)))
        d=HwpxDocument.new();t=d.add_table(1,2);t.cell(0,0).set_text('제목');self.save(d)
        self.assertEqual(inspect_form(self.source,request(field(target_row_offset=1)))['status'],'BLOCKED')

    def format_fixture(self):
        d=HwpxDocument.new();p=d.add_paragraph('',include_run=False);p.add_run('FORMAT TEXT',bold=True,color='#225588');d.add_paragraph('KEEP');self.save(d)
        target=inspect_targets(self.source,'FORMAT TEXT')['targets'][0]
        return {'schema':SCHEMA,'source_sha256':digest(self.source),'targets':[{'part':target['part'],'paragraph_path':target['paragraph_path'],
                'expected_text':'FORMAT TEXT','letter_spacing':-2,'ratio':98,'reason':'Explicit bounded comparison candidate'}]}

    def test_bounded_format_keeps_text_font_height_and_other_styles(self):
        plan=self.format_fixture();result=apply_format(self.source,self.output,plan)
        self.assertFalse(result['font_size_reduced']);self.assertTrue(result['all_unrequested_format_and_text_preserved'])
        self.assertEqual([text for text,_ in read_document(self.source)[0]],[text for text,_ in read_document(self.output)[0]])
        self.assertEqual(self.original,self.source.read_bytes());self.assertEqual(result['native_render'],'not_checked')

    def test_format_excessive_compression_stale_and_duplicate_block(self):
        good=self.format_fixture()
        for mutation in (lambda p:p['targets'][0].update(ratio=70),lambda p:p['targets'][0].update(letter_spacing=-20),
                         lambda p:p.update(source_sha256='0'*64),lambda p:p['targets'].append(copy.deepcopy(p['targets'][0]))):
            plan=copy.deepcopy(good);mutation(plan)
            with self.assertRaises(ValueError):apply_format(self.source,self.output,plan)
            self.assertFalse(self.output.exists());self.assertEqual(self.original,self.source.read_bytes())

    def test_format_api_unrequested_text_corruption_rejected(self):
        plan=self.format_fixture();save=HwpxDocument.save_to_path
        def corrupt(doc,path):
            for p in doc.paragraphs:
                for r in p.runs:
                    if r.text=='KEEP':r.replace_text('KEEP','LOST')
            save(doc,path)
        with patch.object(HwpxDocument,'save_to_path',corrupt):
            with self.assertRaisesRegex(ValueError,'preservation mismatch'):apply_format(self.source,self.output,plan)
        self.assertFalse(self.output.exists());self.assertEqual(self.original,self.source.read_bytes())

    def test_format_dry_run_and_existing_output_protected(self):
        plan=self.format_fixture();result=apply_format(self.source,self.output,plan,dry_run=True)
        self.assertFalse(result['published']);self.assertFalse(self.output.exists())
        self.output.write_bytes(b'KEEP_EXISTING')
        with self.assertRaises(ValueError):apply_format(self.source,self.output,plan)
        self.assertEqual(self.output.read_bytes(),b'KEEP_EXISTING')

    def test_version_uri_literal_preserved_and_adapter_restored(self):
        plan=self.format_fixture()
        with ZipFile(self.source) as z:parts={n:z.read(n) for n in z.namelist()}
        root=E.fromstring(parts['Contents/header.xml']);case=root.find('.//{*}case')
        case.set('{http://www.hancom.co.kr/hwpml/2011/paragraph}required-namespace','http://www.hancom.co.kr/hwpml/2016/paragraph')
        parts['Contents/header.xml']=E.tostring(root,encoding='utf-8')
        with ZipFile(self.source,'w') as z:
            for n,data in parts.items():z.writestr(n,data)
        self.original=self.source.read_bytes();plan['source_sha256']=digest(self.source)
        normalization=xml_utils.normalize_hwpml_namespaces
        apply_format(self.source,self.output,plan)
        self.assertIs(xml_utils.normalize_hwpml_namespaces,normalization)
        with ZipFile(self.output) as z:after=E.fromstring(z.read('Contents/header.xml'))
        self.assertIn('http://www.hancom.co.kr/hwpml/2016/paragraph',[v for n in after.iter() for k,v in n.attrib.items() if k.endswith('required-namespace')])
        self.assertEqual(self.original,self.source.read_bytes())

    def test_active_strikeout_is_preserved(self):
        d=HwpxDocument.new();d.add_paragraph('',include_run=False).add_run('FORMAT TEXT',strike=True);self.save(d)
        t=inspect_targets(self.source,'FORMAT TEXT')['targets'][0]
        plan={'schema':SCHEMA,'source_sha256':digest(self.source),'targets':[{'part':t['part'],'paragraph_path':t['paragraph_path'],
              'expected_text':'FORMAT TEXT','letter_spacing':-2,'ratio':98,'reason':'Preserve active strikeout in new style clone'}]}
        apply_format(self.source,self.output,plan)
        with ZipFile(self.output) as z:root=E.fromstring(z.read('Contents/header.xml'))
        self.assertTrue(any(n.get('shape')!='NONE' for n in root.findall('.//{*}strikeout')))


if __name__=='__main__':unittest.main(verbosity=2)
