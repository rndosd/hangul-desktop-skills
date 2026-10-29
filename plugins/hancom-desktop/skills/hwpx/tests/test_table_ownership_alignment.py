from pathlib import Path
import io
import sys
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from candidate_runtime import activate
activate()
from hwpx import HwpxDocument
from hwpx.oxml.paragraph import HwpxOxmlParagraph
from hwpx_automation.office.agent import HwpxAgentDocument
import hangul_task as task
import safe_cell_layout as layout


class ParagraphOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.doc = HwpxDocument.new()
        self.addCleanup(self.doc.close)
        self.table = self.doc.add_table(2, 2)
        self.cell = self.table.cell(0, 0)
        self.cell.paragraphs[0].text = 'keep'
        self.extra = self.cell.add_paragraph('remove')

    def test_cell_removal_persists_and_preserves_other_cells(self):
        sibling = self.table.cell(0, 1).element
        before = layout.snap(sibling)
        self.extra.remove()
        self.assertEqual([p.text for p in self.cell.paragraphs], ['keep'])
        self.assertEqual(layout.snap(sibling), before)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'removed.hwpx'
            output.write_bytes(self.doc.to_bytes())
            with HwpxDocument.open(output) as reopened:
                table = next(t for p in reopened.sections[0].paragraphs for t in p.tables)
                self.assertEqual([p.text for p in table.cell(0, 0).paragraphs], ['keep'])

    def test_nested_cell_uses_its_own_sublist(self):
        nested = self.cell.add_table(2, 2)
        inner = nested.cell(0, 0)
        inner.paragraphs[0].text = 'inner keep'
        extra = inner.add_paragraph('inner remove')
        outer = [p.text for p in self.cell.paragraphs]
        extra.remove()
        self.assertEqual([p.text for p in inner.paragraphs], ['inner keep'])
        self.assertEqual([p.text for p in self.cell.paragraphs], outer)
        with self.assertRaises(ValueError):
            inner.paragraphs[0].remove()

    def test_last_cell_paragraph_refused_without_mutation(self):
        self.extra.remove()
        before = self.doc.to_bytes()
        with self.assertRaises(ValueError):
            self.cell.paragraphs[0].remove()
        self.assertEqual(self.doc.to_bytes(), before)

    def test_stale_wrapper_is_not_successful_noop(self):
        self.extra.remove()
        before = self.doc.to_bytes()
        with self.assertRaises(ValueError):
            self.extra.remove()
        self.assertEqual(self.doc.to_bytes(), before)

    def test_removed_ancestor_makes_nested_wrapper_stale(self):
        self.table.paragraph.remove()
        with self.assertRaises(ValueError):
            self.extra.remove()

    def test_top_level_removal_and_last_section_invariant(self):
        self.table.paragraph.remove()
        p = self.doc.add_paragraph('temporary')
        p.remove()
        self.assertEqual(len(self.doc.sections[0].paragraphs), 1)
        with self.assertRaises(ValueError):
            self.doc.sections[0].paragraphs[0].remove()

    def test_stdlib_tree_nested_owner(self):
        root = ET.fromstring('<section xmlns:p="http://www.hancom.co.kr/hwpml/2011/paragraph"><p:p/><p:subList><p:p/><p:p/></p:subList></section>')
        class Section:
            element = root
            dirty = False
            def mark_dirty(self):
                self.dirty = True
        section = Section()
        owner = root[1]
        HwpxOxmlParagraph(owner[1], section).remove()
        self.assertEqual(len(owner), 1)
        self.assertEqual(len(root), 2)
        self.assertTrue(section.dirty)


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'source.hwpx'
        self.output = Path(self.temp.name) / 'aligned.hwpx'
        with HwpxDocument.new() as doc:
            table = doc.add_table(3, 3)
            table.cell(0, 0).paragraphs[0].text = 'non-target header'
            table.merge_cells(0, 0, 0, 2)
            cell = table.cell(1, 1)
            p = cell.paragraphs[0]
            p.text = 'first '
            p.add_run('bold', bold=True, size=13)
            other = doc.parts.headers[0].ensure_paragraph_format(base_para_pr_id=p.para_pr_id_ref, alignment='RIGHT', line_spacing_percent=190, margins={'left': 200, 'right': 100})
            second = cell.add_paragraph('second ', para_pr_id_ref=other)
            second.add_run('italic', italic=True, color='#112233')
            table.cell(2, 2).add_paragraph('non-target extra paragraph')
            self.source.write_bytes(doc.to_bytes())
        self.req = dict(schema=layout.SCHEMA, source_sha256=layout.sha(self.source), table=1, operation='align', range=[2, 2, 2, 2], alignment='CENTER')

    def target(self, data):
        _, _, _, table = layout.locate(data, 1)
        return layout.geometry(table, True)[0][1, 1]

    def test_all_selected_paragraphs_align_with_run_styles_preserved(self):
        original = self.source.read_bytes()
        report = layout.apply(self.source, self.output, self.req)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertTrue(report['checks']['stylesPreserved'])
        before = self.target(original)
        after = self.target(self.output.read_bytes())
        bps, aps = layout.paragraphs(before), layout.paragraphs(after)
        self.assertEqual(len(aps), 2)
        self.assertEqual([layout.snap(r) for p in bps for r in p.findall(layout.P+'run')],
                         [layout.snap(r) for p in aps for r in p.findall(layout.P+'run')])
        header = layout.xml(layout.parts(self.output.read_bytes())['Contents/header.xml'])
        defs = {p.get('id'): p for p in header.iter(layout.H+'paraPr')}
        self.assertEqual([defs[p.get('paraPrIDRef')].find(layout.H+'align').get('horizontal') for p in aps], ['CENTER', 'CENTER'])

    def test_single_target_with_other_multirun_multiparagraph_merged_cells(self):
        layout.apply(self.source, self.output, dict(self.req, range=[3, 1, 3, 1]))
        self.assertTrue(self.output.exists())

    def test_repeated_alignment_is_semantically_unchanged(self):
        layout.apply(self.source, self.output, self.req)
        again = self.output.with_name('again.hwpx')
        layout.apply(self.output, again, dict(self.req, source_sha256=layout.sha(self.output)))
        before = layout.parts(self.output.read_bytes())
        after = layout.parts(again.read_bytes())
        self.assertEqual(before, after)

    def test_dry_run_is_not_published(self):
        report = layout.apply(self.source, self.output, self.req, True)
        self.assertFalse(report['published'])
        self.assertFalse(self.output.exists())

    def test_left_and_right_alignments(self):
        for alignment in ['LEFT', 'RIGHT']:
            output = self.output.with_name(alignment+'.hwpx')
            layout.apply(self.source, output, dict(self.req, alignment=alignment))
            members = layout.parts(output.read_bytes())
            header = layout.xml(members['Contents/header.xml'])
            defs = {p.get('id'): p for p in header.iter(layout.H+'paraPr')}
            ps = layout.paragraphs(self.target(output.read_bytes()))
            self.assertEqual([defs[p.get('paraPrIDRef')].find(layout.H+'align').get('horizontal') for p in ps], [alignment, alignment])

    def test_plain_blank_merge_unmerge_still_preserves_styles(self):
        with HwpxDocument.new() as doc:
            doc.add_table(2, 3, width=30000, height=10000)
            self.source.write_bytes(doc.to_bytes())
        request = dict(self.req, source_sha256=layout.sha(self.source), operation='merge', range=[2, 1, 2, 3])
        layout.apply(self.source, self.output, request)
        _, _, _, table = layout.locate(self.output.read_bytes(), 1)
        self.assertEqual(layout.span(layout.geometry(table)[0][1, 0]), (1, 3))
        split = self.output.with_name('split.hwpx')
        report = layout.apply(self.output, split, dict(request, source_sha256=layout.sha(self.output), operation='unmerge'))
        self.assertTrue(report['checks']['stylesPreserved'])
        _, _, _, table = layout.locate(split.read_bytes(), 1)
        self.assertEqual(len(layout.geometry(table)[0]), 6)

    def test_stale_revision_is_not_published(self):
        with self.assertRaises(ValueError):
            layout.apply(self.source, self.output, dict(self.req, source_sha256='0'*64))
        self.assertFalse(self.output.exists())

    def test_missing_coordinate_is_not_published(self):
        with self.assertRaises(ValueError):
            layout.apply(self.source, self.output, dict(self.req, range=[5, 1, 5, 1]))
        self.assertFalse(self.output.exists())

    def test_merge_keeps_single_paragraph_run_scope(self):
        with self.assertRaises(ValueError):
            layout.apply(self.source, self.output, dict(self.req, operation='merge', range=[2, 1, 2, 2]))
        self.assertFalse(self.output.exists())

    def corrupted(self, fn):
        layout.apply(self.source, self.output, self.req)
        members = layout.parts(self.output.read_bytes())
        root = layout.xml(members['Contents/section0.xml'])
        fn(root)
        members['Contents/section0.xml'] = layout.E.tostring(root, encoding='utf-8')
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as package:
            for name, data in members.items():
                package.writestr(name, data)
        return buf.getvalue()

    def test_second_paragraph_run_style_corruption_is_detected(self):
        def corrupt(root):
            table = next(root.iter(layout.P+'tbl'))
            cell = layout.geometry(table, True)[0][1, 1]
            layout.paragraphs(cell)[1].find(layout.P+'run').set('charPrIDRef', '999')
        after = self.corrupted(corrupt)
        with self.assertRaises(ValueError):
            layout.verify(self.source.read_bytes(), after, self.req)

    def test_non_target_tail_corruption_is_detected(self):
        after = self.corrupted(lambda root: setattr(next(root.iter(layout.P+'t')), 'tail', 'unexpected text'))
        with self.assertRaises(ValueError):
            layout.verify(self.source.read_bytes(), after, self.req)

    def test_duplicate_source_ids_are_preserved_for_alignment(self):
        with HwpxDocument.open(self.source) as doc:
            ps = [p for p in doc.sections[0].element.iter(layout.P+'p')]
            ps[-1].set('id', ps[-2].get('id'))
            doc.sections[0].mark_dirty()
            self.source.write_bytes(doc.to_bytes())
        self.req['source_sha256'] = layout.sha(self.source)
        report = layout.apply(self.source, self.output, self.req)
        self.assertFalse(report['checks']['paragraphIdsUnique'])
        _, _, before, _ = layout.locate(self.source.read_bytes(), 1)
        _, _, after, _ = layout.locate(self.output.read_bytes(), 1)
        self.assertEqual([p.get('id') for p in before.iter(layout.P+'p')], [p.get('id') for p in after.iter(layout.P+'p')])


class BatchRemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'source.hwpx'
        self.output = Path(self.temp.name) / 'output.hwpx'
        with HwpxDocument.new() as doc:
            table = doc.add_table(2, 2)
            table.cell(0, 0).paragraphs[0].text = 'keep'
            table.cell(0, 0).add_paragraph('remove')
            self.source.write_bytes(doc.to_bytes())
        with HwpxAgentDocument.open(self.source) as agent:
            paths = {record.summary.get('text'): record.path for record in agent.records if record.kind == 'paragraph'}
        self.remove_path = paths['remove']
        self.keep_path = paths['keep']
        self.request = dict(schemaVersion='hwpx.agent-batch/v1', input={'filename': str(self.source)}, output={'filename': str(self.output), 'overwrite': False},
                            expectedRevision='sha256:'+layout.sha(self.source), quality='transparent', dryRun=False, idempotencyKey='remove-cell-test',
                            verificationRequirements=['package', 'reopen', 'openSafety', 'semanticDiff', 'bytePreservation'],
                            commands=[dict(commandId='remove', op='remove', path=self.remove_path)])

    def test_last_paragraph_failure_rolls_back_prior_command(self):
        self.request['commands'].append(dict(commandId='remove-last', op='remove', path=self.keep_path))
        original = self.source.read_bytes()
        result = task.batch(self.request)
        self.assertFalse(result['ok'])
        self.assertTrue(result['rolledBack'])
        self.assertEqual([c['commandId'] for c in result['commandResults']], ['remove'])
        self.assertTrue(result['commandResults'][0]['ok'])
        self.assertIsNotNone(result.get('error'))
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), original)

    def test_batch_removes_selected_paragraph_and_reopens(self):
        result = task.batch(self.request)
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['verificationReport']['openSafety']['ok'])
        with HwpxDocument.open(self.output) as doc:
            table = next(t for p in doc.sections[0].paragraphs for t in p.tables)
            self.assertEqual([p.text for p in table.cell(0, 0).paragraphs], ['keep'])

    def test_missing_target_is_not_reported_successful(self):
        self.request['commands'][0]['path'] = self.remove_path.rsplit('/', 1)[0]+'/paragraph[99]'
        result = task.batch(self.request)
        self.assertFalse(result['ok'])
        self.assertFalse(self.output.exists())

    def test_stale_revision_is_not_published(self):
        self.request['expectedRevision'] = 'sha256:'+'0'*64
        result = task.batch(self.request)
        self.assertFalse(result['ok'])
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
