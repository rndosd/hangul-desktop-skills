from pathlib import Path
import copy
import io
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from candidate_runtime import activate
activate()
from hwpx import HwpxDocument
import safe_cell_layout as layout


class AlignmentRangesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'source.hwpx'
        self.output = Path(self.temp.name) / 'result.hwpx'
        with HwpxDocument.new() as doc:
            table = doc.add_table(4, 4)
            table.cell(0, 0).paragraphs[0].text = 'Merged header remains'
            table.merge_cells(0, 0, 0, 3)
            for row in range(1, 4):
                for col in range(4):
                    p = table.cell(row, col).paragraphs[0]
                    p.text = f'cell {row},{col} '
                    p.add_run('emphasis', bold=True, size=13)
            p = table.cell(2, 1).add_paragraph('Second paragraph')
            p.para_pr_id_ref = doc.parts.headers[0].ensure_paragraph_format(
                base_para_pr_id=p.para_pr_id_ref, alignment='RIGHT',
                margins={'left': 220, 'right': 130}, line_spacing_percent=190)
            self.source.write_bytes(doc.to_bytes())
        self.request = dict(schema=layout.SCHEMA, source_sha256=layout.sha(self.source),
                            table=1, operation='align_many', alignments=[
            {'range': [2, 1, 4, 1], 'alignment': 'CENTER'},
            {'range': [2, 2, 4, 2], 'alignment': 'LEFT'},
            {'range': [2, 4, 4, 4], 'alignment': 'RIGHT'}])

    def apply(self, request=None, dry=False):
        return layout.apply(self.source, self.output, request or self.request, dry)

    def test_different_ranges_and_paragraphs_keep_content_and_styles(self):
        before = self.source.read_bytes()
        report = self.apply()
        self.assertTrue(report['checks']['stylesPreserved'])
        self.assertEqual(before, self.source.read_bytes())
        bm, _, _, bt = layout.locate(before, 1)
        am, _, _, at = layout.locate(self.output.read_bytes(), 1)
        bc, _ = layout.geometry(bt, True)
        ac, _ = layout.geometry(at, True)
        bdefs = {p.get('id'): p for p in layout.xml(bm['Contents/header.xml']).iter(layout.H+'paraPr')}
        adefs = {p.get('id'): p for p in layout.xml(am['Contents/header.xml']).iter(layout.H+'paraPr')}
        for coord, old_cell in bc.items():
            new_cell = ac[coord]
            if coord[0] == 0 or coord[1] == 2:
                self.assertEqual(layout.snap(old_cell), layout.snap(new_cell))
                continue
            expected = {0:'CENTER', 1:'LEFT', 3:'RIGHT'}[coord[1]]
            for old, new in zip(layout.paragraphs(old_cell), layout.paragraphs(new_cell)):
                self.assertEqual([layout.snap(r) for r in old.findall(layout.P+'run')],
                                 [layout.snap(r) for r in new.findall(layout.P+'run')])
                old_format = copy.deepcopy(bdefs[old.get('paraPrIDRef')])
                new_format = copy.deepcopy(adefs[new.get('paraPrIDRef')])
                self.assertEqual(new_format.find(layout.H+'align').get('horizontal'), expected)
                old_format.attrib.pop('id'); new_format.attrib.pop('id')
                old_format.find(layout.H+'align').set('horizontal', expected)
                self.assertEqual(layout.snap(old_format), layout.snap(new_format))

    def test_one_open_and_one_serialization(self):
        edit_documents = []
        original_open = HwpxDocument.open
        original = HwpxDocument.to_bytes
        def tracked_open(source, *args, **kwargs):
            doc = original_open(source, *args, **kwargs)
            if isinstance(source, (str, Path)) and Path(source).resolve() == self.source.resolve():
                edit_documents.append(doc)
            return doc
        with patch.object(HwpxDocument, 'open', side_effect=tracked_open):
            with patch.object(HwpxDocument, 'to_bytes', autospec=True, side_effect=original) as saved:
                self.apply()
                self.assertEqual(len(edit_documents), 1)
                self.assertEqual(sum(c.args[0] is edit_documents[0] for c in saved.call_args_list), 1)

    def test_dry_run_does_not_publish(self):
        report = self.apply(dry=True)
        self.assertFalse(report['published'])
        self.assertFalse(self.output.exists())

    def test_same_overlap_deduplicated(self):
        q = copy.deepcopy(self.request)
        q['alignments'].append({'range':[3,1,4,1], 'alignment':'CENTER'})
        self.apply(q)
        self.assertTrue(self.output.is_file())

    def rejected(self, request):
        original = self.source.read_bytes()
        with patch.object(HwpxDocument, 'open', wraps=HwpxDocument.open) as opened:
            with self.assertRaises(ValueError): self.apply(request)
            self.assertEqual(opened.call_count, 0)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), original)

    def test_conflicting_overlap_rejected_before_open(self):
        q = copy.deepcopy(self.request)
        q['alignments'].append({'range':[4,1,4,1], 'alignment':'LEFT'})
        self.rejected(q)

    def test_invalid_late_selection_does_not_publish_earlier_edits(self):
        for selection in [
            {'range':[1,1,1,4], 'alignment':'CENTER'},
            {'range':[5,1,5,1], 'alignment':'CENTER'},
            {'range':[True,1,2,1], 'alignment':'CENTER'},
            {'range':[2,1,2,1], 'alignment':'JUSTIFY'},
            {'range':[2,1,2,1], 'alignment':'CENTER', 'force': True}]:
            with self.subTest(selection=selection):
                q = copy.deepcopy(self.request); q['alignments'].append(selection)
                self.rejected(q)

    def test_no_ambiguous_empty_or_old_shape(self):
        for change in [{'range':[2,1,4,1]}, {'alignment':'CENTER'}, {'alignments':[]},
                       {'alignments':self.request['alignments']*34}, {'operation':'align'}]:
            with self.subTest(change=change): self.rejected(dict(self.request, **change))

    def test_stale_source_rejected(self):
        self.rejected(dict(self.request, source_sha256='0'*64))

    def test_overwrite_is_refused(self):
        self.output.write_bytes(b'keep')
        with self.assertRaises(ValueError): self.apply()
        self.assertEqual(self.output.read_bytes(), b'keep')

    def corrupt(self, fn):
        self.apply()
        members = layout.parts(self.output.read_bytes())
        root = layout.xml(members['Contents/section0.xml'])
        fn(root)
        members['Contents/section0.xml'] = layout.E.tostring(root, encoding='utf-8')
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as package:
            for name, data in members.items(): package.writestr(name, data)
        return stream.getvalue()

    def test_target_border_change_is_detected(self):
        after = self.corrupt(lambda root: layout.geometry(next(root.iter(layout.P+'tbl')),True)[0][1,1].set('borderFillIDRef','999'))
        with self.assertRaises(ValueError): layout.verify(self.source.read_bytes(), after, self.request)

    def test_wrong_second_column_alignment_is_detected(self):
        def wrong(root):
            cells,_ = layout.geometry(next(root.iter(layout.P+'tbl')), True)
            layout.paragraphs(cells[1,1])[0].set('paraPrIDRef',layout.paragraphs(cells[1,0])[0].get('paraPrIDRef'))
        after = self.corrupt(wrong)
        with self.assertRaises(ValueError): layout.verify(self.source.read_bytes(), after, self.request)

    def test_repeat_is_semantically_unchanged(self):
        self.apply()
        again = self.output.with_name('again.hwpx')
        layout.apply(self.output, again, dict(self.request, source_sha256=layout.sha(self.output)))
        self.assertEqual(layout.parts(self.output.read_bytes()), layout.parts(again.read_bytes()))


if __name__ == '__main__': unittest.main(verbosity=2)
