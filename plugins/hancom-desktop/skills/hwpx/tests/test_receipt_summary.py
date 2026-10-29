from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from inspection_summary import saved_edit_summary


class ReceiptSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'result.hwpx'

    def test_complete_receipt_and_bounded_diagnostics(self):
        value = {'status': 'PASS_STRUCTURE', 'documentPublished': True,
                 'commandResults': [{'ok': True, 'warnings': [f'warning {i}'],
                                     'changedProperties': {'text': 'a' * 1000}} for i in range(86)],
                 'layout_follow_up': [{'reason': 'newly_blank_cell_paragraph', 'scope': 'cell 4'}]}
        result = saved_edit_summary(value, self.output)
        self.assertEqual(json.loads(Path(result['receiptPath']).read_text(encoding='utf-8')), value)
        self.assertEqual(result['commands'], {'total': 86, 'failed': 0})
        self.assertEqual(result['warnings']['additionalInReceipt'], 80)
        self.assertEqual(result['followUp']['count'], 1)
        self.assertLess(len(json.dumps(result)), len(json.dumps(value)) / 10)
        self.assertEqual(saved_edit_summary(value, self.output), result)

    def test_failure_and_dry_run_remain_visible(self):
        value = {'status': 'BLOCKED', 'ok': False, 'rolledBack': True, 'dryRun': True,
                 'documentPublished': False, 'errors': [{'code': 'stale_revision', 'message': 'source changed'}]}
        result = saved_edit_summary(value, self.output)
        self.assertFalse(result['ok'])
        self.assertTrue(result['rolledBack'])
        self.assertTrue(result['dryRun'])
        self.assertEqual(result['errors']['items'][0]['detail']['code'], 'stale_revision')
        self.assertFalse(self.output.exists())

    def test_selected_text_receipt_preserves_its_existing_field_names(self):
        value = {'status': 'PASS_STRUCTURE_DRY_RUN', 'published': False,
                 'source_sha256': 'source', 'output_sha256': 'candidate', 'changed_runs': 2}
        result = saved_edit_summary(value, self.output)
        self.assertFalse(result['published'])
        self.assertEqual(result['source_sha256'], 'source')
        self.assertEqual(result['changed_runs'], 2)
        self.assertEqual(result['output']['filename'], str(self.output))

    def test_storage_failure_does_not_lie_about_published_document(self):
        value = {'status': 'PASS_STRUCTURE', 'documentPublished': True, 'commandResults': [{'ok': True}]}
        with patch.object(Path, 'open', side_effect=PermissionError('test denied')):
            result = saved_edit_summary(value, self.output)
        self.assertTrue(result['documentPublished'])
        self.assertEqual(result['status'], 'PASS_STRUCTURE')
        self.assertEqual(result['commandResults'], value['commandResults'])
        self.assertIn('receiptWarning', result)

    def test_existing_receipt_collision_is_preserved(self):
        value = {'status': 'PASS_STRUCTURE'}
        raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        receipt = self.output.with_name(self.output.name + '.receipt.' + hashlib.sha256(raw).hexdigest()[:16] + '.json')
        receipt.write_text('existing unrelated content', encoding='utf-8')
        result = saved_edit_summary(value, self.output)
        self.assertIn('receiptWarning', result)
        self.assertEqual(receipt.read_text(encoding='utf-8'), 'existing unrelated content')


if __name__ == '__main__':
    unittest.main()
