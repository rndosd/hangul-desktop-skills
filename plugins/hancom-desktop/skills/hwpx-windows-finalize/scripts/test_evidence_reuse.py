"""Synthetic receipts test evidence linkage, not native or visual quality."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pymupdf
import hancom_completion_gate as gate
import finalize_document as finalize
import test_hancom_completion_gate as gate_fixtures
import test_finalize_document as finalize_fixtures


class EvidenceReuseTests(gate_fixtures.CompletionGateTest):
    def test_collect_proofs_reused_but_review_still_checked(self):
        with patch.object(gate, 'read_package', side_effect=AssertionError('repeated XML parse')), \
             patch.object(pymupdf.Page, 'get_pixmap', side_effect=AssertionError('repeated render')):
            self.assertEqual(gate.check(self.bundle, self.review_path)['status'], 'complete')
            self.review['visual']['performed'] = False
            gate_fixtures.save(self.review_path, self.review)
            self.assert_gate('reviews_not_performed', 'pending')

    def test_fresh_process_proofs_are_recomputed(self):
        gate._comparison_cache = gate._render_cache = None
        with patch.object(gate, 'read_package', wraps=gate.read_package) as reader:
            self.assertEqual(gate.check(self.bundle, self.review_path)['status'], 'complete')
        self.assertEqual(reader.call_count, 2)
        self.assertIsNotNone(gate._render_cache)

    def test_proof_result_mutation_cannot_change_later_checks(self):
        result = gate.compare(self.source, self.final)
        result['invariants']['texts'] = False
        proofs = gate._render_proofs(self.pdf)
        proofs[0]['sha256'] = '0' * 64
        self.assertEqual(gate.check(self.bundle, self.review_path)['status'], 'complete')

    def test_self_consistent_fake_png_is_not_a_render_proof(self):
        evidence_path = self.bundle / 'evidence.json'
        evidence = gate.load(evidence_path)
        image = Path(evidence['pages'][0]['image']['path'])
        image.write_bytes(b'fake image with updated disk hashes')
        evidence['pages'][0]['image'] = gate.ref(image)
        gate_fixtures.save(evidence_path, evidence)
        self.review['evidence'] = gate.ref(evidence_path)
        self.review['visual']['pages'][0]['image'] = gate.ref(image)
        gate_fixtures.save(self.review_path, self.review)
        self.assert_gate('render_does_not_match_pdf')
        gate._render_cache = None
        self.assert_gate('render_does_not_match_pdf')

    def test_changed_pdf_with_updated_receipt_cannot_reuse_old_pages(self):
        replacement = self.root / 'replacement.pdf'
        with pymupdf.open() as doc:
            doc.new_page().insert_text((72, 72), 'different rendered document')
            doc.save(replacement)
        self.pdf.write_bytes(replacement.read_bytes())
        self.receipt['artifacts'] = [gate.ref(self.final), gate.ref(self.pdf)]
        gate_fixtures.save(self.run / 'receipt.json', self.receipt)
        evidence_path = self.bundle / 'evidence.json'
        evidence = gate.load(evidence_path)
        evidence['artifacts'] = gate.native_evidence(gate.load(self.bundle / 'plan.json'))
        gate_fixtures.save(evidence_path, evidence)
        self.assert_gate('render_does_not_match_pdf')

    def test_other_hwpx_with_updated_receipt_recomputes_comparison(self):
        gate_fixtures.hwpx(self.final, text='different content')
        self.receipt['artifacts'] = [gate.ref(self.final), gate.ref(self.pdf)]
        gate_fixtures.save(self.run / 'receipt.json', self.receipt)
        evidence_path = self.bundle / 'evidence.json'
        evidence = gate.load(evidence_path)
        evidence['artifacts'] = gate.native_evidence(gate.load(self.bundle / 'plan.json'))
        gate_fixtures.save(evidence_path, evidence)
        self.assert_gate('native_content_counts_or_assets_changed')

    def test_cache_size_and_renderer_changes_force_real_work(self):
        gate._comparison_cache = gate._render_cache = None
        with patch.object(gate, '_COMPARISON_CACHE_LIMIT', 0), patch.object(gate, '_RENDER_CACHE_LIMIT', 0):
            gate.compare(self.source, self.final)
            gate._render_proofs(self.pdf)
            self.assertIsNone(gate._comparison_cache)
            self.assertIsNone(gate._render_cache)
        gate._render_proofs(self.pdf)
        original = pymupdf.Page.get_pixmap
        calls = []
        def observed(page, *args, **kwargs):
            calls.append(page.number)
            return original(page, *args, **kwargs)
        with patch.object(pymupdf, 'VersionBind', 'test-version-change'), patch.object(pymupdf.Page, 'get_pixmap', new=observed):
            gate._render_proofs(self.pdf)
        self.assertEqual(calls, [0])


class PendingStatusReuseTests(finalize_fixtures.FinalizeDocumentTests):
    def test_retry_reuses_collected_comparison_only_for_pending_status(self):
        with patch.object(finalize.native, 'run', side_effect=self.native_success):
            self.invoke()
            with patch.object(gate, 'compare', side_effect=AssertionError('status must not compare')):
                code, result = self.invoke()
        self.assertEqual(code, 2)
        self.assertEqual(result['status'], 'pending')
        self.assertTrue(result['comparisonReusedForStatusOnly'])
        self.assertEqual(len(self.native_jobs), 1)

    def test_retry_still_rejects_changed_comparison_or_page(self):
        with patch.object(finalize.native, 'run', side_effect=self.native_success):
            self.invoke()
        path = self.bundle / 'differences.json'
        original = path.read_bytes()
        path.write_text('{}', encoding='utf-8')
        code, result = self.invoke()
        self.assertEqual(code, 3)
        self.assertIn('file_changed:', result['reason'])
        path.write_bytes(original)
        evidence = gate.load(self.bundle / 'evidence.json')
        Path(evidence['pages'][0]['image']['path']).write_bytes(b'changed')
        code, result = self.invoke()
        self.assertEqual(code, 3)
        self.assertIn('file_changed:', result['reason'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
