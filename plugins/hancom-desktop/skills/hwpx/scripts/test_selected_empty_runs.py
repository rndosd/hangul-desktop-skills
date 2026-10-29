# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as E
from zipfile import ZipFile

from hwpx import HwpxDocument
from safe_edit import apply_plan, inspect_targets, make_plan, POLICY, SCHEMA
from test_safe_edit import read_document


class EmptyFormattingRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'source.hwpx'
        self.output = Path(self.temp.name) / 'output.hwpx'

    def fixture(self, *, cell=False, mutation=None):
        doc = HwpxDocument.new()
        if cell:
            paragraph = doc.add_table(1, 1).cell(0, 0).add_paragraph('')
            for child in list(paragraph.element):
                paragraph.element.remove(child)
        else:
            paragraph = doc.add_paragraph('', include_run=False)
        for value, style in [('', 'bold'), ('PRE TAR', 'italic'),
                             ('', 'underline'), ('GET POST', 'bold'), ('', 'italic')]:
            run = paragraph.add_run(value, **{style: True})
            if value == '':
                for child in list(run.element):
                    run.element.remove(child)
        doc.add_paragraph('KEEP')
        doc.save_to_path(self.source)
        doc.close()
        if mutation:
            with ZipFile(self.source) as package:
                members = {name: package.read(name) for name in package.namelist()}
            root = E.fromstring(members['Contents/section0.xml'])
            target = next(n for n in root.iter() if n.tag.endswith('}p')
                          and 'PRE TAR' in ''.join(n.itertext()))
            mutation(target)
            members['Contents/section0.xml'] = E.tostring(root, encoding='utf-8')
            with ZipFile(self.source, 'w') as package:
                for name, data in members.items():
                    package.writestr(name, data)
        self.original = self.source.read_bytes()

    def selection(self):
        listing = inspect_targets(self.source, 'TARGET')
        self.assertEqual(listing['total'], 1)
        return listing, listing['targets'][0]

    def test_cross_run_with_leading_middle_trailing_empty_runs(self):
        for cell in (False, True):
            for replacement in ('EXPANDED_REPLACEMENT', 'X', ''):
                with self.subTest(cell=cell, replacement=replacement):
                    self.fixture(cell=cell)
                    listing, target = self.selection()
                    self.assertTrue(target['supported'], target['reason'])
                    plan = make_plan(listing, [target['target_id']], replacement)
                    dry = apply_plan(self.source, self.output, plan, dry_run=True)
                    self.assertFalse(self.output.exists())
                    receipt = apply_plan(self.source, self.output, plan)
                    self.assertEqual(dry['run_diff'], receipt['run_diff'])
                    self.assertEqual([u['run_path'][0] for u in receipt['run_diff']], [1, 3])
                    before, topology, other = read_document(self.source)
                    after, output_topology, output_other = read_document(self.output)
                    self.assertEqual([text for text, _ in after],
                                     [text.replace('TARGET', replacement) for text, _ in before])
                    self.assertEqual([styles for _, styles in before], [styles for _, styles in after])
                    self.assertEqual(topology, output_topology)
                    self.assertEqual(other, output_other)
                    self.assertEqual(self.original, self.source.read_bytes())
                    self.output.unlink()

    def test_empty_only_paragraph_is_not_a_selected_insertion_target(self):
        doc = HwpxDocument.new()
        paragraph = doc.add_paragraph('', include_run=False)
        run = paragraph.add_run('', bold=True)
        for child in list(run.element):
            run.element.remove(child)
        doc.save_to_path(self.source)
        doc.close()
        self.original = self.source.read_bytes()
        listing = inspect_targets(self.source, 'MISSING')
        self.assertEqual(listing['total'], 0)
        with self.assertRaisesRegex(ValueError, 'find must be nonempty'):
            inspect_targets(self.source, '')
        self.assertEqual(self.original, self.source.read_bytes())

    def test_noop_plan_and_forged_noop_apply_are_rejected(self):
        self.fixture()
        listing, target = self.selection()
        self.assertTrue(target['supported'], target['reason'])
        with self.assertRaisesRegex(ValueError, 'must change'):
            make_plan(listing, [target['target_id']], 'TARGET')
        plan = make_plan(listing, [target['target_id']], 'NEW')
        plan['edits'][0]['replace'] = 'TARGET'
        with self.assertRaisesRegex(ValueError, 'must change'):
            apply_plan(self.source, self.output, plan)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.original, self.source.read_bytes())

    def test_controls_and_mixed_text_remain_rejected(self):
        namespace = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
        def control(paragraph):
            E.SubElement(paragraph[2], namespace + 'ctrl')
        def inline(paragraph):
            E.SubElement(paragraph[1][0], namespace + 'tab')
        def two_texts(paragraph):
            E.SubElement(paragraph[1], namespace + 't')
        def raw_text(paragraph):
            paragraph[2].text = 'HIDDEN_TEXT'
        def unstyled(paragraph):
            paragraph[2].attrib.pop('charPrIDRef')
        for mutate in (control, inline, two_texts, raw_text, unstyled):
            with self.subTest(shape=mutate.__name__):
                self.fixture(mutation=mutate)
                listing, target = self.selection()
                self.assertFalse(target['supported'])
                self.assertEqual(target['reason'], 'unsupported_run_control_or_mixed_text')
                forged = {'schema': SCHEMA, 'source_sha256': listing['source_sha256'],
                          'style_policy': POLICY, 'edits': [
                              {'target_id': target['target_id'], 'find': 'TARGET', 'replace': 'NEW'}]}
                with self.assertRaisesRegex(ValueError, 'unsupported'):
                    apply_plan(self.source, self.output, forged)
                self.assertFalse(self.output.exists())
                self.assertEqual(self.original, self.source.read_bytes())


if __name__ == '__main__':
    unittest.main()
