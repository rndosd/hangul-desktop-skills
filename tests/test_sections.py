"""fill sections: repeat a whole activity area with renumbered headings, and reject bad section input (no COM)."""
from pathlib import Path
import json, subprocess, sys, tempfile, unittest, zipfile

SKILL = Path(__file__).resolve().parents[1] / 'plugins/hancom-desktop/skills/hwpx'
T = lambda *xs: [{'text': x} for x in xs]


def cli(*args):
    return subprocess.run([sys.executable, '-X', 'utf8', '-B', str(SKILL / 'scripts/hangul_task.py'), *map(str, args), '--full-output'],
                          capture_output=True, text=True, encoding='utf-8')


def text_of(path):
    with zipfile.ZipFile(path) as z:
        return z.read('Contents/section0.xml').decode('utf-8')


class SectionFill(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def fill(self, template, values):
        path = self.tmp / f'{template}.json'
        path.write_text(json.dumps(values, ensure_ascii=False), encoding='utf-8')
        out = self.tmp / f'{template}.hwpx'
        result = cli('fill', '--template', template, '--values', path, '--output', out)
        return json.loads(result.stdout), out

    def test_describe_lists_sections(self):
        result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(SKILL / 'scripts/hangul_task.py'), 'fill', '--template', 'plan-education'],
                                capture_output=True, text=True, encoding='utf-8')
        sections = json.loads(result.stdout)['sections']
        self.assertEqual((sections['activities']['min'], sections['activities']['max']), (1, 6))
        self.assertIn('task1_details', sections['activities']['inputs'])

    def test_education_three_activity_areas(self):
        areas = [{'task1_title': f'영역 {i}', 'period': f'기간 {i}', 'audience': '전교생', 'method': f'방법 {i}',
                  'task1_goals': T(f'목적 {i}'), 'task1_details': T(f'내용 {i}-가', f'내용 {i}-나')} for i in (1, 2, 3)]
        result, out = self.fill('plan-education', {'title': '시험 계획', 'sections': {'activities': areas}})
        self.assertEqual(result['status'], 'PASS_STRUCTURE', result.get('reason'))
        xml = text_of(out)
        for i, glyph in zip((1, 2, 3), ('\U000f02b1', '\U000f02b2', '\U000f02b3')):
            self.assertIn(f'{glyph} 영역 {i}', xml)
            self.assertIn(f'내용 {i}-나', xml)
        self.assertEqual(result['form']['sections'], {'activities': 3})

    def test_linked_input_stays_shared(self):
        # 'period' sits in the activity section and is linked from the support/management blocks.
        areas = [{'task1_title': f'영역 {i}', 'period': f'영역기간-{i}', 'task1_details': T(f'내용 {i}')} for i in (1, 2)]
        result, out = self.fill('plan-education', {'period': '전체기간', 'sections': {'activities': areas}})
        self.assertEqual(result['status'], 'PASS_STRUCTURE', result.get('reason'))
        xml = text_of(out)
        self.assertIn('영역기간-1', xml)
        self.assertIn('영역기간-2', xml)
        self.assertIn('전체기간', xml)

    def test_school_headings_replace_fixed_text(self):
        events = [{'heading': '오전 행사', 'activity_goal': '가', 'audience': '1학년', 'location': '강당', 'activities': T('a')},
                  {'heading': '오후 행사', 'activity_goal': '나', 'audience': '2학년', 'location': '운동장', 'activities': T('b')}]
        result, out = self.fill('plan-school', {'title': '시험', 'sections': {'activities': events}})
        self.assertEqual(result['status'], 'PASS_STRUCTURE', result.get('reason'))
        xml = text_of(out)
        self.assertIn('\U000f02b1 오전 행사', xml)
        self.assertIn('\U000f02b2 오후 행사', xml)
        self.assertNotIn('운영 개요', xml)

    def test_bad_section_input_is_refused(self):
        for values in ({'sections': {'activities': []}},                                   # below min 1
                       {'sections': {'activities': [{'unknown': 'x'}]}},                    # not a section input
                       {'task1_title': 'x', 'sections': {'activities': [{'task1_title': 'y'}]}},  # given twice
                       {'sections': {'nope': [{}]}}):
            with self.subTest(values=values):
                result, out = self.fill('plan-education', values)
                self.assertEqual(result['status'], 'BLOCKED')
                self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
