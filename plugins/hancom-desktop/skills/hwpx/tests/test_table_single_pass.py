import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hwpx import HwpxDocument
import hangul_task as task
import safe_mixed_table_structure as guarded
import semantic_table_binding as binding


class TableSinglePassTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'source.hwpx'
        self.output = self.root/'result.hwpx'
        with HwpxDocument.new() as doc:
            table = doc.add_table(4, 2)
            for row, values in enumerate([['Key', 'Details'], ['Remove', 'Old complete description'],
                                          ['Anchor', 'Keep complete description'], ['Last', 'Keep last row']]):
                for col, value in enumerate(values):
                    table.cell(row, col).set_text(value)
            doc.save_to_path(self.source)
        self.original = self.source.read_bytes()
        self.request = dict(schema=task.SCHEMA, operation='table', headers=['Key', 'Details'],
                            reason='Test all requested stages and exact content preservation', operations=[
            dict(op='delete', key={'Key': 'Remove'}),
            dict(op='insert_after', key={'Key': 'Anchor'}, cells=['New', 'Complete new description'], heightHwpunit=2400),
            dict(op='insert_after', key={'Key': 'New'}, cells=['Final', 'Depends on prior insertion'], heightHwpunit=2400),
        ])

    def test_each_stage_is_guarded_once_and_rebinds_current_output(self):
        with patch.object(guarded, 'apply', wraps=guarded.apply) as applied:
            report = task.table(self.source, self.output, self.request)
        self.assertEqual(applied.call_count, 3)
        self.assertEqual([call.args[3] for call in applied.call_args_list], [False]*3)
        self.assertTrue(all(stage['checks']['entireNonTargetPackageExact'] for stage in report['stages']))
        self.assertEqual(report['stages'][0]['binding']['sourceSha256'], task.sha(self.source))
        hashes = [stage['binding']['sourceSha256'] for stage in report['stages']]
        self.assertEqual(len(set(hashes)), 3)
        found = binding.bind(self.output, self.request['headers'], {'Key': 'Final'})
        self.assertEqual(found['values'], ['Final', 'Depends on prior insertion'])
        self.assertEqual(found['rows'], 5)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_outer_dry_run_checks_every_stage_without_publication(self):
        with patch.object(guarded, 'apply', wraps=guarded.apply) as applied:
            report = task.table(self.source, self.output, self.request, True)
        self.assertEqual(applied.call_count, 3)
        self.assertTrue(report['dryRun'])
        self.assertFalse(report['documentPublished'])
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_late_guard_failure_preserves_source_and_has_no_final_output(self):
        request = copy.deepcopy(self.request)
        request['operations'][-1]['heightHwpunit'] = 99999
        with patch.object(guarded, 'apply', wraps=guarded.apply) as applied:
            with self.assertRaisesRegex(ValueError, 'bounded explicit new row height'):
                task.table(self.source, self.output, request)
        self.assertEqual(applied.call_count, 3)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_late_binding_failure_has_no_partial_final_output(self):
        request = copy.deepcopy(self.request)
        request['operations'][-1]['key'] = {'Key': 'Not present'}
        with self.assertRaisesRegex(ValueError, 'absent or ambiguous'):
            task.table(self.source, self.output, request)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_preservation_failure_in_last_stage_is_not_ignored(self):
        verify = guarded.verify
        calls = []
        def fail_last(before, after, request):
            calls.append(request)
            if len(calls) == 3:
                raise ValueError('injected final preservation failure')
            return verify(before, after, request)
        with patch.object(guarded, 'verify', side_effect=fail_last):
            with self.assertRaisesRegex(ValueError, 'final preservation failure'):
                task.table(self.source, self.output, self.request)
        self.assertEqual(len(calls), 3)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_changed_original_blocks_final_publication(self):
        apply = guarded.apply
        calls = []
        def changed(*args):
            report = apply(*args)
            calls.append(args)
            if len(calls) == 3:
                self.source.write_bytes(self.original + b'external change')
            return report
        with patch.object(guarded, 'apply', side_effect=changed):
            with self.assertRaisesRegex(ValueError, '원본 변경'):
                task.table(self.source, self.output, self.request)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_preserved(self):
        self.output.write_bytes(b'keep')
        with patch.object(guarded, 'apply', wraps=guarded.apply) as applied:
            with self.assertRaises(ValueError):
                task.table(self.source, self.output, self.request)
        applied.assert_not_called()
        self.assertEqual(self.output.read_bytes(), b'keep')


if __name__ == '__main__':
    unittest.main(verbosity=2)
