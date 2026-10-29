from pathlib import Path
import copy,hashlib,json,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from candidate_runtime import activate
activate()
from hwpx.document import HwpxDocument
from hwpx_automation.office.agent.document import HwpxAgentDocument
from hwpx_automation.office.agent.commands import _apply_set
from fill_template import fill,load_form,compile_fill
from hangul_task import batch

CATALOG=Path(__file__).resolve().parents[1]/'assets/document-templates/blocks.json'

class PreparedFill(unittest.TestCase):
    def test_refresh_matches_full_projection(self):
        with HwpxDocument.new() as doc:
            doc.add_paragraph('old heading')
            table=doc.add_table(2,2);table.cell(0,0).text='old cell'
            view=HwpxAgentDocument.from_document(doc,revision='sha256:'+'0'*64)
            for rec in [r for r in view.records if r.kind=='run' and r.native.text.startswith('old')]:
                _apply_set(doc,rec,{'text':'new content'})
                self.assertTrue(view.refresh_run_text(rec))
            fresh=HwpxAgentDocument.from_document(doc,revision=view.revision)
            self.assertEqual([(r.path,r.summary,r.search_text) for r in view.records],[(r.path,r.summary,r.search_text) for r in fresh.records])

    def test_padding_inherits_other_edges_and_preserves_border(self):
        with HwpxDocument.new() as doc:
            table=doc.add_table(1,1);cell=table.cell(0,0)
            cell.element.set('hasMargin','0')
            old=cell.effective_margins.copy();border=cell.element.get('borderFillIDRef')
            cell.set_margins(left=567)
            self.assertEqual(cell.effective_margins,dict(old,left=567))
            self.assertEqual(cell.element.get('borderFillIDRef'),border)
            self.assertEqual(cell.element.get('hasMargin'),'1')
            with self.assertRaises(ValueError):cell.set_margins(right=cell.width)

    def test_scoped_replacement_keeps_inline_object_position(self):
        with HwpxDocument.new() as doc:
            paragraph=doc.add_paragraph('before');run=paragraph.runs[0]
            shape=run.element.makeelement('{http://www.hancom.co.kr/hwpml/2011/paragraph}rect',{})
            run.element.append(shape)
            text=run.element.makeelement('{http://www.hancom.co.kr/hwpml/2011/paragraph}t',{});text.text='\u200b';run.element.append(text)
            view=HwpxAgentDocument.from_document(doc,revision='sha256:'+'0'*64)
            rec=next(r for r in view.records if r.kind=='run' and r.native.element is run.element)
            _apply_set(doc,rec,{'textReplacement':{'search':'\u200b','replacement':'목표'}})
            self.assertIs(run.element[-2],shape);self.assertEqual(run.element[-1].text,'목표');self.assertEqual(run.element[0].text,'before')
            with self.assertRaises(Exception):_apply_set(doc,rec,{'textReplacement':{'search':'missing','replacement':'x'}})

    def test_missing_padding_can_be_read_but_not_guessed(self):
        with HwpxDocument.new() as doc:
            table=doc.add_table(1,1);cell=table.cell(0,0);cell.element.set('hasMargin','0')
            margin=next(n for n in table.element if n.tag.endswith('}inMargin'));table.element.remove(margin)
            view=HwpxAgentDocument.from_document(doc,revision='sha256:'+'0'*64)
            self.assertIsNone(next(r for r in view.records if r.kind=='cell').summary['paddingMm'])
            with self.assertRaises(ValueError):cell.set_margins(left=567)

    def test_prepared_repeat_style_and_atomic_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'filled.hwpx'
            result=fill(CATALOG,'event-timetable',output,{'sessions':[{'time':'0~10분','minutes':'10','activity':'협력 활동','owner':'교사'}]*3})
            self.assertTrue(result['ok']);self.assertEqual(result['form']['mutationBatches'],1)
            with HwpxAgentDocument.open(output) as view:
                owners=[r for r in view.records if r.kind=='cell' and r.summary['column']==4 and r.summary['row']>1]
                self.assertEqual(len(owners),3)
                self.assertTrue(all(r.summary['verticalAlignment']=='CENTER' for r in owners))
            failed=Path(folder)/'rejected.hwpx'
            with self.assertRaises(ValueError):fill(CATALOG,'event-timetable',failed,{'bad':'value'})
            self.assertFalse(failed.exists())

    def test_large_fixed_fill_is_private_until_success(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'large.hwpx'
            result=fill(CATALOG,'current-status',output,{},dry_run=True)
            self.assertTrue(result['ok']);self.assertFalse(result['documentPublished']);self.assertFalse(output.exists())
            self.assertEqual(result['form']['mutationBatches'],2)

    def test_role_override_and_provenance_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'override.hwpx'
            result=fill(CATALOG,'event-timetable',output,{'sessions':[{'owner':'교사'}]},styles={'short-value':{'alignment':'LEFT'}})
            self.assertTrue(result['ok'])
            with HwpxAgentDocument.open(output) as view:
                paragraphs=[r for r in view.records if r.kind=='paragraph' and '/row[2]/cell[4]/' in r.path]
                self.assertTrue(all(r.summary['alignment']=='LEFT' for r in paragraphs))
            manifest,source,styles,_=load_form(CATALOG,'event-timetable')
            manifest=copy.deepcopy(manifest);manifest['template']['sha256']='0'*64
            with self.assertRaises(ValueError):compile_fill(manifest,source,Path(folder)/'stale.hwpx',{},styles)

    def test_marker_repeat_rejected_before_edit(self):
        manifest,source,styles,_=load_form(CATALOG,'event-timetable')
        manifest=copy.deepcopy(manifest);manifest['repeats']['sessions']['fields']['time']['marker']='\u200b'
        with self.assertRaisesRegex(ValueError,'fixed slots only'):
            compile_fill(manifest,source,Path('unused.hwpx'),{'sessions':[{'time':'1'},{'time':'2'}]},styles)

    def test_caption_slot_replaces_old_unit(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'unit.hwpx'
            result=fill(CATALOG,'current-status',output,{'unit':'건'})
            self.assertTrue(result['ok'])
            with HwpxAgentDocument.open(output) as view:
                captions=[r.summary.get('caption','') for r in view.records if r.kind=='table']
                self.assertIn('(단위: 건)',captions)
                self.assertNotIn('백만원',str(captions))

if __name__=='__main__':unittest.main()
