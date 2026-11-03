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

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tables = (Path(temp.name) / f'tables-{n}' for n in range(100))

    def plan(self, *nodes):
        return a.build_plan(copy.deepcopy(self.manifest), outline(*nodes), next(self.tables))

    def rejects(self, message, *nodes, cover=None):
        value = outline(*nodes)
        if cover is not None:
            value['cover'] = cover
        with self.assertRaisesRegex(ValueError, message):
            a.build_plan(copy.deepcopy(self.manifest), value, next(self.tables))

    def table_copy(self, plan):
        step = next(s for s in plan['steps'] if 'expect' in s)
        with zipfile.ZipFile(plan['parts'][step['part']]['path']) as package:
            table = next(ElementTree.fromstring(package.read('Contents/section0.xml')).iter(a.HP + 'tbl'))
        cells = [[[''.join(t.text or '' for t in p.iter(a.HP + 't')) for p in tc.iter(a.HP + 'p')] for tc in tr.iter(a.HP + 'tc')]
                 for tr in table.iter(a.HP + 'tr')]
        rows = [[tc.find(a.HP + 'cellAddr').get('rowAddr') for tc in tr.iter(a.HP + 'tc')] for tr in table.iter(a.HP + 'tr')]
        return step, table.get('rowCnt'), cells, rows

    def test_manifest_lists_every_kind_with_existing_hashed_parts(self):
        kinds = {p['kind'] for p in self.manifest['parts'].values()}
        self.assertEqual(kinds, {'cover', 'chapter_first', 'chapter', 'heading', 'table', 'spacer', 'item', 'dash', 'dot', 'note'})
        self.assertLessEqual(kinds, set(a.PART_KINDS))
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

    def test_table_rows_are_written_into_a_part_copy(self):
        plan = self.plan(CHAPTER, {'t': 'table', 'part': 'schedule', 'rows': [['안내', '3. 15.', ''], ['실시', '9. 15.', ['각 학교', '교육청']]]})
        step, count, cells, rows = self.table_copy(plan)
        self.assertEqual((step['op'], step['part'], step['expect']['tableRows'], count), ('insert', 'schedule@1', 3, '3'))
        self.assertEqual(cells[1:], [[[' ○ 안내'], ['3. 15.'], ['']], [[' ○ 실시'], ['9. 15.'], ['각 학교', '교육청']]])
        self.assertEqual(rows, [['0'] * 3, ['1'] * 3, ['2'] * 3])
        self.assertEqual(sorted(step['expect']['texts']), sorted(['안내', '3. 15.', '실시', '9. 15.', '각 학교', '교육청']))
        self.rejects('칸 수가 3이 아닙니다', CHAPTER, {'t': 'table', 'part': 'schedule', 'rows': [['안내', '3. 15.']]})
        self.rejects('rows\\[1\\]\\[3\\]\\[2\\]: 빈 문구', CHAPTER, {'t': 'table', 'part': 'schedule', 'rows': [['안내', '3. 15.', ['a', '']]]})
        self.rejects("표 부품 'item'", CHAPTER, {'t': 'table', 'part': 'item', 'rows': [['a']]})

    def test_a_unit_of_merged_rows_repeats(self):
        """Unit of two rows whose first cell spans both: each repeat shifts row addresses and keeps the span."""
        cell = ('<hp:tc><hp:subList><hp:p paraPrIDRef="1"><hp:run charPrIDRef="1"/></hp:p></hp:subList>'
                '<hp:cellAddr colAddr="{c}" rowAddr="{r}"/><hp:cellSpan colSpan="1" rowSpan="{s}"/><hp:cellSz width="100" height="10"/></hp:tc>')
        rows = [cell.format(c=0, r=0, s=1) + cell.format(c=1, r=0, s=1),
                cell.format(c=0, r=1, s=2) + cell.format(c=1, r=1, s=1), cell.format(c=1, r=2, s=1)]
        section = (f'<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="{a.HP[1:-1]}"><hp:p><hp:run><hp:tbl rowCnt="3">'
                   '<hp:sz width="200" height="30"/>' + ''.join(f'<hp:tr>{r}</hp:tr>' for r in rows) + '</hp:tbl></hp:run></hp:p></hs:sec>')
        temp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, temp)
        with zipfile.ZipFile(temp / 'part.hwpx', 'w') as package:
            package.writestr('Contents/section0.xml', section)
        part = {'path': str(temp / 'part.hwpx'), 'table': {'headerRows': 1, 'unitRows': 2}}
        self.assertEqual(a.table_instance(part, ['과제', '지표'], [['과제 1', '지표 가', '지표 나'], ['과제 2', '지표 다', '']], temp / 'out.hwpx'), 5)
        with zipfile.ZipFile(temp / 'out.hwpx') as package:
            table = next(ElementTree.fromstring(package.read('Contents/section0.xml')).iter(a.HP + 'tbl'))
        found = [(tc.find(a.HP + 'cellAddr').get('rowAddr'), tc.find(a.HP + 'cellSpan').get('rowSpan'), ''.join(t.text for t in tc.iter(a.HP + 't')))
                 for tc in table.iter(a.HP + 'tc')]
        self.assertEqual(found, [('0', '1', '과제'), ('0', '1', '지표'), ('1', '2', '과제 1'), ('1', '1', '지표 가'), ('2', '1', '지표 나'),
                                 ('3', '2', '과제 2'), ('3', '1', '지표 다'), ('4', '1', '')])

    def test_a_footer_row_follows_the_units_once(self):
        """A total row kept from the source: after every unit, its label cell fixed and its value cells filled."""
        cell = ('<hp:tc><hp:subList><hp:p paraPrIDRef="1"><hp:run charPrIDRef="1">{t}</hp:run></hp:p></hp:subList>'
                '<hp:cellAddr colAddr="{c}" rowAddr="{r}"/><hp:cellSpan colSpan="1" rowSpan="1"/><hp:cellSz width="100" height="10"/></hp:tc>')
        rows = [cell.format(c=0, r=0, t='') + cell.format(c=1, r=0, t=''), cell.format(c=0, r=1, t='') + cell.format(c=1, r=1, t=''),
                cell.format(c=0, r=2, t='<hp:t>계</hp:t>') + cell.format(c=1, r=2, t='')]
        section = (f'<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="{a.HP[1:-1]}"><hp:p><hp:run><hp:tbl rowCnt="3">'
                   '<hp:sz width="200" height="30"/>' + ''.join(f'<hp:tr>{r}</hp:tr>' for r in rows) + '</hp:tbl></hp:run></hp:p></hs:sec>')
        temp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, temp)
        with zipfile.ZipFile(temp / 'part.hwpx', 'w') as package:
            package.writestr('Contents/section0.xml', section)
        part = {'path': str(temp / 'part.hwpx'), 'table': {'headerRows': 1, 'unitRows': 1, 'footerRows': 1, 'footerCells': 1, 'footerLabelCells': [0]}}
        self.assertEqual(a.table_instance(part, ['기준', '배점'], [['필요성', '20'], ['적절성', '80']], temp / 'out.hwpx', ['100']), 4)
        with zipfile.ZipFile(temp / 'out.hwpx') as package:
            table = next(ElementTree.fromstring(package.read('Contents/section0.xml')).iter(a.HP + 'tbl'))
        found = [(tc.find(a.HP + 'cellAddr').get('rowAddr'), ''.join(t.text or '' for t in tc.iter(a.HP + 't'))) for tc in table.iter(a.HP + 'tc')]
        self.assertEqual(found, [('0', '기준'), ('0', '배점'), ('1', '필요성'), ('1', '20'), ('2', '적절성'), ('2', '80'), ('3', '계'), ('3', '100')])
        self.assertEqual(table.get('rowCnt'), '4')
        self.rejects('합계 줄\\(footer\\)이 없습니다', CHAPTER, {'t': 'table', 'part': 'schedule', 'rows': [['안내', '3. 15.', '']], 'footer': ['1']})

    def test_a_fixed_table_is_filled_by_row_name(self):
        spec = {'rowLabels': [{'label': '운영 요일', 'cells': 3}, {'label': '운영 시간', 'cells': 2}, {'label': '비고', 'cells': 1}]}
        self.assertEqual(a._by_label(spec, {'운영 시간': ['오전', '오후'], '운영 요일': ['월', '화', ['수', '목']]}, 't'),
                         ['월', '화', ['수', '목'], '오전', '오후', ''])  # in the table's row order; 비고 left out stays empty
        with self.assertRaisesRegex(ValueError, '칸 수가 2'):
            a._by_label(spec, {'운영 시간': ['오전']}, 't')
        with self.assertRaisesRegex(ValueError, '운영 요일, 운영 시간, 비고 중에서'):
            a._by_label(spec, {'장소': ['강당']}, 't')
        self.rejects('줄 이름이 없어 values', CHAPTER, {'t': 'table', 'part': 'schedule', 'values': {}})
        self.rejects('rows\\(또는 values\\) 하나', CHAPTER, {'t': 'table', 'part': 'schedule', 'values': {}, 'rows': []})

    def test_table_header_override_is_validated(self):
        rows = [['1~2학년군', '그림책 읽기']]
        _, _, plain, _ = self.table_copy(self.plan(CHAPTER, {'t': 'table', 'part': 'two-column', 'rows': rows}))
        self.assertEqual(plain[0], [[text] for text in self.manifest['parts']['two-column']['table']['header']])
        _, _, named, _ = self.table_copy(self.plan(CHAPTER, {'t': 'table', 'part': 'two-column', 'header': ['학년군', '주요 활동'], 'rows': rows}))
        self.assertEqual(named[0], [['학년군'], ['주요 활동']])
        table = {'t': 'table', 'part': 'two-column', 'rows': rows}
        self.rejects('header 칸 수가 2', CHAPTER, dict(table, header=['학년군']))
        self.rejects('header 칸 수가 2', CHAPTER, dict(table, header='학년군'))
        self.rejects('header\\[2\\]: 빈 문구', CHAPTER, dict(table, header=['학년군', ' ']))
        self.rejects('header\\[1\\]: 양식 자리표시', CHAPTER, dict(table, header=['[항목]', '내용']))
        self.rejects('선택 header·footer만', CHAPTER, dict(table, caption='표'))

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


class ProjectTemplateTest(unittest.TestCase):
    """plan-project: titles in table cells, summary page, boxed task numbers, a tab that fits its title."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = a.load_template(CATALOG, 'plan-project')

    def plan(self, outline_value):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        return a.build_plan(copy.deepcopy(self.manifest), outline_value, Path(temp.name) / 'tables')

    def outline(self, nodes, summary=None):
        value = {'schema': a.OUTLINE_SCHEMA, 'template': 'plan-project', 'cover': {'title': '가상 사업 계획', 'date': '2027. 3.'}, 'nodes': nodes}
        return dict(value, summary=summary) if summary else value

    def test_summary_tasks_and_chapters_number_in_their_own_styles(self):
        plan = self.plan(self.outline(
            [{'t': 'chapter', 'text': '추진 배경'}, {'t': 'task', 'text': '과제 가'}, {'t': 'task', 'text': '과제 나'}, {'t': 'chapter', 'text': '추진 계획'}],
            {'title': '요약 제목', 'nodes': [{'t': 'chapter', 'text': '요약 장'}, {'t': 'item', 'text': '요약'}, {'t': 'point', 'text': '현재'},
                                          {'t': 'point', 'text': '다음'}, {'t': 'arrow', 'text': '개선 방향'}]}))
        texts = [(s['find'], s['text']) for s in plan['steps'] if s['op'] == 'text']
        self.assertIn(('[요약 장 번호]', 'Ⅰ.'), texts)
        self.assertEqual([t for f, t in texts if f == '[점 번호]'], ['①', '②'])
        inserted = [s['part'] for s in plan['steps'] if s['op'] == 'insert']
        self.assertLess(inserted.index('summary_item'), inserted.index('chapter_first'))  # summary spacing on the summary page
        self.assertNotIn('summary_item', inserted[inserted.index('chapter_first'):])
        self.assertEqual([t for f, t in texts if f == '[장 번호]'], ['Ⅰ', 'Ⅱ'])
        self.assertEqual([t for f, t in texts if f == '[과제 번호]'], [chr(0xF02B1), chr(0xF02B2)])
        ops = [s['op'] for s in plan['steps']]
        self.assertEqual(ops.count('pageNumbers'), 1)
        self.assertNotIn('section', ops)
        first = next(i for i, s in enumerate(plan['steps']) if s.get('part') == 'chapter_first')
        self.assertEqual(plan['steps'][first - 1]['op'], 'pageBreak')

    def test_numbered_tab_widens_for_a_long_title(self):
        plan = self.plan(self.outline([{'t': 'chapter', 'text': '계획'}, {'t': 'heading', 'level': 1, 'text': '사업 추진 체계와 기관별 역할'}]))
        step = next(s for s in plan['steps'] if 'expect' in s)
        self.assertEqual(step['expect']['texts'], ['1', '사업 추진 체계와 기관별 역할'])
        width = lambda path: int(next(ElementTree.fromstring(zipfile.ZipFile(path).read('Contents/section0.xml')).iter(a.HP + 'tbl')).find(a.HP + 'sz').get('width'))
        self.assertGreater(width(plan['parts'][step['part']]['path']), width(self.manifest['parts']['heading1']['path']))

    def test_symbol_typed_in_the_text_is_not_drawn_twice(self):
        nodes = [{'t': 'chapter', 'text': '계획'}, {'t': 'note', 'text': '※ 참고 사항'}, {'t': 'item', 'text': '◦ 항목'},
                 {'t': 'dash', 'text': '-1℃ 기준'}, {'t': 'box', 'text': '◈ 핵심 문장'}]
        texts = [s['text'] for s in self.plan(self.outline(nodes))['steps'] if s['op'] == 'text' and s['find'] in ('[항목]', '[평가·환류 개요]')]
        self.assertEqual(texts, ['참고 사항', '항목', '-1℃ 기준', '핵심 문장'])

    def test_unknown_kind_lists_the_kinds_of_this_template(self):
        with self.assertRaisesRegex(ValueError, "'bullet'.*공통 역할.*subhead.*box"):
            self.plan(self.outline([{'t': 'chapter', 'text': '계획'}, {'t': 'bullet', 'text': 'x'}]))


class SchoolEducationTemplateTest(unittest.TestCase):
    """plan-school and plan-education: bars before the first chapter, numbered tab chapters, fixed table cells."""

    def plan(self, template_id, cover, nodes):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        manifest = a.load_template(CATALOG, template_id)
        value = {'schema': a.OUTLINE_SCHEMA, 'template': template_id, 'cover': cover, 'nodes': nodes}
        return manifest, a.build_plan(manifest, value, Path(temp.name) / 'tables')

    def test_school_starts_with_bars_and_numbers_tab_chapters(self):
        _, plan = self.plan('plan-school', {'title': '가상 운영계획'}, [
            {'t': 'subhead', 'text': '추진 근거'}, {'t': 'lead', 'text': '❍ 근거'},
            {'t': 'chapter', 'text': '세부 운영 계획'}, {'t': 'task', 'text': '운영 개요'}, {'t': 'item', 'text': '대상: 전교생'},
            {'t': 'chapter', 'text': '준비·지원 계획과 학교 안팎의 협력 체계'}, {'t': 'task', 'text': '준비'}, {'t': 'task', 'text': '기대 효과'}])
        texts = [(s['find'], s['text']) for s in plan['steps'] if s['op'] == 'text']
        self.assertIn(('[항목]', '근거'), texts)
        self.assertEqual([t for f, t in texts if f == '[과제 번호]'], [chr(0xF02B1), chr(0xF02B1), chr(0xF02B2)])
        tabs = [s['expect']['texts'] for s in plan['steps'] if 'expect' in s]
        self.assertEqual(tabs, [['1', '세부 운영 계획'], ['2', '준비·지원 계획과 학교 안팎의 협력 체계']])
        self.assertNotIn('pageNumbers', [s['op'] for s in plan['steps']])
        self.assertEqual([f for f, _ in texts[:2]], ['[계획서 제목]', '[학교·작성 부서]'])  # no date on this cover

    def test_school_step_table_keeps_its_arrows(self):
        manifest, plan = self.plan('plan-school', {'title': '가상 운영계획'}, [
            {'t': 'chapter', 'text': '일정'}, {'t': 'table', 'part': 'steps', 'rows': [['준비', '운영', '공유', '평가', '가', '나', '다', '라']]}])
        self.assertEqual(manifest['parts']['steps']['table']['unitCells'], 8)
        step = next(s for s in plan['steps'] if 'tableRows' in s.get('expect', {}))
        cells = [''.join(t.text or '' for t in c.iter(a.HP + 't'))
                 for c in ElementTree.fromstring(zipfile.ZipFile(plan['parts'][step['part']]['path']).read('Contents/section0.xml')).iter(a.HP + 'tc')]
        self.assertEqual(cells, ['준비', '⇨', '운영', '⇨', '공유', '⇨', '평가', '가', '나', '다', '라'])
        with self.assertRaisesRegex(ValueError, '묶음'):
            self.plan('plan-school', {'title': '가상'}, [{'t': 'chapter', 'text': '일정'}, {'t': 'table', 'part': 'steps', 'rows': [['x'] * 8, ['y'] * 8]}])

    def test_education_cover_fills_body_header_and_spaces_tasks_by_position(self):
        _, plan = self.plan('plan-education', {'title': '가상 사업', 'date': '2027. 3.', 'organization': '가상 기관'}, [
            {'t': 'subhead', 'text': '운영 여건'}, {'t': 'table', 'part': 'targets', 'rows': [['1', '전교생', '담임', '활동', '3월', '']]},
            {'t': 'subhead', 'text': '추진 방침'},
            {'t': 'chapter', 'text': '교육활동 운영'}, {'t': 'task', 'text': '첫 과제'}, {'t': 'item', 'text': '내용'}, {'t': 'task', 'text': '평가'}])
        texts = [(s['find'], s['text']) for s in plan['steps'] if s['op'] == 'text']
        self.assertEqual([f for f, t in texts if t == '가상 사업'], ['[사업 계획 제목]', '[본문 사업 제목]'])
        self.assertEqual([f for f, t in texts if t == '가상 기관'], ['[작성 기관·부서]', '[본문 작성 기관]'])
        inserted = [s['part'] for s in plan['steps'] if s['op'] == 'insert']
        # titles with nothing under them (추진 방침 before a chapter, 평가 at the end) come from loose copies
        self.assertEqual([p for p in inserted if p.startswith('subhead')], ['subhead', 'subhead_after_table@2'])
        self.assertEqual([p.split('@')[0] for p in inserted if p.startswith('task')], ['task_after_chapter', 'task'])
        self.assertEqual(sum(s['op'] == 'pageNumbers' for s in plan['steps']), 1)
        with self.assertRaisesRegex(ValueError, 'title·date 필수'):
            self.plan('plan-education', {'title': '가상 사업'}, [{'t': 'chapter', 'text': '운영'}])



class CommonVocabularyTest(unittest.TestCase):
    """One outline vocabulary for every template: missing roles, tables and cover fields are drawn by substitutes."""

    def plan(self, template_id, cover, nodes):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        notes = []
        value = {'schema': a.OUTLINE_SCHEMA, 'template': template_id, 'cover': cover, 'nodes': nodes}
        return a.build_plan(a.load_template(CATALOG, template_id), value, Path(temp.name) / 'tables', notes), notes

    def test_missing_roles_take_the_next_role_down_the_chain(self):
        plan, notes = self.plan('plan-school', {'title': '가상'}, [
            {'t': 'chapter', 'text': '운영'}, {'t': 'heading', 'level': 1, 'text': '개요'}, {'t': 'heading', 'level': 2, 'text': '세부'},
            {'t': 'item', 'text': '항목'}, {'t': 'dot', 'text': '‧ 하위'}, {'t': 'note', 'text': '※ 참고'}, {'t': 'box', 'text': '강조'}])
        self.assertEqual([(n['at'], n['role'], n['used']) for n in notes],
                         [('nodes[2]', 'heading1', 'task'), ('nodes[3]', 'heading2', 'task'), ('nodes[5]', 'dot', 'dash'),
                          ('nodes[6]', 'note', 'dash'), ('nodes[7]', 'box', 'lead')])
        texts = [(s['find'], s['text']) for s in plan['steps'] if s['op'] == 'text']
        self.assertEqual([t for f, t in texts if f == '[과제 번호]'], [chr(0xF02B1), chr(0xF02B2)])
        self.assertIn(('[항목]', '하위'), texts)  # the typed symbol of the original role is dropped too

    def test_subhead_on_the_official_template_becomes_a_numbered_heading(self):
        _, notes = self.plan('plan-official', {'title': '가상', 'date': '2027.'},
                             [{'t': 'chapter', 'text': '개요'}, {'t': 'subhead', 'text': '소제목'}, {'t': 'lead', 'text': '문단'}])
        self.assertEqual([(n['role'], n['used']) for n in notes], [('subhead', 'heading1'), ('lead', 'item')])

    def test_tables_are_picked_by_role_then_by_cell_count(self):
        plan, notes = self.plan('plan-school', {'title': '가상'}, [
            {'t': 'chapter', 'text': '일정'}, {'t': 'table', 'role': 'steps', 'rows': [['가', '나', '다', '라', '1', '2', '3', '4']]}])
        self.assertEqual(notes, [])
        self.assertTrue(any(step.get('part', '').startswith('steps@') for step in plan['steps']))
        plan, notes = self.plan('plan-education', {'title': '가상', 'date': '2027.'}, [
            {'t': 'chapter', 'text': '일정'}, {'t': 'table', 'role': 'schedule', 'rows': [['1', '가', '나', '다', '라', '']]}])
        self.assertEqual([(n['role'], n['used']) for n in notes], [('table:schedule', 'table:targets')])
        with self.assertRaisesRegex(ValueError, r"칸 3개 반복 표가 없습니다.*targets\(targets, 칸 6\)"):
            self.plan('plan-education', {'title': '가상', 'date': '2027.'},
                      [{'t': 'chapter', 'text': '일정'}, {'t': 'table', 'role': 'schedule', 'rows': [['업무', '일정', '']]}])

    def test_cover_values_without_a_place_are_carried_not_dropped(self):
        plan, notes = self.plan('plan-school', {'title': '가상', 'subtitle': '부제', 'date': '2027. 3.', 'organization': '가상학교', 'department': '교무부'},
                                [{'t': 'chapter', 'text': '운영'}])
        texts = dict((s['find'], s['text']) for s in plan['steps'] if s['op'] == 'text')
        self.assertEqual(texts['[계획서 제목]'], '가상 - 부제')
        self.assertEqual(texts['[학교·작성 부서]'], '가상학교 · 2027. 3. · 교무부')
        self.assertEqual([n['role'] for n in notes], ['subtitle', 'date', 'department'])

    def test_describe_lists_roles_substitutes_tables_and_cover(self):
        info = a.describe(a.load_template(CATALOG, 'plan-education'))
        self.assertIn('lead', info['roles'])
        self.assertEqual(info['substitutes']['heading1'], 'task')
        self.assertEqual([(t['part'], t['role'], t['cells']) for t in info['tables']], [('targets', 'targets', 6)])
        self.assertEqual(info['cover']['required'], ['title', 'date'])
        self.assertEqual(info['cover']['carried'], {'department': 'organization'})

    def test_reference_outlines_need_no_substitutes(self):
        for folder in sorted(p for p in CATALOG.iterdir() if (p / 'reproduction/outline.json').is_file()):
            temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
            notes = []
            a.build_plan(a.load_template(CATALOG, folder.name), json.loads((folder / 'reproduction/outline.json').read_text(encoding='utf-8')),
                         Path(temp.name) / 'tables', notes)
            self.assertEqual(notes, [], folder.name)
            expected = json.loads((folder / 'reproduction/expected.json').read_text(encoding='utf-8'))
            self.assertGreater(expected['pages'], 0, folder.name)

    def test_a_template_may_let_titles_skip_a_level(self):
        manifest = a.load_template(CATALOG, 'plan-official')
        value = {'schema': a.OUTLINE_SCHEMA, 'template': 'plan-official', 'cover': {'title': '가상', 'date': '2027.'},
                 'nodes': [{'t': 'chapter', 'text': '개요'}, {'t': 'heading', 'level': 2, 'text': '바로 가.'}]}
        with self.assertRaisesRegex(ValueError, '2단계 제목 앞에 1단계'):
            a.build_plan(copy.deepcopy(manifest), copy.deepcopy(value))
        manifest['rules']['headingLevelsMaySkip'] = True  # sources that put 가. right under a task
        plan = a.build_plan(manifest, value)
        self.assertIn('가.', [s['text'].split(' ')[0] for s in plan['steps'] if s['op'] == 'text'])


class RegisteredSourceTest(unittest.TestCase):
    """Behaviour found registering outside documents: title lists, numbered cells, source page breaks."""

    def plan(self, nodes):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        value = {'schema': a.OUTLINE_SCHEMA, 'template': 'plan-official', 'cover': {'title': '가상', 'date': '2027.'}, 'nodes': nodes}
        return a.build_plan(a.load_template(CATALOG, 'plan-official'), value, Path(temp.name) / 'tables')

    def test_titles_with_nothing_under_them_do_not_keep_with_the_next(self):
        plan = self.plan([CHAPTER, dict(H1, text='기간: 3월'), dict(H1, text='장소: 강당'), H1, ITEM, {'t': 'chapter', 'text': '계획'}])
        heads = [s['part'] for s in plan['steps'] if s['op'] == 'insert' and s['part'].startswith('heading')]
        self.assertEqual(['@' in p for p in heads], [True, True, False])  # the last 1. title has an item under it
        with zipfile.ZipFile(plan['parts'][heads[0]]['path']) as package:
            header = ElementTree.fromstring(package.read('Contents/header.xml'))
            ids = {p.get('paraPrIDRef') for p in ElementTree.fromstring(package.read('Contents/section0.xml')).findall(a.HP + 'p')}
        keeps = [b.get('keepWithNext') for s in header.iter(a.HH + 'paraPr') if s.get('id') in ids for b in s.iter(a.HH + 'breakSetting')]
        self.assertEqual(set(keeps), {'0'})

    def test_later_paragraphs_in_a_numbered_cell_are_not_numbered(self):
        header = a.etree.fromstring(  # lxml, like the parts native_assembly edits
            f'<hh:head xmlns:hh="{a.HH[1:-1]}"><hh:refList><hh:paraProperties itemCnt="2">'
            '<hh:paraPr id="0"><hh:heading type="BULLET" idRef="1" level="0"/></hh:paraPr>'
            '<hh:paraPr id="1"><hh:heading type="NUMBER" idRef="2" level="0"/></hh:paraPr></hh:paraProperties></hh:refList></hh:head>')
        cell = a.etree.fromstring(f'<hp:tc xmlns:hp="{a.HP[1:-1]}"><hp:subList><hp:p paraPrIDRef="1"><hp:run charPrIDRef="0"/></hp:p></hp:subList></hp:tc>')
        bullets = copy.deepcopy(cell)
        bullets.find(a.HP + 'subList/' + a.HP + 'p').set('paraPrIDRef', '0')
        plain = a._unnumbered(header)
        a._set_cell(cell, ['1단계', '신청서 제출', '접수'], plain=plain)
        a._set_cell(bullets, ['가', '나'], plain=plain)
        self.assertEqual([p.get('paraPrIDRef') for p in cell.iter(a.HP + 'p')], ['1', '2', '2'])
        self.assertEqual([p.get('paraPrIDRef') for p in bullets.iter(a.HP + 'p')], ['0', '0'])  # bullets repeat
        added = [s for s in header.iter(a.HH + 'paraPr') if s.get('id') == '2']
        self.assertEqual(added[0].find(a.HH + 'heading').get('type'), 'NONE')
        self.assertEqual(header.find(f'{a.HH}refList/{a.HH}paraProperties').get('itemCnt'), '3')

    def test_any_node_may_start_a_new_page(self):
        plan = self.plan([CHAPTER, ITEM, dict(ITEM, pageBreakBefore=True), {'t': 'chapter', 'text': '계획', 'pageBreakBefore': True}, ITEM])
        ops = [s['op'] if s['op'] != 'insert' else s['part'].split('@')[0] for s in plan['steps']]
        body = ops[ops.index('chapter_first'):]
        self.assertEqual(body.count('pageBreak'), 2)
        self.assertEqual(body[body.index('pageBreak') + 1], 'item')
        self.assertEqual(body[len(body) - 1 - body[::-1].index('pageBreak') + 1], 'chapter')
        with self.assertRaisesRegex(ValueError, 'pageBreakBefore'):
            self.plan([CHAPTER, dict(ITEM, pageBreakBefore='yes')])


if __name__ == '__main__':
    unittest.main(verbosity=2)
