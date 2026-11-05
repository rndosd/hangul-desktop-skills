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

    def test_line_pair_rewrites_whole_line_and_keeps_mark(self):
        out = self.root/'line.hwpx'
        result = source_swap.swap(self.source, out, [
            {'find': '오늘 큰', 'replace': '새 기관은 내일 연수를 연다.', 'line': True},
            {'find': '안내', 'replace': '담당 교육정보부', 'flatten': True},
        ], batch)
        self.assertEqual(result['status'], 'PASS_STRUCTURE', result)
        self.assertEqual((result['replaced'], result['flattened'], result['flattenRequestsKeptStyle']), (2, 0, 1))
        runs = runs_of(out, '□')
        self.assertEqual(runs[0], ('□ ', self.plain))
        self.assertEqual(''.join(t for t, _ in runs), '□ 새 기관은 내일 연수를 연다.')

    def test_leading_label_keeps_its_emphasis(self):
        out = self.root/'label.hwpx'
        with HwpxDocument.open(self.source) as doc:
            p = doc.add_paragraph('', include_run=False)
            p.add_run(' ㅇ ')
            p.add_run('(방향) ', bold=True)
            p.add_run('옛 사업을 넓힌다')
            doc.save_to_path(self.root/'labelled.hwpx')
        source_swap.swap(self.root/'labelled.hwpx', out, [
            {'find': '옛 사업', 'replace': '(방향) 새 연수를 늘린다', 'line': True}], batch)
        runs = [r for r in runs_of(out, ' ㅇ') if r[0]]
        self.assertEqual(runs[1], ('(방향) ', self.bold))
        self.assertEqual(runs[2][0], '새 연수를 늘린다')

    def test_deleting_a_spaced_line_takes_one_blank_and_headings_keep_with_next(self):
        spaced = self.root/'spaced.hwpx'
        with HwpxDocument.new() as doc:
            for text in ['□ 추진 계획', '', ' ㅇ 첫째 내용입니다', '', ' ㅇ 지울 내용입니다', '', ' ㅇ 셋째 내용입니다']:
                doc.add_paragraph(text)
            doc.save_to_path(spaced)
        out = self.root/'spaced-out.hwpx'
        result = source_swap.swap(spaced, out, [{'find': '지울 내용', 'delete': True}], batch)
        self.assertEqual((result['deleted'], result['spacersRemoved']), (1, 1), result)
        self.assertEqual(result['deletedLines'], [' ㅇ 지울 내용입니다'])
        with HwpxDocument.open(out) as doc:
            texts = [p.text for p in doc.paragraphs][-5:]
        self.assertEqual(texts, ['□ 추진 계획', '', ' ㅇ 첫째 내용입니다', '', ' ㅇ 셋째 내용입니다'])
        self.assertEqual(result['keptWithNext'], 2)
        from hwpx_automation.office.agent import HwpxAgentDocument
        with HwpxAgentDocument.open(out) as agent:
            nodes = agent.get('/section[1]', depth=1, child_limit=50).to_dict()['children']
        keep = {n['summary'].get('text', ''): n['summary'].get('keepWithNext') for n in nodes}
        self.assertTrue(keep['□ 추진 계획'])
        self.assertFalse(keep[' ㅇ 첫째 내용입니다'])

    def png(self, name, width, height):
        import pymupdf
        doc = pymupdf.open()
        page = doc.new_page(width=width, height=height)
        page.draw_rect(page.rect, color=(0, 0.4, 0), fill=(0, 0.4, 0))
        path = self.root/name
        page.get_pixmap().save(str(path))
        return path

    def test_pictures_are_listed_replaced_and_deleted(self):
        pictured = self.root/'pictured.hwpx'
        old = self.png('old.png', 200, 40)
        with HwpxDocument.open(self.source) as doc:
            doc.add_picture(old.read_bytes(), 'png', width_mm=50, height_mm=10)
            doc.add_picture(old.read_bytes(), 'png', width_mm=50, height_mm=10)
            doc.save_to_path(pictured)
        listed = source_swap.listing(pictured)['pictureList']
        self.assertEqual(len(listed), 2)
        self.assertIn('50×10mm', listed[0])
        new = self.png('new.png', 250, 50)
        out = self.root/'pictured-out.hwpx'
        result = source_swap.swap(pictured, out, [
            {'picture': 1, 'replace': str(new)}, {'picture': 2, 'delete': True}], batch)
        self.assertEqual((result['status'], result['picturesReplaced'], result['picturesDeleted']),
                         ('PASS_STRUCTURE', 1, 1), result)
        self.assertEqual(result['pictureNotes'], [])
        with HwpxDocument.open(out) as doc:
            refs = doc.media.picture_references()
            images = {str(item) for item in doc.media.images}
        self.assertEqual(len(refs), 1)
        self.assertEqual(round(refs[0].width * 25.4 / 7200), 50)
        self.assertIn(refs[0].binary_item_id_ref, images)
        square = self.png('square.png', 40, 40)
        notes = source_swap.swap(pictured, self.root/'square-out.hwpx',
                                 [{'picture': 1, 'replace': str(square)}], batch)['pictureNotes']
        self.assertTrue(notes and '늘어나' in notes[0])
        missing = source_swap.swap(pictured, self.root/'missing.hwpx', [{'picture': 9, 'delete': True}], batch)
        self.assertEqual(missing['unresolved'][0]['reason'], 'not_found')

    def test_full_width_space_stays_and_pieces_around_it_change(self):
        spaced = self.root/'fw.hwpx'
        with HwpxDocument.new() as doc:
            p = doc.add_paragraph('', include_run=False)
            p.add_run('□ 일시 : ')
            p.add_run('11. 4. 13:30\u3000(160분)', bold=True, expand_special_characters=True)
            doc.save_to_path(spaced)
        listed = source_swap.listing(spaced)['lines']
        self.assertTrue(any('11. 4. 13:30\u3000(160분)' in line and '✗' not in line for line in listed), listed)
        out = self.root/'fw-out.hwpx'
        result = source_swap.swap(spaced, out, [
            {'find': '일시 :', 'replace': '□ 일시 : 11. 18. 14:00\u3000(100분)', 'line': True}], batch)
        self.assertEqual(result['status'], 'PASS_STRUCTURE', result)
        import zipfile
        xml = zipfile.ZipFile(out).read('Contents/section0.xml').decode('utf-8')
        self.assertIn('11. 18. 14:00<hp:fwSpace/>(100분)', xml)
        with self.assertRaisesRegex(ValueError, 'unsupported_fixed_space_count'):
            source_swap.swap(spaced, self.root/'fw-bad.hwpx', [
                {'find': '일시 :', 'replace': '□ 일시 : 11. 18. 14:00 (100분)', 'line': True}], batch)

    def test_bad_pairs_are_rejected(self):
        with self.assertRaises(ValueError):
            source_swap.swap(self.source, self.root/'x.hwpx', [{'find': 'a'}], batch)
        with self.assertRaises(ValueError):
            source_swap.swap(self.source, self.root/'x.hwpx', [{'find': 'a"b', 'delete': True}], batch)
        with self.assertRaises(ValueError):
            source_swap.swap(self.source, self.root/'x.hwpx', [{'picture': 1, 'replace': 'no-such.png'}], batch)


if __name__ == '__main__':
    unittest.main()
