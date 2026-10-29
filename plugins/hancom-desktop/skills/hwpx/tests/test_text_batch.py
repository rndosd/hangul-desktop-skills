import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from hwpx import HwpxDocument
import safe_edit as edit
import safe_format as formatting
import safe_word_wrap as wrapping

SKILL = Path.home()/'.codex/skills/hwpx'
spec = importlib.util.spec_from_file_location('baseline_safe_edit', SKILL/'scripts/safe_edit.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


def members(path):
    with ZipFile(path) as z:
        return {name: z.read(name) for name in z.namelist()}


class BatchSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'source.hwpx'
        self.output = self.root/'result.hwpx'
        with HwpxDocument.new() as doc:
            p = doc.add_paragraph('', include_run=False)
            p.add_run('AB', bold=True)
            p.add_run('ABA ALPHA', italic=True)
            doc.add_paragraph('ALPHA BETA')
            table = doc.add_table(2, 3)
            table.merge_cells(0, 0, 1, 1)
            table.cell(0, 0).set_text('ALPHA BETA')
            table.cell(0, 2).set_text('ALPHA')
            table.cell(1, 2).set_text('BETA')
            host = doc.add_table(1, 1).cell(0, 0)
            host.set_text('HOST')
            host.add_table(1, 1).cell(0, 0).set_text('INNER')
            section = doc.add_section()
            doc.add_paragraph('ALPHA BETA', section=section)
            doc.save_to_path(self.source)
        self.original = self.source.read_bytes()
        self.sha = edit.digest(self.source)
        self.queries = [
            {'find': 'ALPHA'}, {'find': 'BETA'}, {'find': 'ABA'},
            {'find': 'ALPHA', 'limit': 1},
            {'find': 'ALPHA', 'table': 1, 'row': 2, 'column': 2},
            {'find': 'ALPHA', 'table': 1, 'row': 1, 'column': 3},
            {'find': 'HOST'}, {'find': 'INNER'}, {'find': 'MISSING'},
        ]

    def plan(self):
        listings = edit.inspect_many(self.source, [{'find': 'ALPHA'}, {'find': 'BETA'}])
        plans = [edit.make_plan(item, [item['targets'][0]['target_id']], value)
                 for item, value in zip(listings, ['LONGER', 'B'])]
        plans[0]['edits'].extend(plans[1]['edits'])
        return plans[0]

    def test_matches_installed_single_inspections_exactly(self):
        expected = [baseline.inspect_targets(self.source, **q) for q in self.queries]
        actual = edit.inspect_many(self.source, self.queries)
        self.assertEqual(actual, expected)
        self.assertEqual([t['start'] for t in actual[2]['targets']], [0, 2])
        self.assertEqual(actual[4]['targets'][0]['scope']['row_span'], 2)
        self.assertFalse(actual[6]['targets'][0]['supported'])
        self.assertFalse(actual[7]['targets'][0]['supported'])
        self.assertEqual(actual[0], edit.inspect_targets(self.source, 'ALPHA'))

    def test_one_parse_and_one_view_per_paragraph_with_duplicate_queries(self):
        paragraph_count = sum(sum(edit.local(n) == 'p' for n in root.iter())
                              for _, root in edit.sections(self.source))
        with patch.object(edit, 'sections', wraps=edit.sections) as parsed:
            with patch.object(edit, 'paragraph_view', wraps=edit.paragraph_view) as viewed:
                edit.inspect_many(self.source, self.queries)
        self.assertEqual(parsed.call_count, 1)
        self.assertEqual(viewed.call_count, paragraph_count)
        self.assertIsInstance(parsed.call_args.args[0], io.BytesIO)
        self.assertEqual(hashlib.sha256(parsed.call_args.args[0].getvalue()).hexdigest(), self.sha)

    def test_invalid_later_query_has_no_partial_result_or_parse(self):
        invalid = [{'find': ''}, {'find': 'ALPHA', 'row': 1},
                   {'find': 'ALPHA', 'table': 1, 'row': -1, 'column': 1},
                   {'find': 'ALPHA', 'limit': 0}, {'find': 'ALPHA', 'extra': 1}, None]
        for query in invalid:
            with self.subTest(query=query), patch.object(edit, 'sections', wraps=edit.sections) as parsed:
                with self.assertRaises(ValueError):
                    edit.inspect_many(self.source, [{'find': 'ALPHA'}, query])
                parsed.assert_not_called()
        with self.assertRaises(ValueError):
            edit.inspect_many(self.source, [])

    def test_changed_read_bytes_never_receive_old_hash(self):
        with patch.object(edit, 'digest', return_value='0'*64):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                edit.inspect_many(self.source, self.queries)

    def test_change_after_snapshot_rejects_whole_inspection(self):
        original = edit.sections
        def changed(data):
            self.source.write_bytes(self.original + b'changed')
            return original(data)
        with patch.object(edit, 'sections', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'source changed during inspection'):
                edit.inspect_many(self.source, self.queries)

    def test_compile_parses_once_and_matches_baseline_updates(self):
        plan = self.plan()
        expected = baseline.compile_edits(self.source, plan, self.sha)
        with patch.object(edit, 'sections', wraps=edit.sections) as parsed:
            actual = edit.compile_edits(self.source, plan, self.sha)
        self.assertEqual(parsed.call_count, 1)
        self.assertEqual(actual, expected)

    def test_apply_has_identical_zip_members_and_run_diff(self):
        plan = self.plan()
        old_output = self.root/'baseline.hwpx'
        old = baseline.apply_plan(self.source, old_output, plan)
        new = edit.apply_plan(self.source, self.output, plan)
        self.assertEqual(new['run_diff'], old['run_diff'])
        self.assertEqual(members(self.output), members(old_output))
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_stale_duplicate_overlap_and_late_bad_target_never_publish(self):
        base = self.plan()
        stale = dict(base, source_sha256='0'*64)
        duplicate = copy.deepcopy(base)
        duplicate['edits'].append(duplicate['edits'][0])
        bad = copy.deepcopy(base)
        bad['edits'].append({'find': 'BETA', 'replace': 'new', 'target_id': 'wrong'})
        listings = edit.inspect_many(self.source, [{'find': 'ABA'}, {'find': 'BAB'}])
        overlap = edit.make_plan(listings[0], [listings[0]['targets'][0]['target_id']], 'X')
        overlap['edits'].extend(edit.make_plan(listings[1], [listings[1]['targets'][0]['target_id']], 'Y')['edits'])
        for plan in [stale, duplicate, overlap, bad]:
            with self.subTest(plan=plan):
                with self.assertRaises(ValueError):
                    edit.apply_plan(self.source, self.output, plan)
                self.assertFalse(self.output.exists())
                self.assertEqual(self.source.read_bytes(), self.original)

    def run_cli(self, *args):
        env = os.environ.copy()
        env['PYTHONPATH'] = os.pathsep.join([str(Path(edit.__file__).parent), str(SKILL/'scripts'), str(SKILL/'vendor')])
        process = subprocess.run([sys.executable, '-X', 'utf8', '-B',
                                  str(SKILL/'scripts/candidate_runtime.py'), str(Path(edit.__file__)),
                                  *map(str, args)], capture_output=True, text=True, encoding='utf-8', env=env)
        return process.returncode, json.loads(process.stdout)

    def test_inspect_many_cli_and_invalid_late_query_publish_nothing(self):
        queries = self.root/'queries.json'
        output = self.root/'inspection.json'
        queries.write_text(json.dumps(self.queries), encoding='utf-8')
        code, result = self.run_cli('inspect-many', self.source, '--queries', queries, '--output', output)
        self.assertEqual(code, 0, result)
        self.assertEqual(result, edit.inspect_many(self.source, self.queries))
        self.assertEqual(json.loads(output.read_text(encoding='utf-8')), result)
        failed = self.root/'failed.json'
        queries.write_text(json.dumps([{'find': 'ALPHA'}, {'find': ''}]), encoding='utf-8')
        code, result = self.run_cli('inspect-many', self.source, '--queries', queries, '--output', failed)
        self.assertEqual(code, 2)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertFalse(failed.exists())


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'source.hwpx'
        self.output = self.root/'result.hwpx'
        with HwpxDocument.new() as doc:
            doc.add_paragraph('First selected paragraph')
            p = doc.add_paragraph('', include_run=False)
            p.add_run('Second ', bold=True)
            p.add_run('selected paragraph', italic=True)
            doc.add_paragraph('Keep this paragraph')
            doc.save_to_path(self.source)
        self.original = self.source.read_bytes()
        self.targets = []
        for text in ['First selected paragraph', 'Second selected paragraph']:
            t = edit.inspect_targets(self.source, text)['targets'][0]
            self.targets.append(dict(part=t['part'], paragraph_path=t['paragraph_path'], expected_text=text))

    def request(self, kind):
        extra = dict(reason='explicit multi-paragraph check')
        if kind == 'format':
            schema = formatting.SCHEMA
            extra.update(letter_spacing=-1, ratio=100)
        else:
            schema = wrapping.SCHEMA
            extra.update(korean='WORD', latin='WORD')
        return dict(schema=schema, source_sha256=edit.digest(self.source),
                    targets=[dict(target, **extra) for target in self.targets])

    def apply(self, kind, plan, dry=False):
        if kind == 'format':
            return formatting.apply_format(self.source, self.output, plan, dry_run=dry)
        return wrapping.apply(self.source, self.output, plan, dry)

    def test_consumers_parse_once_and_preserve_other_content(self):
        for kind in ['format', 'wrap']:
            with self.subTest(kind=kind), patch.object(edit, 'sections', wraps=edit.sections) as parsed:
                report = self.apply(kind, self.request(kind))
                self.assertEqual(parsed.call_count, 1)
                self.assertTrue(report['published'])
                self.assertEqual(self.source.read_bytes(), self.original)
                source_texts = [t['_paragraph_text'] for t in edit.candidates(self.source, 'paragraph', edit.digest(self.source))]
                output_texts = [t['_paragraph_text'] for t in edit.candidates(self.output, 'paragraph', edit.digest(self.output))]
                self.assertEqual(output_texts, source_texts)
            self.output.unlink()

    def test_consumers_dry_run_do_not_publish(self):
        for kind in ['format', 'wrap']:
            with self.subTest(kind=kind):
                self.assertFalse(self.apply(kind, self.request(kind), True)['published'])
                self.assertFalse(self.output.exists())

    def test_consumers_bad_later_target_duplicate_and_stale_block(self):
        for kind in ['format', 'wrap']:
            base = self.request(kind)
            wrong = copy.deepcopy(base)
            wrong['targets'][-1]['expected_text'] = 'missing paragraph'
            duplicate = dict(base, targets=base['targets']*2)
            stale = dict(base, source_sha256='0'*64)
            partial = copy.deepcopy(base)
            partial['targets'][-1]['expected_text'] = 'Second'
            for request in [wrong, duplicate, stale, partial]:
                with self.subTest(kind=kind, request=request):
                    with self.assertRaises(ValueError):
                        self.apply(kind, request)
                    self.assertFalse(self.output.exists())
                    self.assertEqual(self.source.read_bytes(), self.original)

    def test_consumers_still_enforce_format_and_wrap_bounds(self):
        requests = [('format', 'letter_spacing', -20), ('format', 'ratio', 90),
                    ('wrap', 'korean', 'CHARACTER'), ('wrap', 'paragraph_path', [-1])]
        for kind, key, value in requests:
            request = self.request(kind)
            request['targets'][-1][key] = value
            with self.subTest(kind=kind, key=key):
                with self.assertRaises(ValueError):
                    self.apply(kind, request)
                self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
