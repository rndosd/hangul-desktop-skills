"""Assembly outline validation, numbering and template loading. No COM."""
import copy
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import native_assembly as a
from native_composition import inputs, validate

CATALOG = Path(__file__).resolve().parents[2] / 'hwpx/assets/document-templates/assembly'


def outline(*nodes):
    return {'schema': a.OUTLINE_SCHEMA, 'template': 'plan-official',
            'cover': {'title': '가상 시행계획', 'date': '2027. 3. 15.'}, 'nodes': list(nodes)}


def labels(plan):
    return [s['text'].split(' ')[0] for s in plan['steps'] if s['op'] == 'text' and s['find'] in ('[장 제목]', '[1단계 제목]', '[2단계 제목]', '[3단계 제목]')]


CHAPTER = {'t': 'chapter', 'text': '개요'}
H1 = {'t': 'heading', 'level': 1, 'text': '목적'}
H2 = {'t': 'heading', 'level': 2, 'text': '세부'}
H3 = {'t': 'heading', 'level': 3, 'text': '항목'}
ITEM = {'t': 'item', 'text': '내용을 적음.'}


class AssemblyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = a.load_template(CATALOG, 'plan-official')

    def plan(self, *nodes):
        return a.build_plan(copy.deepcopy(self.manifest), outline(*nodes))

    def rejects(self, message, *nodes, cover=None):
        value = outline(*nodes)
        if cover is not None:
            value['cover'] = cover
        with self.assertRaisesRegex(ValueError, message):
            a.build_plan(copy.deepcopy(self.manifest), value)

    def test_manifest_lists_every_kind_with_existing_hashed_parts(self):
        kinds = {p['kind'] for p in self.manifest['parts'].values()}
        self.assertEqual(kinds, set(a.PART_KINDS))
        self.assertEqual({p['level'] for p in self.manifest['parts'].values() if p['kind'] == 'heading'}, {1, 2, 3})
        self.assertTrue(all(Path(p['path']).is_file() for p in self.manifest['parts'].values()))
        self.assertIn('교육부', self.manifest['source']['attribution'])

    def test_parts_name_no_legacy_hft_face(self):
        head = '{http://www.hancom.co.kr/hwpml/2011/head}'
        for name, part in self.manifest['parts'].items():
            with zipfile.ZipFile(part['path']) as package:
                header = ElementTree.fromstring(package.read('Contents/header.xml'))
            legacy = {(node.get('lang').lower(), font.get('id')) for node in header.iter(head + 'fontface')
                      for font in node.iter(head + 'font') if font.get('type') == 'HFT'}
            named = {slot_id for ref in header.iter(head + 'fontRef') for slot_id in ref.attrib.items()}
            self.assertFalse(named & legacy, name)

    def test_changed_part_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            copy_dir = Path(temp) / 'plan-official'
            shutil.copytree(CATALOG / 'plan-official', copy_dir)
            with (copy_dir / 'parts/spacer.hwpx').open('ab') as handle:
                handle.write(b'x')
            with self.assertRaisesRegex(ValueError, 'manifest와 다릅니다: spacer'):
                a.load_template(temp, 'plan-official')
        with self.assertRaisesRegex(ValueError, '조립 양식이 없습니다'):
            a.load_template(CATALOG, 'missing')

    def test_numbering_follows_the_outline(self):
        plan = self.plan(CHAPTER, H1, H2, H3, ITEM, H3, H2, H1, H2, CHAPTER, H1, CHAPTER)
        self.assertEqual(labels(plan), ['Ⅰ.', '1.', '가.', '1)', '2)', '나.', '2.', '가.', 'Ⅱ.', '1.', 'Ⅲ.'])

    def test_dropping_a_section_renumbers_without_a_gap(self):
        full = [CHAPTER, H1, ITEM, dict(H1, text='삭제될 절'), ITEM, H1, H2, H2, CHAPTER, H1]
        short = full[:3] + full[5:]
        self.assertEqual(labels(self.plan(*full)), ['Ⅰ.', '1.', '2.', '3.', '가.', '나.', 'Ⅱ.', '1.'])
        self.assertEqual(labels(self.plan(*short)), ['Ⅰ.', '1.', '2.', '가.', '나.', 'Ⅱ.', '1.'])

    def test_items_under_level_three_use_the_deep_parts(self):
        plan = self.plan(CHAPTER, H1, ITEM, H2, H3, ITEM, {'t': 'dash', 'text': '세부'}, H2, ITEM)
        inserted = [s['part'] for s in plan['steps'] if s['op'] == 'insert']
        self.assertEqual(inserted, ['chapter_first', 'heading1', 'item', 'heading2', 'heading3', 'item-deep', 'dash-deep', 'heading2', 'item'])

    def test_body_section_spacer_page_numbers_and_box_width(self):
        plan = self.plan(CHAPTER, H1, CHAPTER)
        ops = [(s['op'], s.get('part')) for s in plan['steps']][4:]
        self.assertEqual(ops[:3], [('section', None), ('insert', 'chapter_first'), ('pageNumbers', None)])
        self.assertIn(('insert', 'spacer'), ops)
        self.assertLess(ops.index(('insert', 'spacer')), ops.index(('insert', 'chapter')))
        widths = [s['width'] for s in plan['steps'] if s['op'] == 'boxWidth']
        box = self.manifest['parts']['chapter_first']['box']
        self.assertEqual(a.box_width(box, box['sourceTitle']), box['sourceWidthHwp'])
        longer = self.plan(dict(CHAPTER, text='개요 및 추진 배경'))
        self.assertGreater([s['width'] for s in longer['steps'] if s['op'] == 'boxWidth'][0], widths[0])

    def test_tables_keep_part_columns(self):
        plan = self.plan(CHAPTER, {'t': 'table', 'part': 'schedule', 'rows': [['안내', '3. 15.', ''], ['실시', '9. 15.', '각 학교']]})
        table = next(s for s in plan['steps'] if s['op'] == 'table')
        self.assertEqual((table['have'], table['cols'], table['prefix']), (9, 3, ' ○ '))
        self.rejects('칸 수가 3이 아닙니다', CHAPTER, {'t': 'table', 'part': 'schedule', 'rows': [['안내', '3. 15.']]})
        self.rejects("표 부품 'item'", CHAPTER, {'t': 'table', 'part': 'item', 'rows': [['a']]})

    def test_table_header_override_is_validated(self):
        rows = [['1~2학년군', '그림책 읽기']]
        plain = next(s for s in self.plan(CHAPTER, {'t': 'table', 'part': 'two-column', 'rows': rows})['steps'] if s['op'] == 'table')
        self.assertIsNone(plain['header'])
        named = self.plan(CHAPTER, {'t': 'table', 'part': 'two-column', 'header': ['학년군', '주요 활동'], 'rows': rows})
        self.assertEqual(next(s for s in named['steps'] if s['op'] == 'table')['header'], ['학년군', '주요 활동'])
        table = {'t': 'table', 'part': 'two-column', 'rows': rows}
        self.rejects('header 칸 수가 2', CHAPTER, dict(table, header=['학년군']))
        self.rejects('header 칸 수가 2', CHAPTER, dict(table, header='학년군'))
        self.rejects('header\\[2\\]: 빈 문구', CHAPTER, dict(table, header=['학년군', ' ']))
        self.rejects('header\\[1\\]: 양식 자리표시', CHAPTER, dict(table, header=['[항목]', '내용']))
        self.rejects('선택 header만', CHAPTER, dict(table, caption='표'))

    def test_table_cells_wrap_by_word_and_prefixed_column_hangs(self):
        head = '{http://www.hancom.co.kr/hwpml/2011/head}'
        core = '{http://www.hancom.co.kr/hwpml/2011/core}'
        for name, part in self.manifest['parts'].items():
            if part['kind'] != 'table':
                continue
            with zipfile.ZipFile(part['path']) as package:
                section = ElementTree.fromstring(package.read('Contents/section0.xml'))
                header = ElementTree.fromstring(package.read('Contents/header.xml'))
            shapes = {s.get('id'): s for s in header.iter(head + 'paraPr')}
            rows = list(next(section.iter(a.HP + 'tbl')).iter(a.HP + 'tr'))
            for row in rows:
                for cell in row.iter(a.HP + 'tc'):
                    for paragraph in cell.iter(a.HP + 'p'):
                        brk = shapes[paragraph.get('paraPrIDRef')].find(head + 'breakSetting')
                        self.assertEqual((brk.get('breakNonLatinWord'), brk.get('breakLatinWord')), ('BREAK_WORD', 'KEEP_WORD'), name)
            first = [list(row.iter(a.HP + 'tc'))[0].find(f'{a.HP}subList/{a.HP}p').get('paraPrIDRef') for row in rows[1:]]
            self.assertEqual(len(set(first)), 1, name)
            if part['table'].get('firstColumnPrefix'):
                shape = shapes[first[0]]
                self.assertEqual(shape.find(head + 'align').get('horizontal'), 'LEFT', name)
                self.assertLess(int(shape.find(f'.//{head}margin/{core}intent').get('value')), 0, name)
                others = [p.get('paraPrIDRef') for p in section.iter(a.HP + 'p') if p.get('paraPrIDRef') == first[0]]
                self.assertEqual(len(others), len(rows) - 1, f'{name}: the first column format is shared')

    def test_invalid_outlines_are_rejected_before_hangul(self):
        self.rejects('장\\(chapter\\)으로 시작', H1)
        self.rejects('2단계 제목 앞에 1단계 제목', CHAPTER, H2)
        self.rejects('3단계 제목 앞에 2단계 제목', CHAPTER, H1, H3)
        self.rejects('알 수 없는 t', CHAPTER, {'t': 'bullet', 'text': 'x'})
        self.rejects('빈 문구', CHAPTER, dict(ITEM, text='  '))
        self.rejects('줄바꿈', CHAPTER, dict(ITEM, text='한 줄\n두 줄'))
        self.rejects('자리표시', CHAPTER, dict(ITEM, text='[항목] 그대로'))
        self.rejects('level 1~3', CHAPTER, dict(H1, level=4))
        self.rejects('상자가 본문 폭을 넘습니다', dict(CHAPTER, text='아주 긴 장 제목을 한 줄에 넣으면 상자가 본문 폭을 넘어서게 됨'))
        self.rejects('title·date 필수', CHAPTER, cover={'title': '제목만'})
        self.rejects('장은 12개까지', *[CHAPTER] * 13)

    def test_resolved_plan_passes_the_native_boundary(self):
        plan = json.loads(json.dumps(self.plan(CHAPTER, H1, ITEM)))
        checked = validate(plan, plan['base']['path'])
        self.assertEqual(set(inputs(checked)), {plan['base']['path'], *(p['path'] for p in plan['parts'].values())})
        broken = copy.deepcopy(plan)
        broken['steps'].append({'op': 'insert', 'part': 'unknown'})
        with self.assertRaisesRegex(ValueError, 'unknown part'):
            validate(broken)


if __name__ == '__main__':
    unittest.main(verbosity=2)
