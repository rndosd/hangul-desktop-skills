"""Common layout rules: structural checks on synthetic HWPX and line positions on synthetic PDFs."""
from pathlib import Path
import sys, tempfile, unittest, zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/hancom-desktop/skills/hwpx/scripts'))
sys.path.insert(0, str(ROOT / 'plugins/hancom-desktop/skills/hwpx-windows-finalize/scripts'))
import layout_rules
import wrap_alignment
import pymupdf

PARA = '<paraPr id="{id}"><align horizontal="{align}"/><margin><intent value="{intent}"/><left value="0"/><prev value="0"/><next value="0"/></margin><lineSpacing value="160"/></paraPr>'
CHAR = '<charPr id="{id}" height="1300"><fontRef hangul="1"/><spacing hangul="{spacing}"/>{bold}</charPr>'


def hwpx(path, paragraphs, paras=None, chars=None):
    paras = paras or {'1': ('LEFT', -2900), '2': ('LEFT', -2900)}
    chars = chars or {'1': (0, False)}
    header = ('<head><paraProperties>' + ''.join(PARA.format(id=i, align=a, intent=n) for i, (a, n) in paras.items())
              + '</paraProperties>' + ''.join(CHAR.format(id=i, spacing=s, bold='<bold/>' if b else '') for i, (s, b) in chars.items()) + '</head>')
    body = ''.join(f'<p paraPrIDRef="{p}">' + ''.join(f'<run charPrIDRef="{c}"><t>{t}</t></run>' for c, t in runs) + '</p>'
                   for p, runs in paragraphs)
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('Contents/header.xml', header)
        z.writestr('Contents/section0.xml', f'<sec>{body}</sec>')


class StructureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'doc.hwpx'

    def rules(self, paragraphs, **kw):
        hwpx(self.path, paragraphs, **kw)
        return {f['rule'] for f in layout_rules.check(self.path)['findings']}

    def test_consistent_items_pass(self):
        hwpx(self.path, [('1', [('1', '  ◦ 첫째 항목')]), ('1', [('1', '  ◦ 둘째 항목')]), ('2', [('1', '   - 세부')])])
        self.assertEqual(layout_rules.check(self.path)['status'], 'PASS')

    def test_justified_item_is_r2(self):
        self.assertIn('R2', self.rules([('1', [('1', '  ◦ 항목')])], paras={'1': ('JUSTIFY', -2900)}))

    def test_same_level_different_hanging_is_r3(self):
        self.assertIn('R3', self.rules([('1', [('1', '  ◦ 가')]), ('2', [('1', '  ◦ 나')])],
                                       paras={'1': ('LEFT', -2900), '2': ('LEFT', -3500)}))

    def test_detail_without_parent_is_r5(self):
        self.assertIn('R5', self.rules([('1', [('1', '본문 문단')]), ('1', [('1', '   - 부모 없는 세부')])]))

    def test_circled_number_may_carry_detail(self):
        self.assertNotIn('R5', self.rules([('1', [('1', '① 현재: 상황')]), ('1', [('1', '   ⇒ 개선: 방향')])]))

    def test_item_text_weight_mix_is_r6_but_inline_emphasis_is_not(self):
        chars = {'1': (0, False), '2': (0, True)}
        self.assertIn('R6', self.rules([('1', [('1', '  ◦ 보통')]), ('1', [('2', '  ◦ 굵게')])], chars=chars))
        self.assertNotIn('R6', self.rules([('1', [('1', '  ◦ 보통')]), ('1', [('1', '  ◦ 일부 '), ('2', '강조')])], chars=chars))


class WrapTest(unittest.TestCase):
    def pdf(self, items):
        """items: (x, first line, continuation offset in mm or None). Continuations start at the body x + offset."""
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'doc.pdf'
        doc = pymupdf.open(); page = doc.new_page()
        y = 80
        for x, text, offset in items:
            page.insert_text((x, y), text, fontname='korea', fontsize=12)
            if offset is not None:
                chars = [c for b in page.get_text('rawdict')['blocks'] for l in b.get('lines', []) for s in l['spans'] for c in s['chars']
                         if abs(c['origin'][1] - y) < 1 and not c['c'].isspace()]
                body = chars[1]['bbox'][0]
                page.insert_text((body + offset / wrap_alignment.PT_TO_MM, y + 16), '이어지는 둘째 줄', fontname='korea', fontsize=12)
                y += 16
            y += 30
        doc.save(path)
        return wrap_alignment.measure(path)

    def test_aligned_wrap_passes(self):
        report = self.pdf([(60, '- 첫째 줄 본문', 0.0)])
        self.assertEqual((report['status'], report['wrappedItems'], report['misaligned']), ('PASS', 1, 0))

    def test_offset_wrap_warns(self):
        report = self.pdf([(60, '- 첫째 줄 본문', 3.0)])
        self.assertEqual((report['status'], report['misaligned']), ('WARN', 1))
        self.assertAlmostEqual(report['details'][0]['offsetMm'], 3.0, delta=0.2)

    def test_no_wrapped_item_is_not_checked(self):
        self.assertEqual(self.pdf([(60, '- 한 줄 항목', None)])['status'], 'NOT_CHECKED')

    def test_deeper_level_left_of_parent_warns(self):
        report = self.pdf([(90, '◦ 상위 항목', None), (60, '- 하위 항목', None)])
        self.assertTrue(any(w.startswith('[R4]') for w in report['warnings']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
