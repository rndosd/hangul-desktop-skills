# SPDX-License-Identifier: Apache-2.0
"""Synthetic form contracts: exact request coverage and mandatory preservation."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E
from zipfile import ZipFile

from hwpx import HwpxDocument
from hwpx.oxml import HwpxOxmlRun
from form_fill import REQUEST, apply_form, inspect_form, make_form_plan, validate_request
from diagnose_edit import diagnose
from test_safe_edit import read_document


def field(label='제목', values=None, **kwargs):
    result={'id':label,'label':label,'direction':'right','expected_occurrences':1,
            'paragraphs':[1],'values':values if values is not None else [['합성 제목']]}
    result.update(kwargs)
    return result


def request(*fields):
    return {'schema':REQUEST,'fields':list(fields)}


class FormFillTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source.hwpx';self.output=self.root/'filled.hwpx'

    def save(self,doc):
        doc.save_to_path(self.source);doc.close();self.original=self.source.read_bytes()

    def basic(self,rows=1):
        doc=HwpxDocument.new();table=doc.add_table(rows,2)
        for row in range(rows):
            table.cell(row,0).set_text('제목');table.cell(row,1).set_text('')
        return doc,table

    def plan(self,req):
        return make_form_plan(inspect_form(self.source,req))

    def assert_changes(self,changes):
        before,shape_before,other_before=read_document(self.source)
        after,shape_after,other_after=read_document(self.output)
        expected=[text for text,_ in before]
        for index,value in changes.items():expected[index]=value
        self.assertEqual([text for text,_ in after],expected)
        self.assertEqual([styles for _,styles in before],[styles for _,styles in after])
        self.assertEqual(shape_before,shape_after);self.assertEqual(other_before,other_after)
        self.assertEqual(self.source.read_bytes(),self.original)

    def assert_request_blocked(self,req,reason):
        inspection=inspect_form(self.source,req)
        self.assertEqual(inspection['status'],'BLOCKED')
        self.assertIn(reason,json.dumps(inspection,ensure_ascii=False))
        with self.assertRaises(ValueError):make_form_plan(inspection)
        self.assertFalse(self.output.exists());self.assertEqual(self.source.read_bytes(),self.original)

    def assert_plan_blocked(self,plan,reason):
        with self.assertRaisesRegex((ValueError,OSError),reason):apply_form(self.source,self.output,plan)
        self.assertFalse(self.output.exists());self.assertEqual(self.source.read_bytes(),self.original)

    def test_exact_label_fills_existing_blank_run(self):
        doc,table=self.basic();self.save(doc);receipt=apply_form(self.source,self.output,self.plan(request(field())))
        self.assertEqual(receipt['requested_fields'],1);self.assertEqual(receipt['requested_paragraphs'],1)
        self.assertEqual(receipt['native_render'],'not_checked')
        self.assertEqual(receipt['completion'],'filled_candidate_native_pending')
        self.assert_changes({3:'합성 제목'})

    def test_multiple_existing_paragraphs_keep_unselected_notes(self):
        doc,table=self.basic();cell=table.cell(0,1);cell.add_paragraph('주의문 유지');cell.add_paragraph('');self.save(doc)
        req=request(field(values=[['첫 내용','둘째 내용']],paragraphs=[1,3]))
        apply_form(self.source,self.output,self.plan(req));self.assert_changes({3:'첫 내용',5:'둘째 내용'})

    def test_repeat_labels_require_exact_count_and_order(self):
        doc,_=self.basic(rows=3);self.save(doc)
        req=request(field(values=[['첫 항목'],['둘째 항목'],['셋째 항목']],expected_occurrences=3))
        receipt=apply_form(self.source,self.output,self.plan(req));self.assertEqual(receipt['resolved_occurrences'],3)
        self.assert_changes({3:'첫 항목',5:'둘째 항목',7:'셋째 항목'})

    def test_duplicate_label_is_not_silently_first_selected(self):
        doc,_=self.basic(rows=2);self.save(doc)
        self.assert_request_blocked(request(field()),'label_occurrence_count_mismatch')

    def test_missing_one_field_blocks_whole_request(self):
        doc,_=self.basic();self.save(doc)
        self.assert_request_blocked(request(field(),field('없는 라벨',id='missing')),'found 0')

    def test_repeat_values_count_and_per_occurrence_slots_exact(self):
        for req in (request(field(expected_occurrences=2)),
                    request(field(values=[['하나']],paragraphs=[1,2]))):
            with self.assertRaises(ValueError):validate_request(req)

    def test_explicit_table_selector_disambiguates_same_label(self):
        doc,table=self.basic();other=doc.add_table(1,2);other.cell(0,0).set_text('제목');other.cell(0,1).set_text('');self.save(doc)
        req=request(field(table=2));apply_form(self.source,self.output,self.plan(req));self.assert_changes({6:'합성 제목'})

    def test_section_selector_disambiguates_repeated_form(self):
        doc,_=self.basic();section=doc.add_section();other=doc.add_table(1,2,section=section)
        other.cell(0,0).set_text('제목');other.cell(0,1).set_text('');self.save(doc)
        req=request(field(section=2));apply_form(self.source,self.output,self.plan(req))
        before=[t for t,_ in read_document(self.source)[0]];self.assert_changes({len(before)-1:'합성 제목'})

    def test_label_split_over_styled_runs_matches_exact_visible_text(self):
        doc,table=self.basic();cell=table.cell(0,0);cell.set_text('')
        p=cell.paragraphs[0];p.add_run('제',bold=True);p.add_run('목',italic=True);self.save(doc)
        apply_form(self.source,self.output,self.plan(request(field())));self.assert_changes({3:'합성 제목'})

    def test_merged_label_and_target_owner_are_preserved(self):
        doc=HwpxDocument.new();t=doc.add_table(2,3);t.merge_cells(0,0,1,0);t.cell(0,0).set_text('제목')
        t.merge_cells(0,1,1,2);t.cell(0,1).set_text('');self.save(doc)
        plan=self.plan(request(field()));scope=plan['fields'][0]['targets'][0]['target_cell']
        self.assertEqual((scope['row_span'],scope['column_span']),(2,2))
        apply_form(self.source,self.output,plan);self.assert_changes({3:'합성 제목'})

    def test_below_neighbor_uses_full_merged_boundary(self):
        doc=HwpxDocument.new();t=doc.add_table(2,2);t.merge_cells(0,0,0,1);t.cell(0,0).set_text('제목')
        t.merge_cells(1,0,1,1);t.cell(1,0).set_text('');self.save(doc)
        apply_form(self.source,self.output,self.plan(request(field(direction='below'))));self.assert_changes({3:'합성 제목'})

    def test_merged_boundary_with_two_targets_is_ambiguous(self):
        doc=HwpxDocument.new();t=doc.add_table(2,2);t.merge_cells(0,0,0,1);t.cell(0,0).set_text('제목')
        t.cell(1,0).set_text('');t.cell(1,1).set_text('');self.save(doc)
        self.assert_request_blocked(request(field(direction='below')),'multiple_target_cells')

    def test_target_at_table_edge_is_missing(self):
        doc=HwpxDocument.new();doc.add_table(1,1).cell(0,0).set_text('제목');self.save(doc)
        self.assert_request_blocked(request(field()),'neighbor_missing')

    def test_nonempty_field_requires_explicit_replace_and_keeps_runs(self):
        doc,table=self.basic();p=table.cell(0,1).paragraphs[0];p.add_run('기존',bold=True);p.add_run('문구',italic=True);self.save(doc)
        self.assert_request_blocked(request(field()),'nonempty_target')
        apply_form(self.source,self.output,self.plan(request(field(allow_replace=True))));self.assert_changes({3:'합성 제목'})

    def test_blank_multiple_runs_insert_into_first_and_keep_styles(self):
        doc,table=self.basic();p=table.cell(0,1).paragraphs[0];p.add_run('',bold=True);p.add_run('',italic=True);self.save(doc)
        receipt=apply_form(self.source,self.output,self.plan(request(field())))
        self.assertEqual(len(receipt['run_diff']),1);self.assertEqual(receipt['run_diff'][0]['run_path'],(0,0))
        self.assert_changes({3:'합성 제목'})

    def test_more_values_than_existing_paragraphs_does_not_create(self):
        doc,_=self.basic();self.save(doc)
        self.assert_request_blocked(request(field(values=[['첫째','둘째']],paragraphs=[1,2])),'selected_paragraph_missing')

    def test_target_with_nested_table_is_blocked(self):
        doc,table=self.basic();table.cell(0,1).add_table(1,1).cell(0,0).set_text('하위 내용 유지');self.save(doc)
        self.assert_request_blocked(request(field()),'nested_cell_write_unvalidated')

    def test_unrelated_nested_table_remains_intact(self):
        doc,_=self.basic();other=doc.add_table(1,1).cell(0,0);other.set_text('외부 유지')
        other.add_table(1,1).cell(0,0).set_text('내부 유지');self.save(doc)
        apply_form(self.source,self.output,self.plan(request(field())));self.assert_changes({3:'합성 제목'})

    def test_target_inline_linebreak_control_is_not_flattened(self):
        doc,table=self.basic();table.cell(0,1).paragraphs[0].add_run('안내\n유지',expand_special_characters=True);self.save(doc)
        self.assert_request_blocked(request(field(allow_replace=True)),'unsupported_run_control')

    def test_label_prefix_is_not_a_match(self):
        doc,table=self.basic();table.cell(0,0).set_text('제목 안내');self.save(doc)
        self.assert_request_blocked(request(field()),'found 0')

    def test_request_cannot_overwrite_another_requested_label(self):
        doc=HwpxDocument.new();t=doc.add_table(1,3);t.cell(0,0).set_text('제목');t.cell(0,1).set_text('내용');t.cell(0,2).set_text('');self.save(doc)
        self.assert_request_blocked(request(field(allow_replace=True),field('내용',id='body')),'another_requested_label')

    def test_two_labels_mapping_to_same_paragraph_block(self):
        doc=HwpxDocument.new();t=doc.add_table(2,2);t.cell(0,0).set_text('제목');t.cell(1,0).set_text('내용')
        t.merge_cells(0,1,1,1);t.cell(0,1).set_text('');self.save(doc)
        self.assert_request_blocked(request(field(),field('내용',id='body')),'overlapping_target')

    def test_stale_hash_changed_plan_and_omitted_field_block(self):
        doc,_=self.basic();self.save(doc);original=self.plan(request(field()))
        for mutate in (lambda p:p.update(source_sha256='0'*64),
                       lambda p:p['fields'][0]['targets'][0]['paragraphs'][0].update(value='변조'),
                       lambda p:p.update(fields=[]),lambda p:p.update(request_sha256='0'*64)):
            plan=copy.deepcopy(original);mutate(plan);self.assert_plan_blocked(plan,'hash|binding')

    def test_invalid_xml_newline_and_unknown_keys_rejected(self):
        for value in ('a\nb','a\tb','\x00','\ud800'):
            with self.assertRaises(ValueError):validate_request(request(field(values=[[value]])))
        for changes in ({'unknown':True},{'table':True},{'paragraphs':[2,1]},{'allow_replace':'yes'}):
            with self.assertRaises(ValueError):validate_request(request(field(**changes)))

    def test_special_characters_preserved_as_text(self):
        doc,_=self.basic();self.save(doc)
        apply_form(self.source,self.output,self.plan(request(field(values=[['A<&>B']]))));self.assert_changes({3:'A<&>B'})

    def test_dryrun_no_publish_and_output_original_or_existing_rejected(self):
        doc,_=self.basic();self.save(doc);plan=self.plan(request(field()))
        result=apply_form(self.source,self.output,plan,dry_run=True)
        self.assertEqual(result['status'],'PASS_STRUCTURE_DRY_RUN');self.assertFalse(self.output.exists())
        with self.assertRaises(ValueError):apply_form(self.source,self.source,plan)
        self.output.write_bytes(b'KEEP_OTHER_OUTPUT')
        with self.assertRaises(ValueError):apply_form(self.source,self.output,plan)
        self.assertEqual(self.output.read_bytes(),b'KEEP_OTHER_OUTPUT');self.assertEqual(self.source.read_bytes(),self.original)

    def test_injected_blank_setter_drops_other_content_and_is_fatal(self):
        doc,table=self.basic();doc.add_paragraph('KEEP');self.save(doc);plan=self.plan(request(field()))
        setter=HwpxOxmlRun.text.fset
        def destructive(run,value):
            setter(run,value)
            for p in run.paragraph.section.paragraphs:
                for other in p.runs:
                    if other.text=='KEEP':setter(other,'LOST')
        with patch.object(HwpxOxmlRun,'text',property(HwpxOxmlRun.text.fget,destructive)):
            self.assert_plan_blocked(plan,'preservation mismatch')

    def test_noop_request_does_not_publish(self):
        doc,_=self.basic();self.save(doc)
        self.assert_plan_blocked(self.plan(request(field(values=[['']]))),'no changes')

    def test_form_diagnosis_requires_plan_and_missing_field_blocks(self):
        doc,_=self.basic();self.save(doc)
        good=diagnose(self.source,'fill_form',request=request(field()))
        self.assertEqual(good['decision'],'REQUIRES_EXPLICIT_PLAN');self.assertEqual(good['route'],'form_fill.py')
        bad=diagnose(self.source,'fill_form',request=request(field('없는 필드')))
        self.assertEqual(bad['decision'],'BLOCK');self.assertIsNone(bad['route'])

    def test_blank_setter_unrequested_style_change_is_fatal(self):
        doc,table=self.basic();p=table.cell(0,1).paragraphs[0]
        styled=p.add_run('',bold=True);p.runs[0].char_pr_id_ref=styled.char_pr_id_ref;self.save(doc)
        setter=HwpxOxmlRun.text.fset
        def wrong_style(run,value):setter(run,value);run.char_pr_id_ref='0'
        with patch.object(HwpxOxmlRun,'text',property(HwpxOxmlRun.text.fget,wrong_style)):
            self.assert_plan_blocked(self.plan(request(field())),'preservation mismatch')

    def test_invalid_cell_geometry_blocks_form_mapping(self):
        doc,_=self.basic();self.save(doc)
        with ZipFile(self.source) as z:members={n:z.read(n) for n in z.namelist()}
        root=E.fromstring(members['Contents/section0.xml']);addresses=root.findall('.//{*}cellAddr')
        addresses[1].set('colAddr','0');members['Contents/section0.xml']=E.tostring(root,encoding='utf-8')
        with ZipFile(self.source,'w') as z:
            for name,data in members.items():z.writestr(name,data)
        self.original=self.source.read_bytes()
        self.assert_request_blocked(request(field()),'ambiguous_or_invalid_table_geometry')

    def test_actual_cli_inspect_plan_dryrun_apply(self):
        doc,_=self.basic();self.save(doc);req=self.root/'request.json';req.write_text(json.dumps(request(field()),ensure_ascii=False),encoding='utf-8')
        listing=self.root/'inspection.json';plan=self.root/'plan.json';script=Path(__file__).with_name('form_fill.py')
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1')
        diagnosis=subprocess.run([sys.executable,'-X','utf8','-B',str(script.with_name('diagnose_edit.py')),
                                  str(self.source),'--operation','fill_form','--request',str(req)],
                                 env=env,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(diagnosis.returncode,0,diagnosis.stdout+diagnosis.stderr)
        self.assertEqual(json.loads(diagnosis.stdout)['decision'],'REQUIRES_EXPLICIT_PLAN')
        def run(*args):
            result=subprocess.run([sys.executable,'-X','utf8','-B',str(script),*map(str,args)],env=env,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr);return json.loads(result.stdout)
        run('inspect',self.source,'--request',req,'--output',listing)
        run('plan','--inspection',listing,'--output',plan)
        run('apply',self.source,self.output,'--plan',plan,'--dry-run');self.assertFalse(self.output.exists())
        run('apply',self.source,self.output,'--plan',plan);self.assert_changes({3:'합성 제목'})

    def test_actual_cli_missing_field_blocks_plan_and_no_output(self):
        doc,_=self.basic();self.save(doc)
        req=self.root/'missing-request.json';req.write_text(json.dumps(request(field(),field('없는 필드')),ensure_ascii=False),encoding='utf-8')
        listing=self.root/'blocked-inspection.json';plan=self.root/'forbidden-plan.json';script=Path(__file__).with_name('form_fill.py')
        env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1')
        read=subprocess.run([sys.executable,'-X','utf8','-B',str(script),'inspect',str(self.source),
                             '--request',str(req),'--output',str(listing)],env=env,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(read.returncode,2);self.assertEqual(json.loads(read.stdout)['status'],'BLOCKED')
        make=subprocess.run([sys.executable,'-X','utf8','-B',str(script),'plan','--inspection',str(listing),
                             '--output',str(plan)],env=env,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(make.returncode,2);self.assertFalse(plan.exists());self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(),self.original)


if __name__=='__main__':
    unittest.main(verbosity=2)
