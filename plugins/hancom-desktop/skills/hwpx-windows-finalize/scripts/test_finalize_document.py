from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

import finalize_document as finalize
import hancom_completion_gate as gate


class FinalizeDocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='finalize-wrapper-', dir=os.environ.get('HWPX_TEST_TMP'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'source.hwpx'
        fixture = Path(__file__).resolve().parents[2] / 'hwpx/assets/mixed-runs/source.hwpx'
        shutil.copyfile(fixture, self.source)
        self.final = self.root / 'final.hwpx'
        self.pdf = self.root / 'final.pdf'
        self.bundle = self.root / 'evidence'
        self.native_jobs = []

    def invoke(self, command='run', **changes):
        args = {'source': str(self.source), 'final': str(self.final), 'pdf': str(self.pdf),
                'bundle': str(self.bundle), 'context': 'ordinary-shell', 'timeout': '120'}
        args.update(changes)
        if command == 'run':
            argv = ['run', args.pop('source')]
        else:
            argv = ['check']
            args = {'bundle': args['bundle'], 'review': str(self.bundle / 'review.json'), **changes}
        for key, value in args.items():
            argv.extend(['--' + key, str(value)])
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = finalize.main(argv)
        return code, json.loads(stdout.getvalue())

    def native_success(self, source, mode, final, pdf, run_dir, context, timeout):
        self.native_jobs.append({'source': source, 'mode': mode, 'run': str(run_dir)})
        runner = Path(run_dir)
        native_dir = runner / 'native'
        native_dir.mkdir(parents=True)
        shutil.copyfile(source, final)
        with pymupdf.open() as doc:
            doc.new_page().insert_text((50, 50), 'Synthetic native adapter test')
            doc.save(pdf)
        receipt = {
            'evidenceSchema': 'hwpx.hancom-finalize.v2', 'status': 'PASS_FULL',
            'sourceUnchanged': True, 'sourceSha256Before': gate.ref(source)['sha256'],
            'sourceSha256After': gate.ref(source)['sha256'], 'candidatePath': str(source),
            'finalPath': str(final), 'mode': 'SaveAs', 'firstOpen': True, 'saveAs': True,
            'reopen': True, 'pdfExport': True,
            'cleanup': {'owned': True, 'quit': True, 'forced': False, 'remaining': []},
            'artifacts': [gate.ref(final), gate.ref(pdf)],
        }
        gate.write_new(native_dir / 'job.json', {'input': str(source), 'output': str(final), 'pdf': str(pdf)})
        gate.write_new(native_dir / 'receipt.json', receipt)
        result = {'status': 'PASS_NATIVE', 'sourceUnchanged': True}
        gate.write_new(runner / 'runner-result.json', result)
        return result

    def reviewed_fixture(self):
        review = gate.load(self.bundle / 'review-template.json')
        review.update(reviewer='synthetic-unit-test', reviewedAt='2026-10-26T00:00:00Z')
        review['preservation']['performed'] = True
        for item in review['preservation']['checks'].values():
            item.update(outcome='pass', observation='Synthetic fixture preserves exact source bytes.')
        for item in review['preservation']['reviewedMembers']:
            item['reason'] = 'Synthetic fixture checks the expected unchanged package.'
        review['visual']['performed'] = True
        for item in review['visual']['pages']:
            item.update(outcome='pass', observation='Synthetic PDF image fixture is bound to this review.')
        gate.write_new(self.bundle / 'review.json', review)

    def test_native_run_collects_at_correct_path_and_retry_does_not_run_native(self):
        before = self.source.read_bytes()
        with patch.object(finalize.native, 'run', side_effect=self.native_success):
            code, first = self.invoke()
            pdf_before = self.pdf.read_bytes()
            again_code, again = self.invoke()
        self.assertEqual((code, again_code), (2, 2))
        self.assertEqual(first['status'], 'pending')
        self.assertFalse(first['reused'])
        self.assertTrue(again['reused'])
        self.assertEqual(len(self.native_jobs), 1)
        self.assertEqual(self.native_jobs[0]['run'], str(self.bundle / 'runner'))
        self.assertEqual(gate.load(self.bundle / 'plan.json')['run'], str(self.bundle / 'runner/native'))
        self.assertEqual(self.pdf.read_bytes(), pdf_before)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertTrue((self.bundle / 'review-template.json').is_file())

    def test_changed_request_or_source_is_rejected_without_another_native_job(self):
        with patch.object(finalize.native, 'run', side_effect=self.native_success):
            self.invoke()
            for changes in ({'context': 'host-approved'}, {'timeout': '121'},
                            {'final': self.root / 'other.hwpx'}):
                with self.subTest(changes=changes):
                    code, result = self.invoke(**changes)
                    self.assertEqual(code, 3)
                    self.assertEqual(result['reason'], 'request_mismatch')
            self.source.write_bytes(self.source.read_bytes() + b'changed')
            code, result = self.invoke()
        self.assertEqual(code, 3)
        self.assertEqual(result['reason'], 'request_mismatch')
        self.assertEqual(len(self.native_jobs), 1)

    def test_failed_native_does_not_collect_or_become_complete(self):
        def failed(*args):
            runner = Path(args[4])
            runner.mkdir()
            result = {'status': 'BLOCKED_NATIVE', 'sourceUnchanged': True}
            gate.write_new(runner / 'runner-result.json', result)
            return result
        with patch.object(finalize.native, 'run', side_effect=failed) as adapter:
            code, result = self.invoke()
            again_code, again = self.invoke()
        self.assertEqual((code, again_code), (3, 3))
        self.assertEqual(result['nativeStatus'], 'BLOCKED_NATIVE')
        self.assertEqual(again['reason'], 'native_job_not_successful')
        self.assertEqual(adapter.call_count, 1)
        self.assertFalse((self.bundle / 'evidence.json').exists())

    def test_unknown_native_result_is_not_retried(self):
        with patch.object(finalize.native, 'run', side_effect=OSError('interrupted')) as adapter:
            code, result = self.invoke()
            again_code, again = self.invoke()
        self.assertEqual((code, again_code), (3, 3))
        self.assertEqual(again['reason'], 'native_result_unresolved')
        self.assertEqual(adapter.call_count, 1)

    def test_collection_resumes_after_native_without_repeating_native(self):
        with patch.object(finalize.native, 'run', side_effect=self.native_success):
            with patch.object(gate, 'collect', side_effect=gate.GateError('dependency_unavailable', 'pending')):
                code, result = self.invoke()
            resumed_code, resumed = self.invoke()
        self.assertEqual((code, resumed_code), (2, 2))
        self.assertTrue(resumed['reused'])
        self.assertEqual(len(self.native_jobs), 1)
        self.assertTrue((self.bundle / 'evidence.json').is_file())

    def test_partial_collection_is_preserved_and_not_restarted(self):
        with patch.object(finalize.native, 'run', side_effect=self.native_success):
            with patch.object(gate, 'collect', side_effect=gate.GateError('interrupted', 'pending')):
                self.invoke()
            pages = self.bundle / 'pages'
            pages.mkdir()
            marker = pages / 'partial.txt'
            marker.write_text('preserve evidence', encoding='utf-8')
            code, result = self.invoke()
        self.assertEqual(code, 3)
        self.assertEqual(result['reason'], 'partial_collection_requires_inspection')
        self.assertEqual(marker.read_text(encoding='utf-8'), 'preserve evidence')
        self.assertEqual(len(self.native_jobs), 1)

    def test_check_requires_review_and_rechecks_final_bytes(self):
        with patch.object(finalize.native, 'run', side_effect=self.native_success):
            self.invoke()
        code, result = self.invoke('check', review=self.bundle / 'review-template.json')
        self.assertEqual(code, 2)
        self.assertEqual(result['status'], 'pending')
        self.reviewed_fixture()
        code, result = self.invoke('check')
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'complete')
        self.pdf.write_bytes(self.pdf.read_bytes() + b'changed')
        code, result = self.invoke('check')
        self.assertEqual(code, 3)
        self.assertEqual(result['status'], 'blocked')

    def test_existing_output_is_preserved_without_native_launch(self):
        self.final.write_bytes(b'existing user output')
        with patch.object(finalize.native, 'run') as adapter:
            code, result = self.invoke()
        self.assertEqual(code, 3)
        adapter.assert_not_called()
        self.assertEqual(self.final.read_bytes(), b'existing user output')
        self.assertFalse(self.bundle.exists())

    def test_resumed_output_tamper_is_rejected_without_native_launch(self):
        with patch.object(finalize.native, 'run', side_effect=self.native_success):
            self.invoke()
            self.final.write_bytes(self.final.read_bytes() + b'changed')
            code, result = self.invoke()
        self.assertEqual(code, 3)
        self.assertEqual(result['reason'], 'COM_artifact_hash_mismatch')
        self.assertEqual(len(self.native_jobs), 1)


if __name__ == '__main__':
    unittest.main()
