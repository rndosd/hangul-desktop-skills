# SPDX-License-Identifier: Apache-2.0
"""Synthetic editing contracts; native Hancom layout is not claimed here."""
import copy
import base64
import hashlib
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
from safe_edit import apply_plan, inspect_targets, make_plan, POLICY, SCHEMA
from safe_replace import replace as legacy_replace
from diagnose_edit import diagnose


def local(node):
    return node.tag.rsplit('}', 1)[-1]


def read_document(path):
    """Independent oracle: visible text/style, control topology, other members."""
    texts, topology, other = [], [], {}
    with ZipFile(path) as z:
        for member in sorted(z.namelist()):
            if member.startswith('Preview/'):
                continue
            data = z.read(member)
            if member.startswith('Contents/section') and member.endswith('.xml'):
                root = E.fromstring(data)
                for paragraph in [n for n in root.iter() if local(n) == 'p']:
                    runs = [n for n in paragraph if local(n) == 'run']
                    texts.append((''.join(''.join(t.itertext()) for r in runs for t in r if local(t) == 't'),
                                  [(r.get('charPrIDRef'), dict(r.attrib)) for r in runs]))
                def shape(n):
                    return n.tag, sorted(n.attrib.items()), '' if local(n) == 't' else (n.text or ''), tuple(shape(c) for c in n if local(c).lower() != 'linesegarray')
                topology.append(shape(root))
            else:
                other[member] = data
    return texts, topology, other


class SelectedEditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.output = self.root/'source.hwpx', self.root/'edited.hwpx'

    def save(self, doc):
        doc.save_to_path(self.source)
        doc.close()
        self.original = self.source.read_bytes()

    def plan(self, find='TARGET', replacement='NEW', index=0, **coordinates):
        listing = inspect_targets(self.source, find, **coordinates)
        return make_plan(listing, [listing['targets'][index]['target_id']], replacement)

    def assert_preserved(self, expected_texts):
        before, shape_before, other_before = read_document(self.source)
        after, shape_after, other_after = read_document(self.output)
        self.assertEqual([text for text, _ in after], expected_texts)
        self.assertEqual([styles for _, styles in before], [styles for _, styles in after])
        self.assertEqual(shape_before, shape_after)
        self.assertEqual(other_before, other_after)
        self.assertEqual(self.original, self.source.read_bytes())

    def assert_blocked(self, plan, pattern=None):
        with self.assertRaisesRegex((ValueError, OSError), pattern or '.*'):
            apply_plan(self.source, self.output, plan)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.original, self.source.read_bytes())

    def test_cross_run_longer_and_shorter_keep_styles(self):
        for replacement in ('REPLACEMENT_LONG', 'X', ''):
            with self.subTest(replacement=replacement):
                d=HwpxDocument.new();p=d.add_paragraph('', include_run=False)
                p.add_run('PRE TAR', bold=True);p.add_run('G', italic=True);p.add_run('ET POST', underline=True)
                d.add_paragraph('KEEP');self.save(d)
                with self.assertRaisesRegex(ValueError, 'unique_text_target'):
                    legacy_replace(self.source, self.output, 'TARGET', replacement)
                receipt=apply_plan(self.source, self.output, self.plan(replacement=replacement))
                self.assertEqual(receipt['selected_edits'],1)
                self.assertEqual(receipt['native_render'],'not_checked')
                self.assertEqual(receipt['completion'],'edited_candidate_native_pending')
                self.assert_preserved(['', 'PRE '+replacement+' POST', 'KEEP'])
                self.output.unlink()

    def test_simple_cell_approval_table_merged_cell_and_header_preserved(self):
        d=HwpxDocument.new();d.page.set_header(text='HEADER_KEEP')
        approval=d.add_table(2,3);approval.cell(0,0).set_text('APPROVAL_KEEP')
        approval.merge_cells(0,1,0,2);approval.cell(0,1).set_text('MERGED_APPROVAL_KEEP')
        table=d.add_table(2,2);table.cell(0,0).set_text('LABEL_KEEP');table.cell(1,1).set_text('TARGET')
        self.save(d)
        with self.assertRaisesRegex(ValueError,'local_table_text_route_unvalidated'):
            legacy_replace(self.source,self.output,'TARGET','NEW')
        receipt=apply_plan(self.source,self.output,self.plan(table=2,row=2,column=2))
        self.assertEqual(receipt['layout_risk'][0]['scope']['table'],2)
        texts=[t for t,_ in read_document(self.source)[0]]
        self.assert_preserved(['NEW' if t=='TARGET' else t for t in texts])

    def test_covered_merged_coordinate_selects_owner_without_unmerging(self):
        d=HwpxDocument.new();t=d.add_table(2,3);t.merge_cells(0,0,1,1)
        t.cell(0,0).set_text('TARGET');t.cell(0,2).set_text('OTHER_CELL_KEEP');self.save(d)
        listing=inspect_targets(self.source,'TARGET',table=1,row=2,column=2)
        self.assertEqual(listing['targets'][0]['scope']['row_span'],2)
        self.assertEqual(listing['targets'][0]['scope']['column_span'],2)
        apply_plan(self.source,self.output,make_plan(listing,[listing['targets'][0]['target_id']],'NEW'))
        texts=[t for t,_ in read_document(self.source)[0]]
        self.assert_preserved(['NEW' if t=='TARGET' else t for t in texts])

    def test_cell_second_paragraph_only_and_duplicate_cells(self):
        d=HwpxDocument.new();t=d.add_table(1,2)
        t.cell(0,0).set_text('TARGET');t.cell(0,1).set_text('TARGET');t.cell(0,1).add_paragraph('TARGET')
        self.save(d)
        listing=inspect_targets(self.source,'TARGET',table=1,row=1,column=2)
        self.assertEqual([x['scope']['paragraph'] for x in listing['targets']],[1,2])
        apply_plan(self.source,self.output,make_plan(listing,[listing['targets'][1]['target_id']],'NEW'))
        texts=[t for t,_ in read_document(self.source)[0]];texts[-1]='NEW'
        self.assert_preserved(texts)

    def test_second_occurrence_same_run_and_other_paragraph_untouched(self):
        d=HwpxDocument.new();d.add_paragraph('TARGET TARGET');d.add_paragraph('TARGET');self.save(d)
        apply_plan(self.source,self.output,self.plan(index=1))
        self.assert_preserved(['','TARGET NEW','TARGET'])

    def test_duplicate_body_explicit_second_location(self):
        d=HwpxDocument.new();d.add_paragraph('TARGET');d.add_paragraph('TARGET');self.save(d)
        with self.assertRaisesRegex(ValueError,'unique_text_target'):
            legacy_replace(self.source,self.output,'TARGET','NEW')
        apply_plan(self.source,self.output,self.plan(index=1))
        self.assert_preserved(['','TARGET','NEW'])

    def test_batch_same_run_and_different_cells_uses_original_offsets(self):
        d=HwpxDocument.new();d.add_paragraph('TARGET / TARGET');t=d.add_table(1,2)
        t.cell(0,0).set_text('TARGET');t.cell(0,1).set_text('KEEP');self.save(d)
        listing=inspect_targets(self.source,'TARGET');ids=[x['target_id'] for x in listing['targets']]
        plan=make_plan(listing,ids,'EXPANDED_NEW')
        receipt=apply_plan(self.source,self.output,plan)
        self.assertEqual(receipt['selected_edits'],3)
        self.assert_preserved(['','EXPANDED_NEW / EXPANDED_NEW','','EXPANDED_NEW','KEEP'])

    def test_overlap_and_duplicate_selection_block_entire_batch(self):
        d=HwpxDocument.new();d.add_paragraph('ABABA');self.save(d)
        listing=inspect_targets(self.source,'ABA');plan=make_plan(listing,[x['target_id'] for x in listing['targets']],'X')
        self.assert_blocked(plan,'overlapping')
        plan=make_plan(listing,[listing['targets'][0]['target_id']],'X');plan['edits']*=2
        self.assert_blocked(plan,'overlapping')

    def test_invalid_later_edit_never_publishes_first_edit(self):
        d=HwpxDocument.new();d.add_paragraph('TARGET');self.save(d)
        plan=self.plan();plan['edits'].append({'target_id':'wrong','find':'TARGET','replace':'OTHER'})
        self.assert_blocked(plan,'missing or unsupported')

    def test_nested_cell_host_and_inner_cell_still_blocked(self):
        d=HwpxDocument.new();c=d.add_table(1,1).cell(0,0);c.set_text('TARGET')
        c.add_table(1,1).cell(0,0).set_text('INNER');self.save(d)
        for term in ('TARGET','INNER'):
            listing=inspect_targets(self.source,term);target=listing['targets'][0]
            self.assertFalse(target['supported'])
            with self.assertRaisesRegex(ValueError,'unsupported'):
                make_plan(listing,[target['target_id']],'NEW')
            forged={'schema':SCHEMA,'source_sha256':listing['source_sha256'],'style_policy':POLICY,
                    'edits':[{'target_id':target['target_id'],'find':term,'replace':'NEW'}]}
            self.assert_blocked(forged,'nested_cell')

    def test_body_edit_preserves_unrelated_nested_table(self):
        d=HwpxDocument.new();d.add_paragraph('TARGET');c=d.add_table(1,1).cell(0,0)
        c.set_text('HOST_KEEP');c.add_table(1,1).cell(0,0).set_text('INNER_KEEP');self.save(d)
        apply_plan(self.source,self.output,self.plan())
        texts=[t for t,_ in read_document(self.source)[0]];texts[1]='NEW'
        self.assert_preserved(texts)

    def test_tabs_and_inline_controls_not_flattened(self):
        d=HwpxDocument.new();d.add_paragraph('TA\tRGET');self.save(d)
        listing=inspect_targets(self.source,'TARGET')
        self.assertEqual(listing['targets'][0]['reason'],'unsupported_run_control_or_mixed_text')
        with self.assertRaisesRegex(ValueError,'unsupported'):
            make_plan(listing,[listing['targets'][0]['target_id']],'NEW')
        self.assertEqual(self.original,self.source.read_bytes())

    def test_old_hash_tampered_token_policy_and_invalid_text_blocked(self):
        d=HwpxDocument.new();d.add_paragraph('TARGET');self.save(d);original=self.plan()
        for key,value in [('source_sha256','0'*64),('style_policy','guess_styles')]:
            plan=copy.deepcopy(original);plan[key]=value;self.assert_blocked(plan)
        plan=copy.deepcopy(original);plan['edits'][0]['target_id']='0'*64;self.assert_blocked(plan)
        for value in ('a\nb','a\tb','\x00','\ud800'):
            plan=copy.deepcopy(original);plan['edits'][0]['replace']=value;self.assert_blocked(plan)

    def test_special_xml_characters_are_text_not_markup(self):
        d=HwpxDocument.new();d.add_paragraph('TARGET');self.save(d)
        apply_plan(self.source,self.output,self.plan(replacement='A<&>B'))
        self.assert_preserved(['','A<&>B'])

    def test_dry_run_validates_complete_candidate_without_output(self):
        d=HwpxDocument.new();d.add_paragraph('TARGET');self.save(d)
        dry=apply_plan(self.source,self.output,self.plan(),dry_run=True)
        self.assertEqual(dry['status'],'PASS_STRUCTURE_DRY_RUN');self.assertFalse(self.output.exists())
        real=apply_plan(self.source,self.output,self.plan())
        self.assertEqual(dry['run_diff'],real['run_diff'])
        self.assert_preserved(['','NEW'])

    def test_original_existing_output_wrong_version_and_legacy_hwp_blocked(self):
        d=HwpxDocument.new();d.add_paragraph('TARGET');self.save(d);plan=self.plan()
        with self.assertRaisesRegex(ValueError,'new path'):
            apply_plan(self.source,self.source,plan)
        self.output.write_bytes(b'USER_OUTPUT_KEEP')
        with self.assertRaises(ValueError):apply_plan(self.source,self.output,plan)
        self.assertEqual(self.output.read_bytes(),b'USER_OUTPUT_KEEP');self.output.unlink()
        with patch('safe_edit.version',return_value='6.6.0'):self.assert_blocked(plan,'unvalidated')
        legacy=self.root/'source.hwp';legacy.write_bytes(self.original)
        with self.assertRaisesRegex(ValueError,'legacy HWP'):inspect_targets(legacy,'TARGET')

    def test_unexpected_non_target_text_change_is_fatal(self):
        d=HwpxDocument.new();d.add_paragraph('TARGET');d.add_paragraph('KEEP');self.save(d)
        original=HwpxOxmlRun.replace_text
        def destructive(run,old,new,**kwargs):
            count=original(run,old,new,**kwargs)
            for paragraph in run.paragraph.section.paragraphs:
                for other in paragraph.runs:
                    if other.text=='KEEP':original(other,'KEEP','LOST')
            return count
        with patch.object(HwpxOxmlRun,'replace_text',destructive):
            self.assert_blocked(self.plan(),'preservation mismatch')

    def test_api_count_mismatch_and_source_race_blocked(self):
        d=HwpxDocument.new();d.add_paragraph('TARGET');self.save(d);plan=self.plan()
        with patch.object(HwpxOxmlRun,'replace_text',return_value=0):self.assert_blocked(plan,'count mismatch')
        sha=hashlib.sha256(self.original).hexdigest()
        with patch('safe_edit.digest',side_effect=[sha,'changed']):self.assert_blocked(plan,'source changed')

    def test_output_race_does_not_overwrite_existing_file(self):
        d=HwpxDocument.new();d.add_paragraph('TARGET');self.save(d)
        def race(candidate,output):
            Path(output).write_bytes(b'OTHER_WORK_KEEP')
            raise FileExistsError('destination created concurrently')
        with patch('safe_edit.os.link',side_effect=race):
            with self.assertRaises(FileExistsError):apply_plan(self.source,self.output,self.plan())
        self.assertEqual(self.output.read_bytes(),b'OTHER_WORK_KEEP')
        self.assertEqual(self.original,self.source.read_bytes())

    def test_selected_diagnosis_is_plan_required_not_permission_to_write(self):
        d=HwpxDocument.new();p=d.add_paragraph('',include_run=False);p.add_run('TAR');p.add_run('GET');self.save(d)
        result=diagnose(self.source,'selected_text','TARGET')
        self.assertEqual(result['decision'],'REQUIRES_EXPLICIT_PLAN')
        self.assertEqual(diagnose(self.source,'replace_text','TARGET')['decision'],'BLOCK')

    def test_multiple_sections_select_exact_section(self):
        d=HwpxDocument.new();d.add_paragraph('TARGET');s=d.add_section();d.add_paragraph('TARGET',section=s);self.save(d)
        listing=inspect_targets(self.source,'TARGET');self.assertEqual([x['section'] for x in listing['targets']],[1,2])
        apply_plan(self.source,self.output,make_plan(listing,[listing['targets'][1]['target_id']],'NEW'))
        self.assert_preserved(['','TARGET','','NEW'])

    def test_picture_payload_is_preserved_and_corruption_is_fatal(self):
        image=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
        d=HwpxDocument.new();d.add_paragraph('TARGET');d.add_picture(image,'png',width_mm=5,height_mm=5);self.save(d)
        apply_plan(self.source,self.output,self.plan())
        texts=[t for t,_ in read_document(self.source)[0]];texts[1]='NEW';self.assert_preserved(texts);self.output.unlink()
        save=HwpxDocument.save_to_path
        def corrupt(doc,path):
            save(doc,path)
            with ZipFile(path) as z:members={n:z.read(n) for n in z.namelist()}
            image_name=next(n for n in members if n.startswith('BinData/'))
            members[image_name]+=b'UNREQUESTED_CHANGE'
            with ZipFile(path,'w') as z:
                for n,data in members.items():z.writestr(n,data)
        with patch.object(HwpxDocument,'save_to_path',corrupt):self.assert_blocked(self.plan(),'preservation mismatch')

    def test_correct_text_with_unrequested_style_change_is_fatal(self):
        d=HwpxDocument.new();p=d.add_paragraph('',include_run=False);p.add_run('TARGET',bold=True);self.save(d)
        original=HwpxOxmlRun.replace_text
        def change_style(run,old,new,**kwargs):
            count=original(run,old,new,**kwargs);run.char_pr_id_ref='0';return count
        with patch.object(HwpxOxmlRun,'replace_text',change_style):self.assert_blocked(self.plan(),'preservation mismatch')

    def test_overlapping_cell_geometry_is_refused(self):
        d=HwpxDocument.new();t=d.add_table(1,2);t.cell(0,0).set_text('TARGET');t.cell(0,1).set_text('TARGET');self.save(d)
        with ZipFile(self.source) as z:members={n:z.read(n) for n in z.namelist()}
        root=E.fromstring(members['Contents/section0.xml']);addresses=[n for n in root.iter() if local(n)=='cellAddr']
        addresses[1].set('colAddr','0');members['Contents/section0.xml']=E.tostring(root,encoding='utf-8')
        with ZipFile(self.source,'w') as z:
            for n,data in members.items():z.writestr(n,data)
        self.original=self.source.read_bytes();listing=inspect_targets(self.source,'TARGET',table=1,row=1,column=1)
        self.assertTrue(all(t['reason']=='ambiguous_or_invalid_table_geometry' for t in listing['targets']))
        with self.assertRaisesRegex(ValueError,'unsupported'):make_plan(listing,[listing['targets'][0]['target_id']],'NEW')
        self.assertEqual(self.original,self.source.read_bytes())

    def test_cli_inspect_plan_dryrun_apply_and_new_output_conflict(self):
        d=HwpxDocument.new();d.add_paragraph('TARGET');self.save(d)
        script=Path(__file__).with_name('safe_edit.py');inspection=self.root/'inspection.json';plan=self.root/'plan.json'
        env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1';env['PYTHONUTF8']='1'
        def run(*args):
            result=subprocess.run([sys.executable,'-X','utf8','-B',str(script),*map(str,args)],capture_output=True,text=True,encoding='utf-8',env=env)
            return result.returncode,json.loads(result.stdout)
        code,payload=run('inspect',self.source,'--find','TARGET','--output',inspection);self.assertEqual(code,0)
        token=payload['targets'][0]['target_id']
        code,_=run('plan','--inspection',inspection,'--target',token,'--replace','NEW','--output',plan);self.assertEqual(code,0)
        code,_=run('apply',self.source,self.output,'--plan',plan,'--dry-run');self.assertEqual(code,0);self.assertFalse(self.output.exists())
        code,_=run('apply',self.source,self.output,'--plan',plan);self.assertEqual(code,0)
        code,payload=run('apply',self.source,self.output,'--plan',plan);self.assertEqual(code,2);self.assertEqual(payload['status'],'BLOCKED')
        self.assert_preserved(['','NEW'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
