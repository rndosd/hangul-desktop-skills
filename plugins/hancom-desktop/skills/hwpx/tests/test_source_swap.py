# SPDX-License-Identifier: Apache-2.0
"""Whole-paragraph rewrites keep the body style; swap resolves plain pairs."""
from pathlib import Path
import sys
import tempfile
import unittest

from hwpx import HwpxDocument

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import safe_edit as se  # noqa: E402
import source_swap  # noqa: E402
from hangul_task import batch  # noqa: E402

OLD = '□ 옛기관은 오늘 큰 행사를 연다.'


def runs_of(path, text_start):
    with HwpxDocument.open(path) as doc:
        for paragraph in doc.paragraphs:
            if paragraph.text.startswith(text_start):
                return [(r.text, r.char_pr_id_ref) for r in paragraph.runs]
    raise AssertionError('paragraph not found')


class SourceSwapTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root/'source.hwpx'
        with HwpxDocument.new() as doc:
            p = doc.add_paragraph('', include_run=False)
            p.add_run('□ ')
            p.add_run('옛기관', bold=True)
            p.add_run('은 오늘 ')
            p.add_run('큰 행사', bold=True)
            p.add_run('를 연다.')
            doc.add_paragraph('담당 부서 안내')
            table = doc.add_table(1, 2)
            table.cell(0, 0).set_text('일정')
            cell = table.cell(0, 1)
            cell.set_text('개회')
            cell.add_paragraph('지울 사람')
            cell.add_paragraph('남길 사람')
            doc.add_paragraph('같은 말')
            doc.add_paragraph('같은 말 뒤')
            doc.save_to_path(self.source)
        before = runs_of(self.source, '□')
        self.plain = before[0][1]
        self.bold = before[1][1]
        self.assertNotEqual(self.plain, self.bold)

    def plan(self, find, replace, style):
        inspection = se.inspect_many(self.source, [{'find': find}])
        token = inspection[0]['targets'][0]['target_id']
        change = {'query': 0, 'targets': [token], 'replace': replace}
        if style:
            change['style'] = style
        return se.combine_plans(inspection, [change])

    def test_base_style_writes_middle_in_plain_run_and_keeps_marker(self):
        out = self.root/'base.hwpx'
        se.apply_plan(self.source, out, self.plan(OLD, '□ 새봄초등학교는 18일 학부모 연수를 운영한다.', 'base'))
        runs = runs_of(out, '□')
        self.assertEqual(runs[0], ('□ ', self.plain))
        written = [(t, s) for t, s in runs if t]
        self.assertEqual(''.join(t for t, _ in written), '□ 새봄초등학교는 18일 학부모 연수를 운영한다.')
        self.assertTrue(all(s == self.plain for _, s in written), runs)

    def test_keep_style_still_spreads_by_old_lengths(self):
        out = self.root/'keep.hwpx'
        se.apply_plan(self.source, out, self.plan(OLD, '□ 새봄초등학교는 18일 학부모 연수를 운영한다.', None))
        runs = runs_of(out, '□')
        self.assertTrue(any(s == self.bold and t for t, s in runs))

    def test_listing_marks_mixed_styles(self):
        listed = source_swap.listing(self.source)
        self.assertEqual(listed['status'], 'LISTED')
        self.assertTrue(any(line.startswith('[본문] □ 옛기관') and '서식 2종' in line for line in listed['lines']))
        self.assertTrue(any(line.startswith('[표1 1행2열] 지울 사람') for line in listed['lines']))

    def test_swap_replaces_deletes_and_reports(self):
        out = self.root/'swap.hwpx'
        result = source_swap.swap(self.source, out, [
            {'find': OLD, 'replace': '□ 새 기관은 내일 연수를 연다.'},
            {'find': '담당 부서 안내', 'replace': '담당 교육정보부'},
            {'find': '같은 말', 'replace': '다른 말'},
            {'find': '없는 문구', 'replace': 'x'},
            {'find': '지울 사람', 'delete': True},
        ], batch)
        self.assertEqual(result['status'], 'PARTIAL', result)
        self.assertEqual((result['replaced'], result['deleted']), (3, 1))
        self.assertEqual([u['reason'] for u in result['unresolved']], ['not_found'])
        with HwpxDocument.open(out) as doc:
            texts = [p.text for p in doc.paragraphs]
        self.assertIn('□ 새 기관은 내일 연수를 연다.', texts)
        self.assertIn('다른 말', texts)
        self.assertIn('같은 말 뒤', texts)
        listed = '\n'.join(source_swap.listing(out)['lines'])
        self.assertNotIn('지울 사람', listed)
        self.assertIn('남길 사람', listed)
        self.assertEqual(result['layoutFollowUp'][-1]['reason'], 'cell_paragraphs_deleted')

    def test_ambiguous_and_overlap_are_reported_not_guessed(self):
        out = self.root/'amb.hwpx'
        result = source_swap.swap(self.source, out, [
            {'find': '사람', 'replace': '분'},
            {'find': '담당 부서 안내', 'replace': '안내'},
            {'find': '부서', 'replace': '과'},
        ], batch)
        reasons = {u['find']: u['reason'] for u in result['unresolved']}
        self.assertEqual(reasons, {'사람': 'ambiguous', '부서': 'inside_text_changed_by_earlier_pair'})
        self.assertEqual(result['replaced'], 1)

    def test_bad_pairs_are_rejected(self):
        with self.assertRaises(ValueError):
            source_swap.swap(self.source, self.root/'x.hwpx', [{'find': 'a'}], batch)
        with self.assertRaises(ValueError):
            source_swap.swap(self.source, self.root/'x.hwpx', [{'find': 'a"b', 'delete': True}], batch)


if __name__ == '__main__':
    unittest.main()
